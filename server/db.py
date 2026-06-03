"""SQLite data layer for controller configs, tags, and defaults.

Object-agnostic by design: a "controller" drives up to three light strips and
carries free-form tags. Tags are just names — "percussion" / "horns" for a band,
or anything else for lights on other objects. Nothing here is band-specific.

The DB stores *persistent config*; live mesh state (who's online, current
theme/scene) lives in the bridge link registry, not here.
"""
import sqlite3
import time

MAX_STRIPS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS controllers (
    mac            TEXT PRIMARY KEY,
    nickname       TEXT,
    strip1_leds    INTEGER NOT NULL DEFAULT 0,
    strip2_leds    INTEGER NOT NULL DEFAULT 0,
    strip3_leds    INTEGER NOT NULL DEFAULT 0,
    default_theme  TEXT,
    default_scene  TEXT,
    default_color  TEXT,
    config_version INTEGER NOT NULL DEFAULT 1,
    updated_at     REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS controller_tags (
    controller_mac TEXT NOT NULL,
    tag_id         INTEGER NOT NULL,
    PRIMARY KEY (controller_mac, tag_id)
);
CREATE TABLE IF NOT EXISTS defaults (
    id                     INTEGER PRIMARY KEY CHECK (id = 1),
    show_theme             TEXT,
    show_scene             TEXT,
    unassigned_theme       TEXT,
    unassigned_scene       TEXT,
    unassigned_color       TEXT,
    unassigned_strip1_leds INTEGER NOT NULL DEFAULT 0,
    unassigned_strip2_leds INTEGER NOT NULL DEFAULT 0,
    unassigned_strip3_leds INTEGER NOT NULL DEFAULT 0
);
"""

_CONFIG_FIELDS = ('nickname', 'strip1_leds', 'strip2_leds', 'strip3_leds',
                  'default_theme', 'default_scene', 'default_color')


class Database:
    def __init__(self, path=':memory:'):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO defaults (id) VALUES (1)")
        self._conn.commit()

    # ── controllers ──────────────────────────────────────────────────────────

    def upsert_controller(self, mac, **fields):
        """Create or update a controller config. Unknown fields are ignored.
        Bumps config_version so controllers can detect the change."""
        fields = {k: v for k, v in fields.items() if k in _CONFIG_FIELDS}
        row = self.get_controller(mac)
        if row is None:
            cols = ['mac', 'updated_at', 'config_version'] + list(fields)
            vals = [mac, time.time(), 1] + [fields[k] for k in fields]
            ph = ','.join('?' * len(cols))
            self._conn.execute(
                f"INSERT INTO controllers ({','.join(cols)}) VALUES ({ph})", vals)
        else:
            sets = ', '.join(f"{k}=?" for k in fields)
            vals = [fields[k] for k in fields]
            extra = "config_version=config_version+1, updated_at=?"
            self._conn.execute(
                f"UPDATE controllers SET {sets+', ' if sets else ''}{extra} WHERE mac=?",
                vals + [time.time(), mac])
        self._conn.commit()
        return self.get_controller(mac)

    def get_controller(self, mac):
        cur = self._conn.execute("SELECT * FROM controllers WHERE mac=?", (mac,))
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d['tags'] = self.controller_tags(mac)
        return d

    def list_controllers(self):
        cur = self._conn.execute("SELECT mac FROM controllers ORDER BY nickname, mac")
        return [self.get_controller(r['mac']) for r in cur.fetchall()]

    def delete_controller(self, mac):
        self._conn.execute("DELETE FROM controller_tags WHERE controller_mac=?", (mac,))
        self._conn.execute("DELETE FROM controllers WHERE mac=?", (mac,))
        self._conn.commit()

    # ── tags ─────────────────────────────────────────────────────────────────

    def list_tags(self):
        cur = self._conn.execute("SELECT name FROM tags ORDER BY name")
        return [r['name'] for r in cur.fetchall()]

    def _tag_id(self, name):
        self._conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        cur = self._conn.execute("SELECT id FROM tags WHERE name=?", (name,))
        return cur.fetchone()['id']

    def set_tags(self, mac, names):
        """Replace a controller's tags with the given names (created as needed)."""
        self._conn.execute("DELETE FROM controller_tags WHERE controller_mac=?", (mac,))
        for name in names:
            name = name.strip()
            if name:
                self._conn.execute(
                    "INSERT OR IGNORE INTO controller_tags VALUES (?, ?)",
                    (mac, self._tag_id(name)))
        self._conn.commit()

    def controller_tags(self, mac):
        cur = self._conn.execute(
            "SELECT t.name FROM tags t JOIN controller_tags ct ON ct.tag_id=t.id "
            "WHERE ct.controller_mac=? ORDER BY t.name", (mac,))
        return [r['name'] for r in cur.fetchall()]

    def macs_with_tag(self, name):
        cur = self._conn.execute(
            "SELECT ct.controller_mac AS mac FROM controller_tags ct "
            "JOIN tags t ON t.id=ct.tag_id WHERE t.name=?", (name,))
        return [r['mac'] for r in cur.fetchall()]

    # ── defaults ─────────────────────────────────────────────────────────────

    def get_defaults(self):
        cur = self._conn.execute("SELECT * FROM defaults WHERE id=1")
        return dict(cur.fetchone())

    def update_defaults(self, **fields):
        allowed = ('show_theme', 'show_scene', 'unassigned_theme',
                   'unassigned_scene', 'unassigned_color',
                   'unassigned_strip1_leds', 'unassigned_strip2_leds',
                   'unassigned_strip3_leds')
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ', '.join(f"{k}=?" for k in fields)
            self._conn.execute(f"UPDATE defaults SET {sets} WHERE id=1",
                               list(fields.values()))
            self._conn.commit()
        return self.get_defaults()

    def close(self):
        self._conn.close()
