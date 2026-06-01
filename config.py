# Shared non-secret configuration for controllers and the server.
# Credentials (SSIDs, passwords) live in secrets.py.

DISCOVERY_PORT = 5000   # UDP broadcast for server discovery
BRIDGE_PORT    = 5001   # UDP bridge between leader controller and server
HTTP_PORT      = 8080   # Server HTTP port

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
