# SBC Panel Mode (SPI TFT)

Run Tanu's face directly on a small SPI TFT panel — no X11/Wayland, no
desktop environment. Tested layout target: **ILI9341 320x240** on a
Radxa Cubie A7Z-class board, but any Linux framebuffer panel works.

```
SPI panel → kernel fb driver → /dev/fb0 → LVGL (C binary) → Tanu UI
I2S mic + amp ──────────────────────────→ Tanu voice mode (input)
```

## 1. How it works

| Mode | Command | Output |
|------|---------|--------|
| Window (default) | `python3 main.py desk` | 400x400 desktop window |
| Panel (LVGL) | `python3 main.py desk --panel` | Direct to `/dev/fb0` via LVGL |
| Panel (Pygame) | `python3 main.py desk --panel` | Direct to `/dev/fb0` via SDL fbcon |

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
      "rotation": 0,
      "driver": "lvgl"
    }
  }
}
```

- **`driver`**: `"lvgl"` (default) uses the native LVGL C binary for
  rendering. `"pygame"` uses SDL fbcon (requires SDL with fbcon support).
- Set `"display": "panel"` to make `desk` use the panel without the flag.
- `rotation` is only used by the Pygame driver; LVGL handles rotation
  via the kernel/fbtft overlay.

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

## 4. Build the LVGL panel binary

The LVGL panel client is a native C binary that renders directly to
`/dev/fb0` using LVGL's fbdev driver and connects to the Tanu server
via WebSocket (libwebsockets).

### Prerequisites (install once on the board)

```bash
sudo apt install \
    build-essential cmake ninja-build python3 python3-venv \
    libevdev-dev libwebsockets-dev

python3 -m venv /opt/tanu/lvenv
source /opt/tanu/lvenv/bin/activate
pip install kconfiglib pcpp
```

### Build

From the Tanu project root (on the board):

```bash
chmod +x build_panel.sh
./build_panel.sh
```

This will:
1. Clone `lv_port_linux` to `/opt/tanu/lv_port_linux/` (if not present)
2. Build LVGL with fbdev-only configuration
3. Build `tanu_panel` and install it to `/usr/local/bin/`

### Manual build (if build_panel.sh doesn't work)

```bash
# Clone LVGL Linux port
cd /opt/tanu
git clone --recurse-submodules https://github.com/lvgl/lv_port_linux.git
cd lv_port_linux

# Configure for fbdev
cat > .config << 'EOF'
CONFIG_LV_USE_LINUX_FBDEV=y
CONFIG_LV_USE_SDL=n
CONFIG_LV_USE_WAYLAND=n
CONFIG_LV_USE_X11=n
CONFIG_LV_COLOR_DEPTH_16=y
CONFIG_LV_FONT_MONTSERRAT_14=y
CONFIG_LV_FONT_MONTSERRAT_20=y
CONFIG_LV_FONT_DEFAULT_MONTSERRAT_20=y
EOF

cmake -B build -GNinja -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)

# Build tanu_panel
cd /opt/tanu
mkdir -p tanu_panel_build && cd tanu_panel_build
cmake /opt/tanu/src/Tanu/src/tanu/desktop/lvgl_panel \
    -DLVGL_DIR=/opt/tanu/lv_port_linux \
    -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)
sudo cp tanu_panel /usr/local/bin/
```

### Test the binary

```bash
LV_LINUX_FBDEV_DEVICE=/dev/fb0 tanu_panel --ws-url ws://127.0.0.1:7337/ws/chat
```

You should see the Tanu face rendered on the panel.

## 5. SDL sanity check (pygame driver only)

If using `"driver": "pygame"`, the pip pygame-ce wheel must include
SDL's fbcon video driver:

```bash
SDL_VIDEODRIVER=fbcon SDL_FBDEV=/dev/fb0 \
  python3 -c "import pygame; pygame.init(); s=pygame.display.set_mode((320,240)); print('fb OK', s.get_size())"
```

!!! warning "Wheel lacks fbcon?"
    If this fails with "No available video device", the bundled SDL was
    built without framebuffer support. Either:
    - Switch to `"driver": "lvgl"` (recommended), or
    - Install the distro pygame into the venv instead:

    ```bash
    sudo apt install python3-pygame libsdl2-2.0-0
    deactivate
    python3 -m venv venv --system-site-packages   # recreate venv
    source venv/bin/activate && pip install -r requirements.txt
    ```

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
Description=Tanu panel UI (LVGL)
After=multi-user.target

[Service]
User=YOUR_USER
WorkingDirectory=/opt/tanu
Environment=LV_LINUX_FBDEV_DEVICE=/dev/fb0
ExecStart=/usr/local/bin/tanu_panel --ws-url ws://127.0.0.1:7337/ws/chat
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Or, using the Python launcher (which starts the server + LVGL binary):

```ini
# /etc/systemd/system/tanu-panel.service
[Unit]
Description=Tanu panel UI
After=multi-user.target

[Service]
User=YOUR_USER
WorkingDirectory=/opt/tanu
ExecStart=/opt/tanu/venv/bin/python main.py desk --panel
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 8. Physical buttons (future)

Neither LVGL nor pygame talks GPIO natively — the plan is identical
either way: a small `gpiod` watcher thread posts events into the running
UI (push-to-talk, dismiss error, etc.). Not implemented yet.

## Architecture notes

The LVGL panel binary (`tanu_panel`) is a standalone C program that:

1. Initializes LVGL and creates a fbdev display targeting `/dev/fb0`
2. Renders the Tanu face canvas (idle/listening/thinking/speaking/error
   states), status bar, and response ticker using LVGL widgets
3. Connects to the Tanu aiohttp WebSocket server via libwebsockets
4. Parses incoming JSON messages and updates the UI accordingly
5. Runs an animation loop at ~60 fps for face state transitions

The Python backend (aiohttp server on `:7337`) is unchanged — it still
runs on CPython and handles AI inference, tools, and voice processing.
The LVGL binary is just a rendering client.

```
┌─────────────────────────────┐     ┌──────────────────────┐
│  Python backend (CPython)   │     │  tanu_panel (C)      │
│  aiohttp :7337             │◄────│  LVGL + fbdev        │
│  /ws/chat                  │ WS  │  libwebsockets       │
│  face state machine        │     │  → /dev/fb0          │
└─────────────────────────────┘     └──────────────────────┘
```
