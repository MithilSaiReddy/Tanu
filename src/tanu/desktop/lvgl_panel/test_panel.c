/*
 * test_panel.c — Minimal LVGL test for fbdev display.
 * Just shows colored rectangles and text. No GIF, no WebSocket.
 */
#include <lvgl.h>
#include <signal.h>
#include <stdio.h>
#include <unistd.h>

static volatile int g_running = 1;
static void sighandler(int sig) { (void)sig; g_running = 0; }

int main(void) {
    signal(SIGINT, sighandler);
    signal(SIGTERM, sighandler);

    printf("Initializing LVGL...\n");
    lv_init();

    printf("Creating fbdev display...\n");
    lv_display_t *disp = lv_linux_fbdev_create();
    if (!disp) {
        fprintf(stderr, "FATAL: lv_linux_fbdev_create() returned NULL\n");
        return 1;
    }
    lv_linux_fbdev_set_file(disp, "/dev/fb0");

    printf("Creating UI...\n");
    lv_obj_t *scr = lv_screen_active();

    /* Bright red background — impossible to miss */
    lv_obj_set_style_bg_color(scr, lv_color_hex(0xff0000), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    /* Big white text */
    lv_obj_t *label = lv_label_create(scr);
    lv_label_set_text(label, "TANU PANEL OK");
    lv_obj_set_style_text_color(label, lv_color_hex(0xffffff), 0);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_28, 0);
    lv_obj_center(label);

    printf("Main loop...\n");
    fflush(stdout);

    while (g_running) {
        lv_timer_handler();
        usleep(10000); /* 10ms */
    }

    printf("Done.\n");
    return 0;
}
