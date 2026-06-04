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

## Server

The laptop/phone server is a stdlib-only Python package under `server/` (no web
framework — it runs zero-install on a show laptop or in Docker). Run it with
`python3 -m server.app` (or `./server/run.sh`, `./server/run.sh --local`).

- `app.py` — HTTP dispatch (route tables), static serving, OTA endpoints, wiring.
- `db.py` — SQLite (`server/lightrig.db`): controller configs, agnostic tags, defaults.
- `firmware.py` — OTA manifest + a version hash over firmware files (excludes
  `secrets.py` and the per-device config). `OTA_FILES` mirrors `deploy.sh`.
- `link.py` — the bridge UDP comms, signed commands (with optional `target` MAC
  for per-controller commands), and the live controller registry / mesh state.
- `api.py` — control + admin + config logic (testable, no HTTP).
- `serverlog.py` — bounded log shown on both pages.
- `static/` — `control.html` (the default page `/`), `admin.html` (`/admin`),
  shared `app.css` / `common.js`. Vanilla JS, mobile-first, PWA manifest. No build step.

Per-controller config lives in `device_config.json` on the device (strip layout,
nickname, personal default theme/scene/color) — it is NOT firmware, survives OTA,
and is pushed via a targeted `set_config` command (the controller saves it and
reboots to apply). Controllers report their firmware version and config version
in heartbeats so the admin page can flag outdated units.

## Long-Term Roadmap (not immediate priority)

- **Art-Net integration:** Allow a main node (or bridge device) to receive Art-Net DMX-over-IP from professional lighting consoles, translating to ESP-NOW commands across the rig network. Keep protocol boundaries clean so this layer can be added without restructuring the core network.

- **Leader / authority hierarchy:** The elected leader (bridge controller) is the current coordinator but has no authority over other controllers beyond what the mesh protocol provides. A future "authority" layer would allow a designated controller — or the laptop server via the bridge — to issue commands that all controllers must obey regardless of local button presses. This is distinct from the elected leader; the authority could be the server itself. The `type` field in the mesh packet and `apply_state` are the designed extension points.

- **Bridge architecture:** At 10,000-unit scale the main speaks a higher-level protocol (Art-Net, OSC, or custom TCP/IP) to bridge nodes, each of which manages a zone of up to ~200 controllers over ESP-NOW. Controllers are unaware they are in a zone — same firmware, same mesh code throughout.

- **Web/phone configuration interface:** ESP32 hosts a WiFi access point for show-day adjustments without redeployment. Must be secured so audience members cannot interfere — authentication required, ideally with role-based access so a band member cannot accidentally trigger main-level overrides.

- **Beat-sync patterns:** Patterns that accept BPM as a parameter and pulse on the beat. BPM set manually or broadcast from the main controller.

- **OTA passive self-update:** The server now hashes the firmware into a version, the OTA manifest carries it, controllers store it (`firmware_version`) and report it, and the admin page flags/deploys outdated units. Remaining: have a controller compare versions on boot and self-update without a push (the push deploy stays as the override).

- **Error mode display:** Use the addressable strips themselves as the error indicator. On network failure, boot failure, or other fault conditions, display a distinct error pattern on the strips rather than a separate status LED.

- **Per-member fixture configs — remaining work:** The DB stores per-controller nickname, strip lengths, agnostic tags, and a personal default theme/scene/color; the `default` packet sends everyone to their stored default; `set_config` pushes a config to one controller. Still to do: pattern tuning per member, favorites (deliberately deferred), and **tag/group commands** (e.g. "solo all drummers", "dim all horns") — the tag↔MAC mapping exists in `db.macs_with_tag`, but no API/command turns a tag into a targeted group action yet.

- **Config auto-sync on check-in:** Controllers report their config version in heartbeats, and saving a config pushes `set_config` to that controller. Still to do: when a controller checks in reporting an older config version than the DB holds (e.g. it was offline when the config changed), the server should push the current config automatically rather than only on edit.

- **Controller identity and assignment — done:** Controllers are identified by MAC (short form = last 6 hex). The admin page lists online + assigned controllers, pushes configs, and can `identify` a unit (orange blink). Remaining identity work is folded into the two items above.

- **Sync wait fade to black:** While a controller waits for a heartbeat at boot (before it has synced to the mesh), slowly fade the strips to black rather than keeping them dark and static. Gives a visual indication that the controller is alive and waiting. Fade should complete before the controller would start showing a default or fallback state.

- **I2C button expander:** Replace the two direct GPIO buttons with a PCF8574 or similar I2C GPIO expander. Gives 8 inputs on 2 shared pins, detects simultaneous presses for combo gestures, unaffected by WiFi ADC noise. Current two-button layout (GPIO33 scene/theme, GPIO27 soloist) should map directly into the expander with room to add independent mode, leader declaration, and other show controls as dedicated buttons. Button reading is isolated to the Button class and main.py — the hardware swap should be contained there.

- **Independent mode:** Dual button hold toggles a controller in and out of independent mode. In independent mode the controller ignores incoming mesh commands and does not broadcast its own changes — it runs its own patterns locally without affecting or being affected by the group. On exit, the controller re-syncs to the current mesh state. The control panel should also be able to pull a controller out of independent mode remotely.

- **Admin page — structured packet view:** The `/admin` page exists (mesh stats, firmware version + deploy all/outdated, controller list with identify + config editor, defaults, combined server+mesh log). Remaining: a structured per-packet stream — sender MAC, message type, theme/scene/dim, sequence number, timestamp — rather than just log lines.

- **Monitoring and metrics:** Track per-controller health over time — last seen timestamp, packet counts, command success/failure rates, leader election history. Exportable for post-show review. Groundwork for alerting when a controller goes silent mid-show.

- **Rename LIGHTRIG_OTA network:** The shared hotspot SSID is still named `LIGHTRIG_OTA` but now serves both OTA updates and show control. Rename to something more generic (e.g. `LIGHTRIG`) once we decide on a final name.

- **Venue WiFi push:** Add a server command that pushes WiFi credentials to all controllers over the hotspot, allowing them to connect to the venue's WiFi network directly. Controllers would switch to venue WiFi after receiving credentials. Architecture to be designed — needs care around ESP-NOW channel conflicts and recovery if venue WiFi drops.

- **Button Boxes:** Create code for button command boxes that have more buttons but no light outputs. They will have more options for triggering actions in the mesh. These boxes should take precedence as lead controllers since they won't have lights.

**TODO**

The following categories are unrefined ideas and todo items. Keep the list titles even if all items have been removed.

- **Change Requests:**
* A list of tags can be shown from a button that doesn't change the page. those can be selected and added to the tags field. Typing tags also auto completes with known tags, unknown tags get added automatically. 
* default scene selection is also a drop down with all known themes. 
* add a button next to a controller to force the leader to switch to that controller. This should not prevent a reelection incase that controller goes down. Just acts like that controller won a new election. 
* Add all active tags as buttons below the release soloist button on the control page that cause all controllers with that tag to be in solo mode. This should be done through the packet as, soloist to trumpet tags and those controllers should check the tag against their internal tag list and turn them selves on accordingly. I don't want individually addressed packets. Just one mass packet that lets everyone know who the target solo group is. 
* Add a slider to change the relative brightness for non solo member at the top of the solo button area. This is relative to the soloist lighting which could have been controlled by the master dimmer above. 
* Add the default config as a fall back (or potential target for control actions) to every controller and make it part of the firmware hash so controlers are out of date when it's missing. 
* I want a toggle at the top of the actioins that switches between mesh freedom and only the control plane is allowed to send changes. default is free comand mode.
* The ident needs to start with an all lights off and then flash 3 lights 3 times. I like the current tempo of the flashes. 
* create a special controller tag named "leader" that when applied to a controller makes them a priority for handling the bridge
* remove the text from the tag input field for controller edits. 
* Create a special controller tag named "no-solo" that appears red. this tag removes the controller from the solo grid. It does not prevent that controller from participating in tag based solo groups. 
* Add a special tag description page to the config edit page just before the controller section
* discuss a system of saving some amount of logs after each show and keeping a few shows worth of logs before removing them. 
* Add special tag "player" 
* controllers without a user defined nickname should have priority as bridge. the order is leader label -> mac address name -> nicknamed -> player
* add a color wheel for picking default colors with an optional text input below. 

- **Larger Ideas:**
* I see were tracking when controllers go offline. I like that behavior on the main page. I also want that on the admin page to gray out missing controllers that have previously been seen this session. On the admin page make an option to remove that user from the show (do not delete that persons config). I want a deploy button next to each controller that opens a drop down that starts with a list of all known controllers for that show that are not responding then a line break and a list of all known configs in alphabetical order. If a new controller is brought online and a config is deployed, automatically remove the disconnected controller. If a config is deployed multiple times then those two controllers are allowed to operate as duplicates of each other. Put those in the list order based on which ever controller came online first. Controller configs should have a toggle that when true means they are important and should follow this missing controller behavior. False means they just disappear from the pages. Default should be any named controller is true, any unnamed controller is false.
* Show configs live in their own DB table — not the `defaults` singleton. A show has a name, default theme/scene/color (show-wide fallback pushed as a mesh packet, not a firmware change), and a list of expected controllers by assignment. Shows do NOT have strip LED counts — those belong to the controller. A controller can appear across multiple shows. UI: dropdown at the top of the admin page to select the active show; selecting one sends its defaults to the mesh. Show editor lists expected controllers and flags missing ones; a session-reset button flushes the missing list without deleting the show's known controller roster. New controllers that check in during a show's lifecycle are added automatically. Shows can have tags (reserved for future use).
* Make a separate config for adding and editing shows and controllers the page should start with show lists. Have an add button at the top of the section that opens a fresh show config as a section below and buttons with a save and discard. List all shows by name underneath with an edit button that opens the edit page under that show with save and discard. Add a delete button next to that with a confirm popup. Add a deploy button next to the show title

- **Future Ideas:**
* allow an optional starting position for the lights so they might skip the first n lights before displaying the pattern. Ending light is based on it's light position but provide a toggle to switch to end is Z lights ahead of start where number of lights includes the starting light. E.G. start 2, end 5 in default would turn on lights 2, 3, 4, 5 but in the other mode it would be 2, 3, 4, 5, 6. 
* add a shadow to the dimmer slidder that shows the previous location of the dim setting when the lights off toggle is engaged. 
* Build a listening option so a series of commands and their time intervals can be recorded and saved to be used as custom actions. 
* add custom tag sections for creating special tags and giving them custom actions (this would be a significant lift to create custom commands and behaviors)


- **BUG Report:**
* when pushing a new config send a turn off all lights signal to wipe any lights past what we are turning off. The strings may be longer than what we want to show at a given time. 
* The everyone personal (change name to personal defaults) momentarily changes the controllers before they change back. I'm assuming the heartbeat is overriding the change because it doesn't understand how users could be doing something different. 
* a controller with fewer than 3 lights on its main string seems to prevent a firmware deployment. I assume it's because it's missing enough leds. This should not be blocking and a controller should be fine with missing some or all of the downloading lights. 

- **Architecture Clarification Questions:**

These are questions that I want clarification on over how they work so we can discuss if changes need to be made.

* Is everything related to the user configs stored in the local database. I want to ensure were not adding traffic to the mesh by polling the admin page more than is necessary. I expect things like leader and controller count can all be picked up passively. 
* Can the future phone app operate the server on its own and broadcast a hotspot from the app or would it be better to 

- **Refactor:**
* give all controllers a short mac address name in it's own field. Then remove the short mac addresses from controler nicknames and allow them to be none. That way we can remove the user defined nickname flag and fix the solo page selection because only user defined nicknames would appear in the nickname field. Make sure any display name defaults to the short macaddress when nickname is not present. Switch to using the first 6 characters of the mac instead of the last 6 unless that would be a problem. 