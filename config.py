# Shared non-secret configuration for controllers and the server.
# Credentials (SSIDs, passwords) live in secrets.py.

DISCOVERY_PORT = 5000   # UDP broadcast for server discovery
BRIDGE_PORT    = 5001   # UDP bridge between leader controller and server
HTTP_PORT      = 8080   # Server HTTP port

# ESP-NOW and WiFi share one radio and must be on the same channel. The leader
# discovers the hotspot's channel by scanning and announces it to the mesh
# (set_channel) before associating, so the whole mesh migrates together and the
# leader is never dragged off a channel the followers can still hear.
# DEFAULT_CHANNEL is only the starting channel every controller boots on (and
# the fallback when no hotspot exists) — its value is arbitrary, it just has to
# be identical on every controller.
DEFAULT_CHANNEL = 1
SET_CHANNEL_REPEATS = 5  # times to burst the set_channel announcement

# Leader bridge-retry backoff. Doubles from INIT to MAX (the rampup). Once it
# reaches MAX the leader declares the mesh autonomous (heartbeat 'auto' flag).
# After CAP_RETRIES further failures at MAX it stops scanning entirely until a
# newly-booted controller finds a hotspot and alerts it (hotspot_found).
BRIDGE_RETRY_INIT_MS      = 5000
BRIDGE_RETRY_MAX_MS       = 300000   # 5 minutes
BRIDGE_AUTONOMOUS_AFTER_MS = 40000   # declare autonomous once the 40s interval fails
BRIDGE_CAP_RETRIES        = 3        # cap-interval failures after rampup before giving up

# Discovery broadcast message. Any server implementation must broadcast this
# as a UDP payload to 255.255.255.255:DISCOVERY_PORT every second.
# The leader controller listens for it to find the server's IP address.
DISCOVERY_MSG  = b'LIGHTRIG'

# ── Bridge protocol ───────────────────────────────────────────────────────────
# Any device (laptop, phone app, tablet) can act as the server by implementing
# this two-step protocol:
#
# 1. DISCOVERY (server → broadcast)
#    UDP broadcast to 255.255.255.255:DISCOVERY_PORT every ~1 second.
#    Payload: DISCOVERY_MSG (bytes literal, not JSON).
#    The leader controller listens for this to find the server's IP.
#
# 2. BRIDGE (bidirectional UDP on BRIDGE_PORT)
#    Controller → server: forwarded ESP-NOW packets (fire-and-forget).
#      {"fwd": true, "type": "...", "sender": "mac", ...mesh fields...}
#    Controller → server: connection announcement.
#      {"type": "bridge_connected"}
#    Server → controller: sequenced commands (with retry + ACK).
#      {"seq": 42, "type": "change"|"dim"|"solo"|"ota_update", ...}
#    Controller → server: ACK.
#      {"ack": 42}
#    The controller deduplicates by sequence number — retransmits are safe.
# ─────────────────────────────────────────────────────────────────────────────

# Mirrors the themes list in main.py.
# Update here when themes change — the server reads this for control panel logic.
THEMES = [
    {'name': 'random', 'scenes': ['rainbow', 'firefly'], 'color': None},
    {'name': 'red',    'scenes': ['solid', 'breathe'],   'color': [255, 0, 0]},
    {'name': 'blue',   'scenes': ['solid', 'breathe'],   'color': [0, 0, 255]},
]
