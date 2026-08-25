/*
 * test_gif.c — Test LVGL GIF loading on fbdev.
 * Shows red background + status text, then tries to load a GIF.
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

    lv_init();

    lv_display_t *disp = lv_linux_fbdev_create();
    if (!disp) { fprintf(stderr, "FATAL: no display\n"); return 1; }
    lv_linux_fbdev_set_file(disp, "/dev/fb0");

    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x14141f), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    /* Status label */
    lv_obj_t *label = lv_label_create(scr);
    lv_label_set_text(label, "Loading GIF...");
    lv_obj_set_style_text_color(label, lv_color_hex(0x00ff00), 0);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_14, 0);
    lv_obj_align(label, LV_ALIGN_TOP_LEFT, 4, 4);

    /* Try to load GIF */
    printf("Attempting to load S:character.gif ...\n");
    fflush(stdout);

    lv_obj_t *gif = lv_gif_create(scr);
    if (!gif) {
        printf("ERROR: lv_gif_create() returned NULL\n");
        lv_label_set_text(label, "GIF: create failed");
    } else {
        lv_gif_set_color_format(gif, LV_COLOR_FORMAT_RGB565);
        lv_result_t res = lv_gif_set_src(gif, "S:character.gif");
        printf("lv_gif_set_src returned: %d\n", res);
        fflush(stdout);

        if (res != LV_RESULT_OK) {
            printf("ERROR: lv_gif_set_src failed (res=%d)\n", res);
            lv_label_set_text(label, "GIF: load failed");
        } else {
            lv_obj_align(gif, LV_ALIGN_CENTER, 0, 0);
            lv_label_set_text(label, "GIF loaded OK");
        }
    }

    /* Also test: can we open the file directly? */
    lv_fs_file_t f;
    lv_fs_res_t fres = lv_fs_open(&f, "S:character.gif", LV_FS_MODE_RD);
    printf("lv_fs_open S:character.gif = %d (0=OK)\n", fres);
    if (fres == LV_FS_RES_OK) {
        uint8_t buf[16];
        uint32_t br;
        lv_fs_read(&f, buf, 16, &br);
        printf("First bytes: ");
        for (uint32_t i = 0; i < br; i++) printf("%02x ", buf[i]);
        printf("\n");
        lv_fs_close(&f);
    }

    lv_obj_invalidate(scr);
    fflush(stdout);

    while (g_running) {
        lv_timer_handler();
        usleep(10000);
    }
    return 0;
}
