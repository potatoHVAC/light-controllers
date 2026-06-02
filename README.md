# Light Controllers

## Deploying to ESP32

### Flash MicroPython firmware (once per board)

Download the latest firmware from [micropython.org/download/ESP32_GENERIC](https://micropython.org/download/ESP32_GENERIC/), then:

Replace `<port>` with your port (`/dev/ttyUSB0` on Linux, `/dev/tty.usbserial-*` on Mac, `COM3` on Windows).

```bash
./flash_firmware.sh <port> <firmware.bin>
```

### Upload files

```bash
pipx install mpremote
./deploy.sh <port>
```

---

## OTA Updates

Once controllers are deployed you can push firmware updates over WiFi without plugging anything in.

### Requirements

- Docker
- A laptop with a WiFi adapter

### First-time credentials setup

Create a secrets.py file using the secrets.py.example

### Start the hotspot

Find your WiFi interface name:

```bash
ip link show
```

Look for a name starting with `wl` (e.g. `wlp3s0`). Then start the hotspot:

```bash
./hotspot.sh <interface>
```

Credentials are read from `.env`. The hotspot stays up until you disconnect it or reboot.

### Pushing an update

Start the OTA server:

```bash
./server/run.sh
```

Open [http://localhost:8080](http://localhost:8080) to see the update log.

To update a controller:

1. Hold the button while powering it on
2. Keep holding for **3 seconds**
3. The controller connects to the hotspot, downloads all files, and restarts automatically

Update multiple controllers by holding the button on each one during power-on. They update independently and can all be done at the same time.

---

## Show Control Panel

The first controller to boot with no others running automatically becomes the **leader**. The leader connects to the show control hotspot and bridges the ESP-NOW mesh to the laptop server.

### Setup

Start a second hotspot for show control (credentials from `.env`):

```bash
./hotspot.sh <interface>
```

> If you need both OTA and show control active at the same time, use two WiFi adapters or a phone for one of the hotspots.

Start the server (also handles OTA):

```bash
./server/run.sh
```

### Using the panel

Once the leader controller connects, open [http://localhost:8080/panel](http://localhost:8080/panel) in a browser or on your phone.

The panel provides:
- Current theme, scene, and dim level
- Next Scene / Next Theme buttons
- Random Scene — each controller picks independently
- Solo toggle
- Dim slider

The leader is elected automatically. If the leader controller goes offline, another controller takes over within 10 seconds.

---

## Tests

The suite runs under CPython — the MicroPython hardware modules (`machine`,
`neopixel`, `network`, `espnow`, `uhashlib`, `ubinascii`) are replaced with
fakes, and `time` is driven by a controllable clock. Integration tests build
real `Controller` + `Mesh` + `Fixture` + `Strip` instances and run them against
an in-memory, channel-aware mesh bus, so multiple controllers are simulated in
one process.

### Running

```bash
python3 -m pip install -r tests/requirements.txt   # one-time (needs pytest)
./tests/run.sh
```

Pass extra arguments straight through to pytest:

```bash
./tests/run.sh -k election     # only tests matching "election"
./tests/run.sh tests/unit      # only the unit tests
./tests/run.sh -v              # verbose
```

### Layout

- `tests/fakes/` — fake hardware modules and the shared radio **bus** (models
  ESP-NOW only reaching peers on the same WiFi channel).
- `tests/harness.py` — the clock and the multi-node `Simulation`.
- `tests/conftest.py` — installs the fakes before any controller code imports.
- `tests/unit/` — pure logic: color math, the HMAC cross-runtime contract,
  button debounce, strip dim scaling, storage, themes, mesh dedup/channel,
  bridge auth.
- `tests/integration/` — leader election, scene/theme propagation, solo,
  channel convergence across simulated controllers.

No hardware is required. Anything that can only be checked on a real ESP32
(actual ESP-NOW range, NeoPixel timing, flash, GC) is intentionally out of scope.

---

## Wiring Diagram

### 12v Non-Addressable LED Strip (SMD2835)

```
12V SUPPLY
    (+) ──────────┬────────────────────────────→ LED Strip (+)
                  │
            ┌─────┴──────┐
            │  LM2596    │
            │  IN+   OUT+│──→ ESP32 VIN
            │  IN-   OUT-│──→ GND
            └─────┬──────┘
                  │
    (-) ──────────┴─────────────────────────── GND (common)

ESP32
    VIN    ←── LM2596 OUT+ (5v)
    GND    ←── common GND
    GPIO16 ──→ 100Ω ──┬──→ IRLZ34N Gate
                      │
                     10kΩ
                      │
                     GND
    GPIO25 ──── Button ──── GND   (next pattern + broadcast)
    GPIO26      [RESERVED: future soloist button]

IRLZ34N
    Gate   ←── 100Ω ←── GPIO16
    Drain  ←── LED Strip (-)
    Source ──→ GND
```

### Notes

- Set LM2596 output to **5v** before connecting ESP32 (measure with multimeter, adjust trimmer pot)
- Buttons are active-low: GPIO reads LOW when pressed, internal pull-up enabled in firmware
- All GNDs tied to a common ground
- LED strip power runs parallel to the controller — no LED current flows through the ESP32

### Components

| Component | Part | Qty |
|---|---|---|
| Microcontroller | ESP32 DevKit V1 (38-pin) | 1 |
| Buck converter | LM2596 module (adjustable) | 1 |
| MOSFET | IRLZ34N | 1 |
| Resistor | 100Ω | 1 |
| Resistor | 10kΩ | 1 |
| Button | Momentary pushbutton (NO) | 1 |
