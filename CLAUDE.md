# Light Controllers

## Laws — Never Break These

These rules have no exceptions. They override all other instructions.

- **Never commit plaintext passwords, keys, tokens, or secrets to the repository.** All credentials belong in untracked files (`secrets.py`, `.env`) or encrypted secret stores. Never use hardcoded credential fallbacks — if a secrets file is missing, fail loudly with a clear error. Before writing any credential to a file, verify that file is in `.gitignore`. Scan changed files for credential patterns before every commit.

- **No blocking during normal operation.** The main loop must never block — no `sleep()`, no polling loops, no waiting on I/O. All long-running operations (WiFi connection, discovery, OTA) must be implemented as non-blocking state machines that advance one step per tick and return immediately. Blocking is only permitted during one-shot startup operations before the main loop begins (e.g., the boot-time slot selection in boot.py, the initial boot sequence), and for a single WiFi scan (`sta.scan()`, ~2s — no async API exists) at the discrete moment a controller connects to or recovers a hotspot: only the leader scans on connect, and only a freshly-booted or orphaned controller scans on recovery. Steady-state controllers never scan.


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
- After completing work, check the backlog and remove any items that were just addressed.
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

# Architecture (how it works)

Reference documentation for the shipped system. The capability index is in **Feature Outline** below; this section is the "how."

## Code

- **Language:** MicroPython
- **WS2812b control:** built-in `neopixel` module
- **12v PWM control:** `machine.PWM`
- **ESP-NOW:** `espnow` module (built into MicroPython ESP32 port)
- HSV color math written in-house (no FastLED equivalent exists for MicroPython)
- Controllers use a unified `LightRig` abstraction so network logic is decoupled from light type

### A/B firmware slots & crash recovery

Firmware lives in two slots, `/a` and `/b`; the root shims `boot.py` / `main.py`
/ `slots.py` select and run the active one. Those three shims plus the per-device
state at root (`active_slot`, `boot_count`, `device_config.json`, `state.json`)
are the trusted base — updated only by a wired `deploy.sh`, never by OTA.

- **boot.py** counts only *fault* resets (watchdog / `machine.reset`), never a
  user power-on (`machine.reset_cause()`), so power-cycling a healthy unit can't
  falsely mark it bad. It arms the watchdog (via main.py) before importing the
  slot so hangs are caught too. After `THRESHOLD` (3) faults without a stable
  run it flips to the other slot. It *always* flips — even to a slot that has
  also failed — so the unit never refuses to boot.
- **app.py** (the slot entry) marks the active slot `proven` once it has run
  `HEALTHY_MS` (10s) error-free, and resets the boot counter.
- **OTA and deploy write the *unproven* slot** (`slots.update_target`), so a run
  of bad firmwares keeps overwriting the same untried slot and never destroys the
  last known-good one. OTA downloads straight into that slot and flips the
  pointer — there is no separate staging copy and no boot-time file copy.
- A rollback records `update_failed` (slot + version), surfaced on the admin page.

### Server

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
nickname, personal default theme/scene/color, tags) — it is NOT firmware, survives
OTA, and is pushed via a targeted `set_config` command (the controller saves it and
reboots to apply). Controllers report their firmware version and config version
in heartbeats so the admin page can flag outdated units.

# Feature Outline (shipped)

Completed capabilities (an index — the "how" lives in **Architecture** above). **When a group finishes, add its capability here and delete its todos from the backlog.**

- **ESP-NOW mesh & leader election** — peer-to-peer mesh, first-boot election with MAC tiebreak, ~10s reelection on leader loss, autonomous mode when no server, channel convergence on hotspot connect. Admin "Make Leader" forces a bridge handoff (LeaderLink releases then re-acquires the bridge).
- **A/B firmware slots & crash recovery** — two slots, fault-counting boot supervisor, proven-slot update targeting, rollback with an admin "update failed" flag, never refuses to boot.
- **OTA** — downloads into the inactive/unproven slot and flips the pointer; watchdog-fed; orange "do not power off" marker.
- **Server (control panel + admin)** — stdlib package, SQLite per-controller configs + tags + defaults, signed UDP bridge, live registry/mesh-state, bridge-offline UI gating.
- **Show control** — next/random theme & scene, master dim, lights-off toggle, default show, personal defaults.
- **Solo** — individual soloist grid + tag-group solo, relative background dim (heartbeat carries both `dim` and `master_dim`), release; `no-solo` tag.
- **Personal mode** — mesh-wide "everyone show your own default"; entered via the `default` command, exits on any explicit `change`. The `personal` flag in heartbeats is a status signal only (used for the admin display); it does NOT propagate entry to avoid re-infection loops. Distinct from the (specced) independent mode.
- **Per-controller config** — device_config.json (survives OTA), targeted set_config push + reboot, nickname/strips/tags/personal defaults, config-version reporting; blackout before a config-apply reboot.
- **Controller identity** — identified by MAC (short form = last 6 hex); admin lists online + assigned controllers and can `identify` a unit (orange blink overlaid on the running pattern, first 3 LEDs, 2s).
- **Special tags** — leader / button-box / light / no-solo, color-coded, with a picker and reference card (election behavior is specced, not yet wired).
- **Firmware version tracking** — SHA-256 hash, deploy all/outdated, deploy all configs, hash-debug view.

# Grouped Work (current backlog)

Worked in numbered groups. **On finishing a group:** delete its todos here, add the capability to the Feature Outline above, and produce a completed report + a commit message. The Roadmap and Phase Two (at the bottom) are tracked separately and not part of this backlog.

### Group 1 — Shows system
- Show configs in their own DB table (not the `defaults` singleton): name, default theme/scene/color (pushed to the mesh, not a firmware change), and an expected-controller roster. A controller can appear in multiple shows; shows have no strip counts (those belong to the controller). Shows can carry tags (reserved). Selecting the active show pushes its defaults to the mesh.
- Separate show/controller editor page: starts with the show list; add (fresh show section with save/discard), edit (inline under the show with save/discard), delete (confirm), deploy button per show.

### Group 2 — Roster & offline tracking (builds on Group 1)
- Admin: gray out previously-seen offline controllers; per-config "important" toggle (default true for named, false for unnamed) controlling whether a missing controller persists or disappears; remove-from-show (keep the config); per-controller deploy dropdown listing non-responding roster members, then a separator, then all configs A–Z; deploying a config to a new unit auto-removes the matching disconnected one; deploying the same config to multiple online units lets them run as duplicates (ordered by who came online first).

### Group 3 — Identity & default-config refactor
- Short MAC in its own field; nickname becomes optional (none allowed); remove `has_custom_nickname`; display name falls back to short MAC; switch to first 6 hex of the MAC unless problematic. (Cleans up solo-grid filtering — only real nicknames live in the nickname field.)
- Default to 3 strips × 150 LEDs when a controller has no custom light settings.
- Give every controller a built-in default config as a fallback / control target; make its presence hash-aware so a missing one reads as out of date. (Coordinate with Group 4's dual-hash.)

### Group 4 — Repo & integrity refactor
- Mirror the on-device slot layout in the repo; move all scripts (incl. those in subdirs) to `/bin`. move all controller specific files into a `/controller` directory with a flat structure that holds all controler specific files.
- Dual firmware hash: existing hash tracks only OTA-updatable files; a new, unadvertised hash tracks the wired-only sensitive files (the trusted base). On mismatch, flag the controller bold red on the admin page with a "use a hardline and reflash fresh" message.
- Database validation to prevent committing bad data.

### Group 5 — Control authority
- Toggle at the top of the actions: free-mesh mode vs control-plane-only (only the control plane may send changes). Default: free command mode.

### Group 6 — Solo / dim / color UI polish
- **Bug:** tag-solo dims all controllers instead of making the tagged ones soloists — controllers with the matching tag should go to the master level, others should dim to the background fraction.
- **Bug:** special tags (leader, button-box, light, no-solo) should always appear in the tag picker even when no controller has used them yet.
- **Bug:** duplicate tags should be automatically deduplicated when saving a config.
- Color wheel for default colors, with an optional text input below.
- Dimmer-slider shadow showing the previous dim position while the lights-off toggle is engaged.
- Tag-solo highlights the soloists it activates in the grid; clicking one of those overrides the tag solo and hands control to that single soloist; a further click disables solo as normal.
- Personal mode indicator on the top status card of both the control and admin pages (theme/scene show a dashed line when the mesh is in personal mode).
- Independent mode indicator on the top status card of both pages showing when any controller is in independent mode.

### Group 7 — Pattern positioning
- Optional start/end light offset: skip the first N LEDs; end is either an absolute light position or "Z lights ahead of start" (count inclusive of the start), toggleable.

### Group 8 — Advanced custom actions (large / future-leaning)
- Record a series of commands + intervals and save as a custom action ("listening" mode).
- Custom tag sections that create special tags with custom actions/behaviors (significant lift).
- A scene-sync tag plus a distributed syncing system to keep tagged scenes aligned.

### Group 9 — Scale prep (small; when 20+ controllers)
- OTA association jitter: MAC-based stagger before the WiFi connect in ota.py (`mac[5] * 20ms`, 0–5s spread). Config pushes don't need it (ACK-serialized server-side).

**Capture inbox** — raw ideas land here, then get folded into a group.
- (empty)

**Architecture clarification questions** — discussion, not tasks.
* Can the future phone app run the server on its own and broadcast a hotspot from the app, or is a dongle/Pi better?
* Can any config field (show or user) cause a controller to fail and stop working? Do we have tests covering that? (Ties to Group 4's db validation.)

# Roadmap (longer-term, not yet grouped)

Future work and specs beyond the current backlog, but before Phase Two. Pull items into a numbered group when they become active.

- **Tag/group commands:** the tag↔MAC mapping exists (`db.macs_with_tag`) and tag-group *solo* ships; remaining is turning a tag into other group actions (e.g. "dim all horns", set a theme by tag).

- **Config auto-sync on check-in:** when a controller checks in reporting an older config version than the DB holds (e.g. it was offline when the config changed), the server should push the current config automatically rather than only on edit.

- **OTA passive self-update:** have a controller compare its firmware version on boot and self-update without a push (the push deploy stays as the override). The version/hash/report/deploy-outdated infrastructure already ships.

- **Sync-wait fade to black:** while a controller waits for its first heartbeat at boot (before mesh sync), slowly fade the strips to black rather than holding them dark and static — a visible "alive and waiting" cue. Fade completes before any default/fallback state would show.

- **Error-mode display:** richer fault indication on the strips themselves — distinct patterns for different conditions (network loss, boot failure) beyond the existing dim-red fault marker.

- **Admin structured packet view:** a structured per-packet stream on `/admin` — sender MAC, message type, theme/scene/dim, sequence number, timestamp — instead of only log lines.

- **Monitoring and metrics:** per-controller health over time — last-seen, packet counts, command success/failure rates, leader-election history. Exportable for post-show review; groundwork for "controller went silent" alerts.

- **I2C button expander:** replace the two direct GPIO buttons with a PCF8574-style expander — 8 inputs on 2 shared pins, simultaneous-press combos, immune to WiFi ADC noise. Maps the current two-button layout in with room for independent mode, leader declaration, etc. Button reading is isolated to the Button class + main.py, so the swap is contained.

- **Web/phone configuration interface:** ESP32 hosts a WiFi AP for show-day adjustments without redeployment. Must be secured (auth, ideally role-based) so the audience / a band member can't trigger main-level overrides.

- **Beat-sync patterns:** patterns that accept BPM and pulse on the beat. BPM set manually or broadcast from the main.

- **WiFi credential management:** Controllers store two WiFi credential sets — a *fallback* hotspot (permanent, the show hotspot) and a *temporary* one (venue WiFi, optional). On connect, the temporary is tried first; if it fails or is absent, the fallback is used. Admin page has a dedicated card to push new credentials for either slot and a button to clear the temporary. All credentials pushed over the network must be encrypted and unpacked by each controller (the existing HMAC-signed command channel provides integrity; a lightweight symmetric cipher or the existing bridge secret can provide confidentiality). Needs care around ESP-NOW channel conflicts when switching to venue WiFi, and clean recovery if venue WiFi drops mid-show.

- **Rename LIGHTRIG_OTA network:** the shared hotspot SSID still says `LIGHTRIG_OTA` but now serves both OTA and show control. Rename to something generic (e.g. `LIGHTRIG`) once the final name is decided.

### Spec — Independent mode

A controller in independent mode runs freely without being affected by or affecting the rest of the rig. Distinct from personal mode (a mesh-wide coordinated state).

- **Does:** runs its own patterns (buttons change its own state only); keeps forwarding mesh packets (relay/leader duties unaffected); keeps sending heartbeats with an `independent: True` flag; the heartbeat does NOT carry its theme/scene as authoritative; still respects master dim.
- **Ignores:** incoming theme/scene (`change`/heartbeat sync), solo (`solo`/`solo_request`/`solo_tag`), dim, and `default`. Does NOT propagate — no other controller goes independent because of this one.
- **Enter:** dual-button hold, or a targeted `enter_independent` command.
- **Exit:** dual-button hold (toggle), a broadcast `exit_independent` (releases ALL), or a targeted `exit_independent` (releases one). On exit it re-syncs to current mesh state from the next heartbeat.
- **Admin UI:** a card on the control page listing all independent controllers (from the flag) with a "Release All" and per-controller "Release". An indicator on the top status card of both the control and admin pages shows when any controller is in independent mode, just one icon saying more than 0 are independent.

### Spec — Tiered leader election (Hybrid A)

Problem: the elected leader bridges the mesh to the server, and ESP-NOW + WiFi share one radio, so the bridge work stutters that controller's rendering. Fix: prefer no-light / designated devices for the bridge so light controllers stay fast — while never removing the hardware-free failover to a light controller.

- **Priority (high → low):** `leader`-tagged → `button-box`-tagged (no lights) → light controllers (default / `light`-tagged, the failsafe). MAC breaks ties within a tier. *(In "leader → mac → button-box → light", `mac` is read as the in-tier tiebreaker, not a separate tier — confirm if you meant otherwise.)*
- **Behavior:** each controller computes its own tier from its tags; declares leader only if no higher-tier peer is online; defers to higher tiers (and to a winning MAC in-tier); hands off if a higher-tier device appears (pre-emption on the next reelection window, with hysteresis); if all higher-tier devices drop, a light controller takes over.
- **Plumbing:** heartbeats carry the sender's tier (a small int) — `mesh.py` `_broadcast`, `controller.py` `tick_start` / `_become_leader` / reelection. A `button-box`-tagged (or zero-strip) controller builds an empty fixture and skips rendering.
- **Tags:** `leader` / `button-box` / `light` are reserved election-role tags (UI/colors/reference card already shipped). `no-solo` is a behavior flag.



# Phase Two — Future Architecture (do not start yet; keep in mind)

Big structural work for after the current phase and roadmap. The **leader failsafe is never eliminated** in any of these — light-controller election always remains the bottom backstop.

- **Live config updates (no reboot):** gracefully apply config changes that don't require hardware re-init (nickname, tags, personal defaults, colors) without a full reboot. Strip-layout changes still require restart. Requires splitting `apply_set_config` into live-apply vs next-boot fields. Add a confirm save and push popup when making a change that requires a restart with a message about which fields cause a restart.

- **Pi/ESP32 hybrid leader boxes (topmost bridge tier):** A Raspberry Pi hosts the server in Docker and holds the configs locally. It serves the control plane over DNS/hostname so phones and laptops connect by name instead of an IP. One or more attached ESP32s drive the ESP-NOW mesh as the bridge (the Pi talks to them over USB/serial). When built, these boxes become the highest election tier — the `leader` tag is moved onto them. Multiple ESP32s per Pi allow additional zones and automatic failover among the Pi's own bridge radios. This is the eventual home of the `leader` tag from the Hybrid A spec.

- **Server-as-mesh-peer via ESP-NOW dongle (Option B):** Instead of a controller bridging over WiFi, the server speaks ESP-NOW directly through a USB ESP32 dongle running a serial↔ESP-NOW firmware. Eliminates WiFi-during-show for control entirely (no association, no channel convergence, every controller equally fast); WiFi survives only for OTA, which is already per-controller. Signed commands unchanged, new transport. This underlies the Pi-hybrid box's ESP32 link.

- **10,000-node bridge / zone architecture:** The main speaks a higher-level protocol (Art-Net, OSC, or custom TCP/IP) to bridge nodes, each managing a zone of up to ~200 controllers over ESP-NOW. Controllers are unaware they are in a zone — same firmware, same mesh code throughout. The Pi-hybrid boxes are the natural bridge nodes.

- **Leader / authority hierarchy:** Distinct from the elected bridge leader. A designated authority (the Pi/server) can issue commands all controllers must obey regardless of local button presses. The `type` field in the mesh packet and `apply_state` are the designed extension points.

- **Art-Net integration:** A main node (or bridge device) receives Art-Net DMX-over-IP from professional lighting consoles and translates to ESP-NOW commands. Keep protocol boundaries clean so this layer adds without restructuring the core network.

# Ingest

New things that need to be added to groups, roadmap, or active bugs. Do not delete this section when items have been transferred.

- (empty)
- 