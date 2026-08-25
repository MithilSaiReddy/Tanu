# SBC Panel Mode (SPI TFT)

Run Tanu's face directly on a small SPI TFT panel — no X11/Wayland, no
desktop environment. Tested layout target: **ILI9341 320x240** on a
Radxa Cubie A7Z-class board, but any Linux framebuffer panel works.

```
SPI panel → kernel fb driver → /dev/fb0 → SDL2 (fbcon) → Tanu Pygame UI
I2S mic + amp ─────────────────────────→ Tanu voice mode (input)
```

## 1. How it works

| Mode | Command | Output |
|------|---------|--------|
| Window (default) | `python3 main.py desk` | 400x400 desktop window |
| Panel | `python3 main.py desk --panel` | Direct to `/dev/fb0` |

In panel mode the keyboard-dependent input row disappears — the UI shows
the animated character, connection/status line, and a scrolling ticker
with the latest response. Voice is the input (see §5).

Config lives under `ui` in `~/.tanu/config.json` (defaults shown):

```json
{
  "ui": {
    "display": "window",
    "panel": {
      "device": "/dev/fb0",
      "width": 320,
      "height": 240,
      "fps": 24,
      "rotation": 0
    }
  }
}
```

Set `"display": "panel"` to make `desk` use the panel without the flag.
`width`/`height` are the *logical* size you want to draw in; set
`rotation` to 90/270 only if the framebuffer itself is portrait and the
kernel isn't already rotating (software rotation costs a blit per frame).

## 2. Panel wiring (ILI9341 → SBC header)

Typical ILI9341 module pins:

| Module pin | SoC signal |
|------------|------------|
| VCC        | 3.3V       |
| GND        | GND        |
| CS         | SPI0 CS0   |
| RESET      | free GPIO  |
| DC/RS      | free GPIO  |
| SDI/MOSI   | SPI0 MOSI  |
| SCK        | SPI0 SCLK  |
| LED        | 3.3V (or PWM GPIO for dimming) |
| SDO/MISO   | SPI0 MISO (optional) |

Pin numbers differ per board — confirm against the Radxa Cubie A7Z pinout
(`radxa pinout` or the hardware docs page) before wiring.

## 3. Kernel framebuffer setup

The goal is a `/dev/fb0` node driven at your panel's resolution.

### Option A — fbtft overlay (simplest)

Most Armbian/mainline kernels ship the `fbtft` staging drivers. Create
`ili9341-fb.dts` (adjust GPIO numbers/spi bus to your board):

```dts
/dts-v1/;
/plugin/;

/ {
    compatible = "allwinner,sun50i-*";

    fragment@0 {
        target = <&spi0>;
        __overlay__ {
            status = "okay";
            pinctrl-names = "default";
            pinctrl-0 = <&spi0_pins>, <&spi0_cs0_pin>;

            ili9341: ili9341@0 {
                compatible = "ilitek,ili9341";
                reg = <0>;
                spi-max-frequency = <32000000>;
                rotate = <90>;
                bgr;
                fps = <30>;
                buswidth = <8>;
                dc-gpios = <&pio 1 3 0>;    /* PB3 - change me */
                reset-gpios = <&pio 1 2 0>; /* PB2 - change me */
                led-gpios = <&pio 1 4 0>;   /* PB4 - change me (optional) */
                debug = <0>;
            };
        };
    };
};
```

Apply and load:

```bash
sudo armbian-add-overlay ili9341-fb.dts     # Armbian images
sudo reboot
dmesg | grep -iE "ili9341|fb_ili9341|fb0"
ls -l /dev/fb0
```

If your image doesn't have `armbian-add-overlay`, compile with
`dtc -@ -I dts -O dtb -o ili9341-fb.dtbo ili9341-fb.dts` and add an
`overlays=` entry referencing it in boot config (image-specific).

### Option B — panel-mipi-dbi-spi (mainline DRM)

Newer alternative without fbtft: the `panel-mipi-dbi-spi` driver takes a
small firmware file containing the panel's init sequence. Generate it
from your controller's init table with the `mipi-dbi-cmd` tool, then add
a DT node with `compatible = "panel-mipi-dbi-spi"`. More setup, cleaner
long-term. See the kernel docs
(`Documentation/devicetree/bindings/display/panel/panel-mipi-dbi-spi.yaml`).

### Verify the framebuffer

```bash
cat /dev/urandom > /dev/fb0   # static noise on the panel = working
```

## 4. SDL sanity check

The pip pygame-ce wheel must include SDL's fbcon video driver:

```bash
SDL_VIDEODRIVER=fbcon SDL_FBDEV=/dev/fb0 \
  python3 -c "import pygame; pygame.init(); s=pygame.display.set_mode((320,240)); print('fb OK', s.get_size())"
```

!!! warning "Wheel lacks fbcon?"
    If this fails with "No available video device", the bundled SDL was
    built without framebuffer support. Fix: install the distro pygame
    into the venv instead:

    ```bash
    sudo apt install python3-pygame libsdl2-2.0-0
    deactivate
    python3 -m venv venv --system-site-packages   # recreate venv
    source venv/bin/activate && pip install -r requirements.txt
    ```

## 5. Audio (mic + speaker over I2S)

Tanu's voice stack handles wake word, STT, and TTS — the panel just shows
state. Wire an I2S MEMS mic (e.g. INMP441) and I2S DAC/amp (e.g.
MAX98357A) to the matching I2S pins, enable the sound overlays for your
board, then confirm capture/playback:

```bash
arecord -D hw:1,0 -f S16_LE -r 16000 -d 2 test.wav && aplay test.wav
```

Configure the devices in `config.json` (`tanu` / `deskbot` sections) as
usual for voice mode (`python3 main.py tanu`).

## 6. Running everything

```bash
# Terminal/service 1 — voice brain (mic, TTS, wakeword)
python3 main.py tanu

# Terminal/service 2 — panel face (spawns chat server on :7337)
python3 main.py desk --panel
```

### systemd unit template

```ini
# /etc/systemd/system/tanu-panel.service
[Unit]
Description=Tanu panel UI
After=multi-user.target

[Service]
User=YOUR_USER
WorkingDirectory=/opt/tanu
Environment=SDL_NOMOUSE=1
ExecStart=/opt/tanu/venv/bin/python main.py desk --panel
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 7. Physical buttons (future)

Neither pygame nor LVGL talks GPIO natively — the plan is identical
either way: a small `gpiod` watcher thread posts synthetic
`pygame.KEYDOWN` events into the running UI (push-to-talk, dismiss
error, etc.). Not implemented yet; the event loop in
`src/tanu/desktop/app.py` is the integration point.
