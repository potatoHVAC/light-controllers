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
- **Main control:** A designated main node can broadcast pattern/state changes to all rigs
- **State sharing:** Controllers broadcast what they are currently doing so peers can react

### Scale targets

- **Unmanaged mesh (no main):** Design to support up to 200 controllers. Network decisions — traffic patterns, buffer sizing, jitter strategies — should hold up at this scale.
- **Main-controlled:** Design to support up to 10,000 controllers when a main controller is present. The main architecture must account for this scale from the start; retrofitting it later is not acceptable.

## Pin Assignments (ESP32 DevKit V1 38-pin)

| GPIO | Role | Status |
|---|---|---|
| GPIO22 | WS2812b strip 2 data | Active |
| GPIO26 | WS2812b strip 1 data | Active |
| GPIO27 | Button 2 — soloist signal | Reserved (future) |
| GPIO33 | Button 1 — next scene + broadcast to network | Active |

- Buttons wired active-low: GPIO → button → GND, internal pull-up enabled
- Avoid GPIO 0, 2, 12 (boot-strapping pins)

## Collaboration

- Review all code, comments, and documentation for cultural sensitivity before writing. Avoid terms with historical exclusionary connotations (e.g. main/follower instead of master/slave, allowlist/blocklist instead of whitelist/blacklist).


- When the user proposes an approach that conflicts with best practices or has meaningful tradeoffs, push back with a clear argument before proceeding. Don't just implement what's asked if there's a good reason not to.
- After completing work, check the Upcoming Work section and remove any items that were just addressed.


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

## Upcoming Work

- **OTA updates:** Push firmware to all controllers over WiFi rather than physical deployment. Significant time saver at scale.
- **Brightness as a packet field:** Brightness is a network-level decision, not an individual controller setting. The mesh packet should carry a brightness value that all controllers apply uniformly. Not a per-device override.

## Long-Term Roadmap (not immediate priority)

- **Art-Net integration:** Allow a main node (or bridge device) to receive Art-Net DMX-over-IP from professional lighting consoles, translating to ESP-NOW commands across the rig network. Keep protocol boundaries clean so this layer can be added without restructuring the core network.

- **Main controller:** A main always wins — its commands override any controller-initiated state. The main is open to requests from individual controllers but decides whether to relay them to the network. Controllers have tiers of authority; the main grants or ignores override requests based on tier. Individual controllers must never need to know about the hierarchy — they just receive and apply state. The `type` field in the mesh packet and the `apply_state` interface on the controller are the designed extension points for this.

- **Bridge architecture:** At 10,000-unit scale the main speaks a higher-level protocol (Art-Net, OSC, or custom TCP/IP) to bridge nodes, each of which manages a zone of up to ~200 controllers over ESP-NOW. Controllers are unaware they are in a zone — same firmware, same mesh code throughout.

- **Web/phone configuration interface:** ESP32 hosts a WiFi access point for show-day adjustments without redeployment. Must be secured so audience members cannot interfere — authentication required, ideally with role-based access so a band member cannot accidentally trigger main-level overrides.

- **Beat-sync patterns:** Patterns that accept BPM as a parameter and pulse on the beat. BPM set manually or broadcast from the main controller.

- **Error mode display:** Use the addressable strips themselves as the error indicator. On network failure, boot failure, or other fault conditions, display a distinct error pattern on the strips rather than a separate status LED.
