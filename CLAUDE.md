# Light Controllers

## Laws — Never Break These

These rules have no exceptions. They override all other instructions.

- **Never commit plaintext passwords, keys, tokens, or secrets to the repository.** All credentials belong in untracked files (`secrets.py`, `.env`) or encrypted secret stores. Never use hardcoded credential fallbacks — if a secrets file is missing, fail loudly with a clear error. Before writing any credential to a file, verify that file is in `.gitignore`. Scan changed files for credential patterns before every commit.

- **No blocking during normal operation.** The main loop must never block — no `sleep()`, no polling loops, no waiting on I/O. All long-running operations (WiFi connection, discovery, OTA) must be implemented as non-blocking state machines that advance one step per tick and return immediately. Blocking is only permitted during one-shot startup operations before the main loop begins (e.g., the A/B swap, the initial boot sequence), and for a single WiFi scan (`sta.scan()`, ~2s — no async API exists) at the discrete moment a controller connects to or recovers a hotspot: only the leader scans on connect, and only a freshly-booted or orphaned controller scans on recovery. Steady-state controllers never scan.


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
- If the user has manually edited a file, re-read it before touching it and flag what they changed. Never silently overwrite user edits. If an improvement is worth making to user-written code, raise it as a suggestion rather than just doing it.


## Scripts

- Every shell script must have a `-h` flag that prints usage and a description of all flags.
- When adding a new flag to an existing script, update the `-h` output to include it.

## Deployment

- `deploy.sh` is the source of truth for what gets flashed to the ESP32. When new files are added to the repo that need to be deployed, update `deploy.sh` to include them. Do this in bulk at the end of a session, not after each individual file.

## Core Design Rules

- **All light actions must be interruptable at any time.** Patterns must never block — no `sleep()` inside pattern logic. Patterns calculate their output from elapsed time and return immediately. The main loop applies the value, checks inputs, and checks the network on every tick.

- **Patterns must only write to strips via the public API** — `strip[i]`, `strip.fill()`, `strip.draw_pulse()`. Never access `strip._np` directly. The strip maintains a separate unscaled buffer so network dim scaling is applied once at show() time without compounding across ticks. Bypassing the public API breaks this.

- **The main loop must feed the hardware watchdog every iteration.** A stalled tick resets the chip (`WDT_TIMEOUT_MS`, ~8s). Any in-loop operation that can block longer than the timeout must feed the watchdog itself — the OTA download does this via a `feed` callback. The loop body is wrapped so a transient per-tick exception is logged and skipped; a persistent run of errors or a fatal error shows a small dim fault marker (first few LEDs at ~10% red) and resets rather than dropping to a dark REPL on stage. Keep any failure indicator small and dim — never blast a full strip at full brightness.

## Code

- **Language:** MicroPython
- **WS2812b control:** built-in `neopixel` module
- **12v PWM control:** `machine.PWM`
- **ESP-NOW:** `espnow` module (built into MicroPython ESP32 port)
- HSV color math written in-house (no FastLED equivalent exists for MicroPython)
- Controllers use a unified `LightRig` abstraction so network logic is decoupled from light type

## Long-Term Roadmap (not immediate priority)

- **Art-Net integration:** Allow a main node (or bridge device) to receive Art-Net DMX-over-IP from professional lighting consoles, translating to ESP-NOW commands across the rig network. Keep protocol boundaries clean so this layer can be added without restructuring the core network.

- **Leader / authority hierarchy:** The elected leader (bridge controller) is the current coordinator but has no authority over other controllers beyond what the mesh protocol provides. A future "authority" layer would allow a designated controller — or the laptop server via the bridge — to issue commands that all controllers must obey regardless of local button presses. This is distinct from the elected leader; the authority could be the server itself. The `type` field in the mesh packet and `apply_state` are the designed extension points.

- **Bridge architecture:** At 10,000-unit scale the main speaks a higher-level protocol (Art-Net, OSC, or custom TCP/IP) to bridge nodes, each of which manages a zone of up to ~200 controllers over ESP-NOW. Controllers are unaware they are in a zone — same firmware, same mesh code throughout.

- **Web/phone configuration interface:** ESP32 hosts a WiFi access point for show-day adjustments without redeployment. Must be secured so audience members cannot interfere — authentication required, ideally with role-based access so a band member cannot accidentally trigger main-level overrides.

- **Beat-sync patterns:** Patterns that accept BPM as a parameter and pulse on the beat. BPM set manually or broadcast from the main controller.

- **OTA versioning:** Add a version field to the OTA manifest. Controllers compare against a locally stored version and skip the download if already up to date.

- **Error mode display:** Use the addressable strips themselves as the error indicator. On network failure, boot failure, or other fault conditions, display a distinct error pattern on the strips rather than a separate status LED.

- **Per-member fixture configs:** Each band member has a custom config (strip lengths, pattern tuning) sized to their instrument. Stored in the server database alongside member metadata (name, instrument, role, grouping tags like "drummers" or "horns"). Used for quick controller swap-outs and for group commands — e.g. dim all horns, solo all drummers. Each member config includes a default scene (theme + scene name) that replaces the solid color fallback for unknown themes. A mesh packet type `default` should send every controller to its own stored default scene — useful for resetting the rig to a known per-member state between songs.

- **Controller identity and assignment:** Controllers need a persistent identity (short ID derived from MAC) that can be assigned to a band member in the database. Enables the server to push the right fixture config when a controller joins, and to target commands at specific members or groups rather than broadcasting to all.

- **Sync wait fade to black:** While a controller waits for a heartbeat at boot (before it has synced to the mesh), slowly fade the strips to black rather than keeping them dark and static. Gives a visual indication that the controller is alive and waiting. Fade should complete before the controller would start showing a default or fallback state.

- **I2C button expander:** Replace the two direct GPIO buttons with a PCF8574 or similar I2C GPIO expander. Gives 8 inputs on 2 shared pins, detects simultaneous presses for combo gestures, unaffected by WiFi ADC noise. Current two-button layout (GPIO33 scene/theme, GPIO27 soloist) should map directly into the expander with room to add independent mode, leader declaration, and other show controls as dedicated buttons. Button reading is isolated to the Button class and main.py — the hardware swap should be contained there.

- **Independent mode:** Dual button hold toggles a controller in and out of independent mode. In independent mode the controller ignores incoming mesh commands and does not broadcast its own changes — it runs its own patterns locally without affecting or being affected by the group. On exit, the controller re-syncs to the current mesh state. The control panel should also be able to pull a controller out of independent mode remotely.

- **Control panel debug page — structured packet view:** The `/debug` page exists (combined server+mesh log, push-firmware button, live controller count). Remaining work: a structured per-packet stream — sender MAC, message type, theme/scene/dim, sequence number, timestamp — rather than just log lines.

- **Monitoring and metrics:** Track per-controller health over time — last seen timestamp, packet counts, command success/failure rates, leader election history. Exportable for post-show review. Groundwork for alerting when a controller goes silent mid-show.

- **OTA versioning and passive updates:** Add a version field to the OTA manifest and store the current version on each controller. Controllers would passively check for a newer version on boot and self-update without needing a push command. The push deploy button stays as an override. Versioning also prevents unnecessary downloads when nothing has changed.

- **Rename LIGHTRIG_OTA network:** The shared hotspot SSID is still named `LIGHTRIG_OTA` but now serves both OTA updates and show control. Rename to something more generic (e.g. `LIGHTRIG`) once we decide on a final name.

- **Venue WiFi push:** Add a server command that pushes WiFi credentials to all controllers over the hotspot, allowing them to connect to the venue's WiFi network directly. Controllers would switch to venue WiFi after receiving credentials. Architecture to be designed — needs care around ESP-NOW channel conflicts and recovery if venue WiFi drops.

- **Button Boxes:** Create code for button command boxes that have more buttons but no light outputs. They will have more options for triggering actions in the mesh. These boxes should take precident as lead controllers since they won't have lights.
