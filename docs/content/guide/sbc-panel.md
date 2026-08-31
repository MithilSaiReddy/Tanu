# SBC Panel Mode (SPI TFT)

Run Tanu's face directly on a small SPI TFT panel — no X11/Wayland, no
desktop environment. Tested layout target: **ILI9341 320x240** on a
Radxa Cubie A7Z-class board, but any Linux framebuffer panel works.

```
SPI panel → kernel fb driver → /dev/fb0 → Tanu face (Python + Pillow)
I2S mic + amp ──────────────────────────→ Tanu voice mode (input)
```

The panel is a **pure-Python** driver: Pillow composites each frame and
writes RGB565 into the mapped framebuffer. No C, no LVGL, no build step.

## 1. How it works

| Mode | Command | Output |
|------|---------|--------|
| Normal (no args) | `python3 main.py` | Voice assistant (simulate: type text, it speaks) + face on `/dev/fb0` |
| Voice + panel | `python3 main.py tanu --simulate` | Type text → Tanu speaks it, face on `/dev/fb0` |
| Chat + panel | `python3 main.py desk` | Chat server :7337 + panel (auto panel if `/dev/fb0` present) |
| Window (dev box) | `python3 main.py desk` | 400x400 desktop window (Pygame, no `/dev/fb0`) |

Display selection is **auto**: the panel is used whenever a usable `/dev/fb0`
is present (the SBC), otherwise it falls back to the Pygame window (desktop).
In panel/voice mode the keyboard-dependent input row disappears — the UI shows
the animated character, a status line, and a scrolling response ticker.
Voice is the input (see §5).

Config lives under `ui` in `~/.tanu/config.json` (defaults shown):

```json
{
  "ui": {
    "display": "auto",
    "panel": {
      "device": "/dev/fb0",
      "width": 320,
      "height": 240,
      "fps": 24,
      "speed": 1.0,
      "rotation": 0,
      "vsync": false,
      "show_fps": false,
      "driver": "fbdev"
    }
  }
}
```

- `driver` is always `"fbdev"` (pure-Python, Pillow → `/dev/fb0`).
- `rotation` (`0/90/180/270`) rotates the rendered frame before writing.
- `speed` (default `1.0`) multiplies the face-animation playback rate. Set
  `> 1` to play faster (e.g. `2.0` = twice as fast); the animation loops. The
  render pipeline is fast enough for 100+ fps on the low-level bulk write path,
  so raising `speed` up to ~4 keeps playback smooth.
- `vsync` (default `false`) — if `true`, tries to enable double buffering via
  `FBIOPAN_DISPLAY` when the fb driver advertises `yres_virtual >= 2*yres`.
  This pans between two pages for tear-free updates; falls back silently to
  single buffering if the driver can't honour it.
- `show_fps` (default `false`) — if `true`, logs the measured panel frame rate
  every 5 s to tune `speed`/`fps` against the real display.
- `"display"` (`auto`/`window`/`panel`) — `auto` (default) selects the panel
  when `/dev/fb0` is usable; set `"panel"` to force it, `"window"` to force
  the Pygame window.

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
                spi-max-frequency = <64000000>;
                rotate = <90>;
                bgr;
                fps = <60>;
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

#### Hitting a smooth 60 fps (important)

`fps = <60>` alone does **not** guarantee 60 frames/second. The visible
refresh rate is capped by the SPI bus bandwidth: a full 320x240 RGB565
frame is 153,600 bytes = 1,228,800 bits, so

- 32 MHz SPI  → ~26 fps (default — this is why it looks slow)
- 64 MHz SPI  → ~38–48 fps
- ~73.7 MHz   → ~60 fps (physical max for full-frame updates)

`fps` only tells the driver how often to *attempt* a redraw; the data still
has to cross the SPI bus. To make the panel actually smooth, tune **both**
`spi-max-frequency` and `fps` (the example above uses 64 MHz / 60):

1. Apply the overlay and reboot, then confirm the driver accepted the clock:
   `dmesg | grep -i ili9341`.
2. If the panel "scrambles" / shows rainbow noise, back the SPI clock down a
   step (e.g. `<50000000>` then `<40000000>`) — the max stable rate is board
   and panel dependent. A solid 40–50 fps already looks far smoother than 26.
3. Raise `ui.panel.speed` in `~/.tanu/config.json` (see §1) so the face motion
   moves fast enough to be noticed at the higher refresh rate.

Note: display refresh smooths each *screen update*; `ui.panel.speed` controls
how fast the *face animates* — the two are independent. Tune both.

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

## 4. Run the panel

### Prerequisites (install once on the board)

```bash
sudo apt install python3 python3-venv python3-pil     # python3-pil or pip pillow

python3 -m venv /opt/tanu/lvenv
source /opt/tanu/lvenv/bin/activate
pip install Pillow numpy websocket-client
```

### Run

On the board the simplest start is the **normal run** — it auto-detects
`/dev/fb0` and drives the panel while letting you talk to Tanu by typing
(which it speaks through the speaker):

```bash
python3 main.py
```

Equivalent explicit commands:

```bash
python3 main.py tanu --simulate   # voice assistant: type text -> speaks it, face on panel
python3 main.py desk              # chat server :7337 + panel (auto panel)
```

Your user needs read/write access to `/dev/fb0`:

```bash
sudo usermod -aG video $USER   # then log out/in
```

### Troubleshooting — "Panel framebuffer /dev/fb0 not found"

The fbtft/ili9341 kernel driver isn't loaded (see §3), or the panel isn't
showing `/dev/fb0`. Confirm with `ls -l /dev/fb0` and `dmesg | grep -i fb0`.

## 5. SDL sanity check (pygame window only)

The default `desk` window uses Pygame. To verify it can run headless via
the framebuffer (legacy `fbcon`):

```bash
SDL_VIDEODRIVER=fbcon SDL_FBDEV=/dev/fb0 \
  python3 -c "import pygame; pygame.init(); s=pygame.display.set_mode((320,240)); print('fb OK', s.get_size())"
```

!!! warning "Wheel lacks fbcon?"
    If this fails with "No available video device", the bundled SDL was
    built without framebuffer support. The pure-Python `fbdev` panel
    (§1–4) does **not** need SDL, so prefer `desk --panel` on the SBC.

## 6. Audio (mic + speaker over I2S)

Tanu's voice stack handles wake word, STT, and TTS — the panel just shows
state. Wire an I2S MEMS mic (e.g. INMP441) and I2S DAC/amp (e.g.
MAX98357A) to the matching I2S pins, enable the sound overlays for your
board, then confirm capture/playback:

```bash
arecord -D hw:1,0 -f S16_LE -r 16000 -d 2 test.wav && aplay test.wav
```

Configure the devices in `config.json` (`tanu` / `deskbot` sections) as
usual for voice mode (`python3 main.py tanu`).

## 7. Running everything

On the board, one process handles voice+panel+speaker:

```bash
# Normal run — voice assistant (simulate): type text -> Tanu speaks it,
# face + status animated on the TFT panel
python3 main.py
```

If you want the mic-driven voice assistant (wake word, real STT) instead of
typing, drop `--simulate` and enable wake word in config:

```bash
# Voice brain + panel face (mic, TTS, wakeword)
python3 main.py tanu
```

A purely-visual `desk` chat panel (server :7337 + panel, no speaker) is still
available with `python3 main.py desk`.

### systemd unit template

```ini
# /etc/systemd/system/tanu-panel.service
[Unit]
Description=Tanu panel UI
After=multi-user.target

[Service]
User=YOUR_USER
WorkingDirectory=/opt/tanu
ExecStart=/opt/tanu/lvenv/bin/python main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 8. Physical buttons (future)

Neither the Python panel nor Pygame talks GPIO natively — the plan is a
small `gpiod` watcher thread that posts events into the running UI
(push-to-talk, dismiss error, etc.). Not implemented yet.

## Architecture notes

The pure-Python panel is a small module, `src/tanu/desktop/fbdev_panel.py`:

1. Maps `/dev/fb0` and reads its resolution/pitch via fbdev ioctls.
2. Loads the pre-rendered face frames from `src/tanu/assets/idle/frame_*.png`.
3. Runs a throttled render thread at `fps`, compositing the current face
   frame with a status line and response ticker, and writing RGB565.
4. Connects to the Tanu aiohttp WebSocket server (`/ws/chat`) via
   `WSClient` and maps events (`state`, `token`, `response`, `done`,
   `error`, `tool_*`) onto the display states.

The Python backend (aiohttp server on `:7337`) is unchanged — it handles
AI inference, tools, and voice processing. The panel is just a rendering
client, running in the same process.

```
┌─────────────────────────────┐     ┌──────────────────────┐
│  Python backend (CPython)   │     │  FbdevPanel (Python) │
│  aiohttp :7337             │◄────│  Pillow → RGB565     │
│  /ws/chat                  │ WS  │  → /dev/fb0 (fbtft)  │
│  face state machine        │     │                      │
└─────────────────────────────┘     └──────────────────────┘
```
