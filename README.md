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
