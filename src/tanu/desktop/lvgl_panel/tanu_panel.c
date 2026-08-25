/*
 * tanu_panel.c — LVGL panel client for Tanu AI assistant.
 *
 * Renders Tanu's face, status bar, and response ticker directly to a Linux
 * framebuffer (/dev/fb0) via LVGL's fbdev driver. Connects to the Tanu
 * aiohttp WebSocket server to receive state updates and response tokens.
 *
 * Build: see CMakeLists.txt in this directory.
 * Usage: tanu_panel --ws-url ws://localhost:7337/ws/chat
 */

#include <getopt.h>
#include <libwebsockets.h>
#include <lvgl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* ---------------------------------------------------------------------------
 * Configuration
 * ------------------------------------------------------------------------- */

#define FACE_RADIUS      60
#define STATUS_BAR_H     18
#define RESPONSE_LINES   3
#define RESPONSE_BUF_SZ  4096
#define WS_RX_BUF_SZ     2048
#define MSG_JSON_SZ      2048
#define ANIM_TICK_MS     16  /* ~60 fps animation */
#define WS_POLL_MS       50  /* 20 Hz WebSocket poll */

#define BG_COLOR         lv_color_hex(0x14141f)

/* State accent colors (matching character.py) */
#define COLOR_IDLE       lv_color_hex(0x00d4ff)
#define COLOR_LISTENING  lv_color_hex(0x00ff88)
#define COLOR_THINKING   lv_color_hex(0xffaa00)
#define COLOR_SPEAKING   lv_color_hex(0xff00ff)
#define COLOR_ERROR      lv_color_hex(0xff4444)

/* ---------------------------------------------------------------------------
 * Globals
 * ------------------------------------------------------------------------- */

typedef enum {
    STATE_IDLE,
    STATE_LISTENING,
    STATE_THINKING,
    STATE_SPEAKING,
    STATE_ERROR,
} tanu_state_t;

static const char *state_names[] = {
    "idle", "listening", "thinking", "speaking", "error"
};

typedef struct {
    tanu_state_t state;
    int connected;
    char response[RESPONSE_BUF_SZ];
    char status[128];
    float anim_t;          /* animation time in seconds */
    int dirty;             /* 1 if UI needs redraw */
} panel_state_t;

static panel_state_t g_state = {
    .state     = STATE_IDLE,
    .connected = 0,
    .response  = "Waiting for server...",
    .status    = "Connecting...",
    .anim_t    = 0.0f,
    .dirty     = 1,
};

/* LVGL widgets */
static lv_obj_t *scr;
static lv_obj_t *face_canvas;
static lv_obj_t *status_label;
static lv_obj_t *response_label;

/* WebSocket context */
static struct lws_context *lws_ctx;
static struct lws *lws_wsi;
static char g_ws_url[256] = "ws://127.0.0.1:7337/ws/chat";

/* Canvas buffer for face drawing */
static lv_layer_t face_layer;
static lv_color_t face_buf[FACE_RADIUS * 2 * FACE_RADIUS * 2];

/* Signal handling */
static volatile int g_running = 1;

static void sighandler(int sig) {
    (void)sig;
    g_running = 0;
}

/* ---------------------------------------------------------------------------
 * State helpers
 * ------------------------------------------------------------------------- */

static lv_color_t get_state_color(tanu_state_t s) {
    switch (s) {
        case STATE_IDLE:      return COLOR_IDLE;
        case STATE_LISTENING: return COLOR_LISTENING;
        case STATE_THINKING:  return COLOR_THINKING;
        case STATE_SPEAKING:  return COLOR_SPEAKING;
        case STATE_ERROR:     return COLOR_ERROR;
        default:              return COLOR_IDLE;
    }
}

static tanu_state_t parse_state(const char *name) {
    for (int i = 0; i < (int)(sizeof(state_names) / sizeof(state_names[0])); i++) {
        if (strcmp(name, state_names[i]) == 0)
            return (tanu_state_t)i;
    }
    return STATE_IDLE;
}

/* Simple JSON value extractor for flat key:value pairs.
 * Writes the value string into `out` (max `out_sz` bytes).
 * Returns 0 on success, -1 if key not found. */
static int json_get_string(const char *json, const char *key,
                           char *out, size_t out_sz) {
    char needle[128];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return -1;
    p = strchr(p + strlen(needle), ':');
    if (!p) return -1;
    p++;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '"') {
        p++;
        const char *end = strchr(p, '"');
        if (!end) return -1;
        size_t len = (size_t)(end - p);
        if (len >= out_sz) len = out_sz - 1;
        memcpy(out, p, len);
        out[len] = '\0';
        return 0;
    }
    /* Numeric / boolean / null value */
    const char *start = p;
    while (*p && *p != ',' && *p != '}' && *p != '\n') p++;
    size_t len = (size_t)(p - start);
    if (len >= out_sz) len = out_sz - 1;
    memcpy(out, start, len);
    out[len] = '\0';
    return 0;
}

/* ---------------------------------------------------------------------------
 * Face drawing (LVGL canvas)
 * --------------------------------------------------------------------- */

static void draw_face_idle(int cx, int cy, lv_color_t color) {
    /* Center dot with breathing effect */
    float breathe = 4.0f + 3.0f * sinf(g_state.anim_t * 1.5f);
    lv_draw_arc_dsc_t arc_dsc;
    lv_draw_arc_dsc_init(&arc_dsc);
    arc_dsc.color = color;
    arc_dsc.width = 2;
    arc_dsc.start_angle = 0;
    arc_dsc.end_angle = 360;
    lv_area_t area = {(lv_coord_t)(cx - (int)breathe), (lv_coord_t)(cy - (int)breathe),
                      (lv_coord_t)(cx + (int)breathe), (lv_coord_t)(cy + (int)breathe)};
    lv_draw_arc(&face_layer, &arc_dsc, &area);

    /* Orbiting particles */
    for (int i = 0; i < 3; i++) {
        float angle = g_state.anim_t * 0.5f + i * 2.0943951f; /* TAU/3 */
        float r = FACE_RADIUS * 0.6f;
        int px = cx + (int)(cosf(angle) * r);
        int py = cy + (int)(sinf(angle) * r);
        lv_area_t pa = {(lv_coord_t)(px - 2), (lv_coord_t)(py - 2),
                        (lv_coord_t)(px + 2), (lv_coord_t)(py + 2)};
        lv_draw_fill_dsc_t fill;
        lv_draw_fill_dsc_init(&fill);
        fill.color = color;
        lv_draw_rect(&face_layer, &fill, &pa);
    }
}

static void draw_face_listening(int cx, int cy, lv_color_t color) {
    /* Concentric rings */
    for (int i = 0; i < 3; i++) {
        int ring_r = (int)(FACE_RADIUS * 0.4f) + i * 12;
        float pulse = sinf(g_state.anim_t * 4.0f + i) * 5.0f;
        ring_r += (int)pulse;
        if (ring_r < 2) ring_r = 2;
        lv_draw_arc_dsc_t arc;
        lv_draw_arc_dsc_init(&arc);
        arc.color = color;
        arc.width = 2;
        arc.start_angle = 0;
        arc.end_angle = 360;
        lv_area_t a = {(lv_coord_t)(cx - ring_r), (lv_coord_t)(cy - ring_r),
                       (lv_coord_t)(cx + ring_r), (lv_coord_t)(cy + ring_r)};
        lv_draw_arc(&face_layer, &arc, &a);
    }
    /* Center dot */
    lv_area_t ca = {(lv_coord_t)(cx - 6), (lv_coord_t)(cy - 6),
                    (lv_coord_t)(cx + 6), (lv_coord_t)(cy + 6)};
    lv_draw_fill_dsc_t fill;
    lv_draw_fill_dsc_init(&fill);
    fill.color = color;
    lv_draw_rect(&face_layer, &fill, &ca);
}

static void draw_face_thinking(int cx, int cy, lv_color_t color) {
    /* Orbiting dots */
    for (int i = 0; i < 5; i++) {
        float angle = g_state.anim_t * 3.0f + i * 1.256637f; /* TAU/5 */
        float r = FACE_RADIUS * 0.5f;
        int px = cx + (int)(cosf(angle) * r);
        int py = cy + (int)(sinf(angle) * r);
        int ds = 3 + (int)(sinf(g_state.anim_t * 5.0f + i) * 1.5f);
        if (ds < 1) ds = 1;
        lv_area_t a = {(lv_coord_t)(px - ds), (lv_coord_t)(py - ds),
                       (lv_coord_t)(px + ds), (lv_coord_t)(py + ds)};
        lv_draw_fill_dsc_t fill;
        lv_draw_fill_dsc_init(&fill);
        fill.color = color;
        lv_draw_rect(&face_layer, &fill, &a);
    }
    /* Pulsing center */
    int cs = 5 + (int)(sinf(g_state.anim_t * 4.0f) * 3.0f);
    lv_area_t ca = {(lv_coord_t)(cx - cs), (lv_coord_t)(cy - cs),
                    (lv_coord_t)(cx + cs), (lv_coord_t)(cy + cs)};
    lv_draw_fill_dsc_t fill;
    lv_draw_fill_dsc_init(&fill);
    fill.color = color;
    lv_draw_rect(&face_layer, &fill, &ca);
}

static void draw_face_speaking(int cx, int cy, lv_color_t color) {
    int bar_count = 8;
    int bar_w = 5;
    int max_h = (int)(FACE_RADIUS * 0.6f);

    for (int i = 0; i < bar_count; i++) {
        float angle = (i - bar_count / 2.0f) * 0.2f;
        int x = cx + (int)(angle * (FACE_RADIUS * 0.8f));
        int h = (int)(max_h * (0.3f + 0.7f * fabsf(sinf(g_state.anim_t * 8.0f + i * 0.7f))));
        if (h < 2) h = 2;
        lv_area_t a = {(lv_coord_t)(x - bar_w / 2), (lv_coord_t)(cy - h / 2),
                       (lv_coord_t)(x + bar_w / 2), (lv_coord_t)(cy + h / 2)};
        lv_draw_fill_dsc_t fill;
        lv_draw_fill_dsc_init(&fill);
        fill.color = color;
        lv_draw_rect(&face_layer, &fill, &a);
    }
}

static void draw_face_error(int cx, int cy, lv_color_t color) {
    if (sinf(g_state.anim_t * 6.0f) <= 0) return;
    int s = 12;
    int w = 3;
    lv_draw_line_dsc_t line;
    lv_draw_line_dsc_init(&line);
    line.color = color;
    line.width = w;

    lv_point_t pts1[] = {{(lv_coord_t)(cx - s), (lv_coord_t)(cy - s)},
                         {(lv_coord2_t){(lv_coord_t)(cx + s), (lv_coord_t)(cy + s)}}};
    lv_draw_line(&face_layer, &line, pts1, 2);

    lv_point_t pts2[] = {{(lv_coord_t)(cx + s), (lv_coord_t)(cy - s)},
                         {(lv_coord2_t){(lv_coord_t)(cx - s), (lv_coord_t)(cy + s)}}};
    lv_draw_line(&face_layer, &line, pts2, 2);
}

static void draw_face(void) {
    lv_canvas_fill_bg(face_canvas, BG_COLOR, LV_OPA_COVER);
    lv_canvas_init_layer(face_canvas, &face_layer);

    int cw = lv_canvas_get_width(face_canvas);
    int ch = lv_canvas_get_height(face_canvas);
    int cx = cw / 2;
    int cy = ch / 2;
    lv_color_t color = get_state_color(g_state.state);

    /* Outer glow */
    lv_draw_fill_dsc_t glow_fill;
    lv_draw_fill_dsc_init(&glow_fill);
    glow_fill.color = color;
    glow_fill.opa = LV_OPA_20;
    int glow_r = FACE_RADIUS + 15;
    lv_area_t ga = {(lv_coord_t)(cx - glow_r), (lv_coord_t)(cy - glow_r),
                    (lv_coord_t)(cx + glow_r), (lv_coord_t)(cy + glow_r)};
    lv_draw_rect(&face_layer, &glow_fill, &ga);

    /* Face circle */
    lv_draw_fill_dsc_t face_fill;
    lv_draw_fill_dsc_init(&face_fill);
    face_fill.color = lv_color_hex(0x1a1a2e);
    face_fill.opa = LV_OPA_COVER;
    lv_area_t fa = {(lv_coord_t)(cx - FACE_RADIUS), (lv_coord_t)(cy - FACE_RADIUS),
                    (lv_coord_t)(cx + FACE_RADIUS), (lv_coord_t)(cy + FACE_RADIUS)};
    lv_draw_rect(&face_layer, &face_fill, &fa);

    /* State-specific animation */
    switch (g_state.state) {
        case STATE_IDLE:      draw_face_idle(cx, cy, color); break;
        case STATE_LISTENING: draw_face_listening(cx, cy, color); break;
        case STATE_THINKING:  draw_face_thinking(cx, cy, color); break;
        case STATE_SPEAKING:  draw_face_speaking(cx, cy, color); break;
        case STATE_ERROR:     draw_face_error(cx, cy, color); break;
    }

    lv_canvas_finish_layer(face_canvas, &face_layer);
}

/* ---------------------------------------------------------------------------
 * UI creation
 * ------------------------------------------------------------------------- */

static void create_ui(void) {
    scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, BG_COLOR, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_clear_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    int scr_w = lv_display_get_horizontal_resolution(NULL);
    int scr_h = lv_display_get_vertical_resolution(NULL);
    int pad = 4;

    /* Status bar */
    status_label = lv_label_create(scr);
    lv_label_set_text(status_label, "Connecting...");
    lv_obj_set_style_text_color(status_label, lv_color_hex(0xaaaaaa), 0);
    lv_obj_set_style_text_font(status_label, &lv_font_montserrat_14, 0);
    lv_obj_align(status_label, LV_ALIGN_TOP_LEFT, pad, pad);

    /* Face canvas — centered vertically between status bar and response area */
    int face_area_top = STATUS_BAR_H + pad * 2;
    int resp_area_h = RESPONSE_LINES * 22 + pad * 2;
    int face_area_h = scr_h - face_area_top - resp_area_h - pad;
    int face_size = (face_area_h < scr_w - pad * 2) ? face_area_h : scr_w - pad * 2;
    if (face_size < 40) face_size = 40;

    face_canvas = lv_canvas_create(scr);
    lv_canvas_set_buffer(face_canvas, face_buf, face_size, face_size,
                         LV_COLOR_FORMAT_RGB565);
    lv_obj_align(face_canvas, LV_ALIGN_TOP_MID, 0, face_area_top + (face_area_h - face_size) / 2);

    /* Response ticker at bottom */
    response_label = lv_label_create(scr);
    lv_label_set_text(response_label, "");
    lv_label_set_long_mode(response_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(response_label, scr_w - pad * 2);
    lv_obj_set_style_text_color(response_label, lv_color_hex(0xdddddd), 0);
    lv_obj_set_style_text_font(response_label, &lv_font_montserrat_14, 0);
    lv_obj_align(response_label, LV_ALIGN_BOTTOM_LEFT, pad, -pad);
}

/* ---------------------------------------------------------------------------
 * UI update (called from animation timer)
 * ------------------------------------------------------------------------- */

static void update_ui(void) {
    lv_label_set_text(status_label, g_state.status);

    /* Truncate response to fit */
    char display_resp[RESPONSE_BUF_SZ];
    snprintf(display_resp, sizeof(display_resp), "%s", g_state.response);
    lv_label_set_text(response_label, display_resp);

    draw_face();
}

/* ---------------------------------------------------------------------------
 * WebSocket client (libwebsockets)
 * --------------------------------------------------------------------- */

typedef struct {
    unsigned char buf[WS_RX_BUF_SZ + LWS_PRE];
    size_t len;
    int ready;
} ws_user_data_t;

static int ws_callback(struct lws *wsi, enum lws_callback_reasons reason,
                       void *user, void *in, size_t len) {
    ws_user_data_t *ud = (ws_user_data_t *)user;

    switch (reason) {
    case LWS_CALLBACK_CLIENT_ESTABLISHED:
        g_state.connected = 1;
        snprintf(g_state.status, sizeof(g_state.status), "Connected");
        g_state.dirty = 1;
        break;

    case LWS_CALLBACK_CLIENT_RECEIVE: {
        /* Assemble message (handle partials) */
        if (ud->len + len > WS_RX_BUF_SZ) ud->len = 0;
        memcpy(ud->buf + LWS_PRE + ud->len, in, len);
        ud->len += len;
        if (lws_is_final_fragment(wsi)) {
            char *json = (char *)(ud->buf + LWS_PRE);
            json[ud->len] = '\0';

            char msg_type[64] = "";
            json_get_string(json, "type", msg_type, sizeof(msg_type));

            if (strcmp(msg_type, "token") == 0) {
                char content[512] = "";
                json_get_string(json, "content", content, sizeof(content));
                size_t curlen = strlen(g_state.response);
                if (curlen < RESPONSE_BUF_SZ - 2) {
                    /* If response was a status message, clear it first */
                    if (g_state.state == STATE_IDLE ||
                        g_state.state == STATE_THINKING) {
                        g_state.response[0] = '\0';
                        curlen = 0;
                    }
                    strncat(g_state.response, content,
                            RESPONSE_BUF_SZ - curlen - 1);
                }
                g_state.state = STATE_SPEAKING;
                snprintf(g_state.status, sizeof(g_state.status), "Speaking...");
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "response") == 0) {
                json_get_string(json, "content", g_state.response,
                                sizeof(g_state.response));
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "done") == 0) {
                g_state.state = STATE_IDLE;
                snprintf(g_state.status, sizeof(g_state.status), "Ready");
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "error") == 0) {
                char err_msg[256] = "Unknown error";
                json_get_string(json, "message", err_msg, sizeof(err_msg));
                snprintf(g_state.response, sizeof(g_state.response),
                         "Error: %s", err_msg);
                g_state.state = STATE_ERROR;
                snprintf(g_state.status, sizeof(g_state.status), "Error");
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "tool_start") == 0) {
                char tool_name[128] = "";
                json_get_string(json, "name", tool_name, sizeof(tool_name));
                snprintf(g_state.status, sizeof(g_state.status),
                         "Using: %s...", tool_name);
                g_state.state = STATE_THINKING;
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "tool_done") == 0) {
                snprintf(g_state.status, sizeof(g_state.status), "Thinking...");
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "state") == 0) {
                char sname[32] = "";
                json_get_string(json, "state", sname, sizeof(sname));
                g_state.state = parse_state(sname);
                if (g_state.state == STATE_IDLE)
                    snprintf(g_state.status, sizeof(g_state.status), "Ready");
                else if (g_state.state == STATE_THINKING)
                    snprintf(g_state.status, sizeof(g_state.status), "Thinking...");
                else if (g_state.state == STATE_SPEAKING)
                    snprintf(g_state.status, sizeof(g_state.status), "Speaking...");
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "status") == 0) {
                char provider[64] = "";
                char model[128] = "";
                json_get_string(json, "provider", provider, sizeof(provider));
                json_get_string(json, "model", model, sizeof(model));
                if (provider[0])
                    snprintf(g_state.status, sizeof(g_state.status),
                             "%s / %s", provider, model);
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "_connected") == 0) {
                g_state.connected = 1;
                g_state.state = STATE_IDLE;
                snprintf(g_state.status, sizeof(g_state.status), "Ready");
                g_state.dirty = 1;

            } else if (strcmp(msg_type, "_disconnected") == 0) {
                g_state.connected = 0;
                g_state.state = STATE_ERROR;
                snprintf(g_state.status, sizeof(g_state.status),
                         "Disconnected");
                g_state.dirty = 1;
            }

            ud->len = 0;
        }
        break;
    }

    case LWS_CALLBACK_CLIENT_CONNECTION_ERROR:
        g_state.connected = 0;
        snprintf(g_state.status, sizeof(g_state.status), "Connection error");
        g_state.state = STATE_ERROR;
        g_state.dirty = 1;
        lws_wsi = NULL;
        break;

    case LWS_CALLBACK_CLIENT_CLOSED:
        g_state.connected = 0;
        snprintf(g_state.status, sizeof(g_state.status), "Closed");
        g_state.state = STATE_ERROR;
        g_state.dirty = 1;
        lws_wsi = NULL;
        break;

    default:
        break;
    }

    return 0;
}

static const struct lws_protocols ws_protocols[] = {
    {
        .name                  = "tanu-ws",
        .callback              = ws_callback,
        .per_session_data_size = sizeof(ws_user_data_t),
        .rx_buffer_size        = WS_RX_BUF_SZ,
    },
    LWS_PROTOCOL_LIST_TERM
};

static void ws_connect(void) {
    if (lws_wsi) return;  /* already connected */

    struct lws_client_connect_info info;
    memset(&info, 0, sizeof(info));

    /* Parse URL */
    const char *url = g_ws_url;
    const char *host = "127.0.0.1";
    int port = 7337;
    const char *path = "/ws/chat";

    /* Simple parse: ws://host:port/path */
    if (strncmp(url, "ws://", 5) == 0) {
        url += 5;
    }
    char hostbuf[128];
    const char *slash = strchr(url, '/');
    if (slash) {
        size_t hlen = (size_t)(slash - url);
        if (hlen >= sizeof(hostbuf)) hlen = sizeof(hostbuf) - 1;
        memcpy(hostbuf, url, hlen);
        hostbuf[hlen] = '\0';
        host = hostbuf;
        path = slash;
        /* Extract port from hostbuf */
        char *colon = strchr(hostbuf, ':');
        if (colon) {
            *colon = '\0';
            port = atoi(colon + 1);
        }
    }

    info.context   = lws_ctx;
    info.address   = host;
    info.port      = port;
    info.path      = path;
    info.host      = host;
    info.origin    = host;
    info.protocol  = ws_protocols[0].name;
    info.pwsi      = &lws_wsi;

    lws_client_connect_via_info(&info);
}

/* ---------------------------------------------------------------------------
 * Animation timer callback
 * ------------------------------------------------------------------------- */

static lv_timer_t *anim_timer;

static void anim_timer_cb(lv_timer_t *timer) {
    (void)timer;
    float dt = ANIM_TICK_MS / 1000.0f;
    g_state.anim_t += dt;
    g_state.dirty = 1;
    update_ui();
    lv_obj_invalidate(scr);
}

/* ---------------------------------------------------------------------------
 * Main
 * ------------------------------------------------------------------------- */

static void print_usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s [OPTIONS]\n"
        "  --ws-url URL    WebSocket server URL (default: ws://127.0.0.1:7337/ws/chat)\n"
        "  --help          Show this help\n",
        prog);
}

int main(int argc, char **argv) {
    /* Parse arguments */
    static struct option long_opts[] = {
        {"ws-url", required_argument, NULL, 'w'},
        {"help",   no_argument,       NULL, 'h'},
        {NULL,     0,                 NULL, 0},
    };
    int opt;
    while ((opt = getopt_long(argc, argv, "w:h", long_opts, NULL)) != -1) {
        switch (opt) {
        case 'w':
            strncpy(g_ws_url, optarg, sizeof(g_ws_url) - 1);
            break;
        case 'h':
            print_usage(argv[0]);
            return 0;
        default:
            print_usage(argv[0]);
            return 1;
        }
    }

    /* Signal handlers */
    signal(SIGINT, sighandler);
    signal(SIGTERM, sighandler);

    /* Initialize LVGL */
    lv_init();

    /* Create fbdev display */
    lv_display_t *disp = lv_linux_fbdev_create();
    if (!disp) {
        fprintf(stderr, "Failed to create LVGL fbdev display\n");
        return 1;
    }
    lv_linux_fbdev_set_file(disp, "/dev/fb0");

    /* Create UI */
    create_ui();

    /* Animation timer (~60 fps) */
    anim_timer = lv_timer_create(anim_timer_cb, ANIM_TICK_MS, NULL);

    /* Initialize libwebsockets */
    struct lws_context_creation_info lws_info;
    memset(&lws_info, 0, sizeof(lws_info));
    lws_info.port = CONTEXT_PORT_NO_LISTEN;
    lws_info.protocols = ws_protocols;
    lws_info.options = LWS_SERVER_OPTION_DO_SSL_GLOBAL_INIT;

    lws_ctx = lws_create_context(&lws_info);
    if (!lws_ctx) {
        fprintf(stderr, "Failed to create libwebsockets context\n");
        return 1;
    }

    printf("Tanu LVGL panel starting...\n");
    printf("  WS URL: %s\n", g_ws_url);
    printf("  Device: /dev/fb0\n");

    /* Initial draw */
    update_ui();
    lv_obj_invalidate(scr);

    /* Main event loop */
    unsigned long last_ws_attempt = 0;
    while (g_running) {
        unsigned long now_ms = (unsigned long)(time(NULL)) * 1000;

        /* Try to reconnect WS if not connected */
        if (!lws_wsi && (now_ms - last_ws_attempt > 3000)) {
            ws_connect();
            last_ws_attempt = now_ms;
        }

        /* Service libwebsockets (non-blocking) */
        lws_service(lws_ctx, 0);

        /* Service LVGL */
        lv_timer_handler();

        usleep(1000);  /* 1ms sleep to avoid busy-wait */
    }

    printf("Tanu LVGL panel shutting down.\n");
    lws_context_destroy(lws_ctx);
    return 0;
}
