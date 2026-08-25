/*
 * test_gif2.c — Minimal test: does lv_gif_create work at all?
 */
#include <lvgl.h>
#include <stdio.h>
#include <unistd.h>

LV_IMAGE_DECLARE(gif_character);

int main(void) {
    printf("1. lv_init\n"); fflush(stdout);
    lv_init();

    printf("2. fbdev create\n"); fflush(stdout);
    lv_display_t *disp = lv_linux_fbdev_create();
    lv_linux_fbdev_set_file(disp, "/dev/fb0");
    printf("3. fbdev ready\n"); fflush(stdout);

    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x000000), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    /* Test A: can we create a simple label? */
    printf("4. creating label...\n"); fflush(stdout);
    lv_obj_t *label = lv_label_create(scr);
    lv_label_set_text(label, "GIF TEST");
    lv_obj_set_style_text_color(label, lv_color_hex(0xffffff), 0);
    lv_obj_center(label);
    printf("5. label OK\n"); fflush(stdout);

    /* Refresh display once to show label */
    lv_timer_handler();
    usleep(100000);

    /* Test B: try lv_gif_create */
    printf("6. lv_gif_create...\n"); fflush(stdout);
    fflush(stdout);
    lv_obj_t *gif = lv_gif_create(scr);
    printf("7. lv_gif_create returned: %p\n", (void*)gif); fflush(stdout);

    if (gif) {
        printf("8. lv_gif_set_color_format...\n"); fflush(stdout);
        lv_gif_set_color_format(gif, LV_COLOR_FORMAT_RGB565);
        printf("9. color format set\n"); fflush(stdout);

        printf("10. lv_gif_set_src...\n"); fflush(stdout);
        lv_gif_set_src(gif, &gif_character);
        printf("11. src set\n"); fflush(stdout);

        lv_obj_align(gif, LV_ALIGN_CENTER, 0, 0);
    }

    printf("12. entering loop...\n"); fflush(stdout);

    for (int i = 0; i < 500; i++) {
        lv_timer_handler();
        usleep(10000);
    }

    printf("13. done\n");
    return 0;
}
