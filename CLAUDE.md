# Light Controllers

## Project Purpose

A generic networked LED lighting platform for coordinating lights across any collection of objects. Controllers communicate wirelessly to synchronise lighting behaviour across an entire rig. The initial use case is a live band where lights are mounted on instruments and other objects on stage, but the platform is object-agnostic — object-specific behaviour lives in fixtures and themes, not in the core network or controller logic.

## Hardware

### Controller
- **MCU:** ESP32
- **Wireless protocol:** ESP-NOW (peer-to-peer, no router required, low latency)

### Light Systems
Two mutually exclusive configurations per controller — always one or the other:
- **12v system:** Non-addressable SMD2835 strips, 60 LED/m, ~6–12W/m (MOSFET PWM for intensity)
- **Addressable system:** TBD — existing 5v WS2812b stock vs. moving to 12v WS2811 going forward. Open decision. WS2811 would allow a single 12v supply across all rig types; WS2812b requires separate 5v supply path. Both use same NeoPixel protocol.

Controllers are generic: same PCB/firmware, behavior determined by which power supply and light output is connected.

### Power
- **12v line:** Requires a voltage regulator (e.g., buck converter) to step down to 3.3v for the ESP32
- **12v control:** MOSFET between ESP32 GPIO and LED strip to enable PWM intensity control
- **5v line:** Powers ESP32 and WS2812b directly (with appropriate level shifting if needed)

## Networking / Protocol

All controllers run ESP-NOW and form a peer-to-peer mesh. Key behaviors to support:

- **Handshake/discovery:** Controllers announce themselves and build awareness of the network
- **Solo request:** A controller can request to be the "solo" node; all others dim accordingly
- **Master control:** A designated master node can broadcast pattern/state changes to all rigs
- **State sharing:** Controllers broadcast what they are currently doing so peers can react

## Pin Assignments (ESP32 DevKit V1 38-pin)

| GPIO | Role | Status |
|---|---|---|
| GPIO16 | IRLZ34N gate (PWM, 12v strip control) | Active |
| GPIO25 | Button 1 — next pattern + broadcast to network | Active |
| GPIO26 | Button 2 — soloist signal | Reserved (future) |

- Buttons wired active-low: GPIO → button → GND, internal pull-up enabled
- Avoid GPIO 0, 2, 12 (boot-strapping pins)

## Collaboration

- When the user proposes an approach that conflicts with best practices or has meaningful tradeoffs, push back with a clear argument before proceeding. Don't just implement what's asked if there's a good reason not to.

## Scripts

- Every shell script must have a `-h` flag that prints usage and a description of all flags.
- When adding a new flag to an existing script, update the `-h` output to include it.

## Deployment

- `deploy.sh` is the source of truth for what gets flashed to the ESP32. When new files are added to the repo that need to be deployed, update `deploy.sh` to include them. Do this in bulk at the end of a session, not after each individual file.

## Core Design Rules

- **All light actions must be interruptable at any time.** Patterns must never block — no `sleep()` inside pattern logic. Patterns calculate their output from elapsed time and return immediately. The main loop applies the value, checks inputs, and checks the network on every tick.

## Code

- **Language:** MicroPython
- **WS2812b control:** built-in `neopixel` module
- **12v PWM control:** `machine.PWM`
- **ESP-NOW:** `espnow` module (built into MicroPython ESP32 port)
- HSV color math written in-house (no FastLED equivalent exists for MicroPython)
- Controllers use a unified `LightRig` abstraction so network logic is decoupled from light type

## Long-Term Roadmap (not immediate priority)

- **Art-Net integration:** Allow a master node (or bridge device) to receive Art-Net DMX-over-IP from professional lighting consoles, translating to ESP-NOW commands across the rig network. Keep protocol boundaries clean so this layer can be added without restructuring the core network.
