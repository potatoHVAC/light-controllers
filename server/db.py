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
    mac                 TEXT PRIMARY KEY,
    nickname            TEXT,
    has_custom_nickname INTEGER NOT NULL DEFAULT 0,
    strip1_leds         INTEGER NOT NULL DEFAULT 0,
    strip2_leds         INTEGER NOT NULL DEFAULT 0,
    strip3_leds         INTEGER NOT NULL DEFAULT 0,
    default_theme       TEXT,
    default_scene       TEXT,
    default_color       TEXT,
    config_version      INTEGER NOT NULL DEFAULT 1,
    updated_at          REAL NOT NULL DEFAULT 0
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
CREATE TABLE IF NOT EXISTS shows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    default_theme TEXT,
    default_scene TEXT,
    default_color TEXT,
    created_at    REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS show_controllers (
    show_id        INTEGER NOT NULL,
    controller_mac TEXT NOT NULL,
    PRIMARY KEY (show_id, controller_mac)
);
CREATE TABLE IF NOT EXISTS show_tags (
    show_id INTEGER NOT NULL,
    tag_id  INTEGER NOT NULL,
    PRIMARY KEY (show_id, tag_id)
);
"""

_CONFIG_FIELDS = ('nickname', 'strip1_leds', 'strip2_leds', 'strip3_leds',
                  'default_theme', 'default_scene', 'default_color')

_SHOW_FIELDS = ('name', 'default_theme', 'default_scene', 'default_color')


class Database:
    def __init__(self, path=':memory:'):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute("INSERT OR IGNORE INTO defaults (id) VALUES (1)")
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """Apply schema changes to existing databases."""
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(controllers)")}
        if 'has_custom_nickname' not in cols:
            self._conn.execute(
                "ALTER TABLE controllers ADD COLUMN has_custom_nickname INTEGER NOT NULL DEFAULT 0")
            # Backfill: controllers that already have a nickname were user-defined.
            self._conn.execute(
                "UPDATE controllers SET has_custom_nickname = 1 WHERE nickname IS NOT NULL AND nickname != ''")

        dcols = {r[1] for r in self._conn.execute("PRAGMA table_info(defaults)")}
        if 'active_show_id' not in dcols:
            self._conn.execute("ALTER TABLE defaults ADD COLUMN active_show_id INTEGER")

    # ── controllers ──────────────────────────────────────────────────────────

    def upsert_controller(self, mac, **fields):
        """Create or update a controller config. Unknown fields are ignored.
        Bumps config_version so controllers can detect the change.
        has_custom_nickname is set automatically from whether nickname is provided."""
        fields = {k: v for k, v in fields.items() if k in _CONFIG_FIELDS}
        if 'nickname' in fields:
            fields['has_custom_nickname'] = 1 if fields['nickname'] else 0
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

    # ── shows ─────────────────────────────────────────────────────────────────

    def create_show(self, name, **fields):
        fields = {k: v for k, v in fields.items() if k in _SHOW_FIELDS and k != 'name'}
        cols = ['name', 'created_at'] + list(fields)
        vals = [name, time.time()] + [fields[k] for k in fields]
        ph = ','.join('?' * len(cols))
        cur = self._conn.execute(
            f"INSERT INTO shows ({','.join(cols)}) VALUES ({ph})", vals)
        self._conn.commit()
        return self.get_show(cur.lastrowid)

    def get_show(self, show_id):
        cur = self._conn.execute("SELECT * FROM shows WHERE id=?", (show_id,))
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d['controllers'] = self.show_controllers(show_id)
        d['tags'] = self.show_tags(show_id)
        return d

    def list_shows(self):
        cur = self._conn.execute("SELECT id FROM shows ORDER BY name")
        return [self.get_show(r['id']) for r in cur.fetchall()]

    def update_show(self, show_id, **fields):
        fields = {k: v for k, v in fields.items() if k in _SHOW_FIELDS}
        if fields:
            sets = ', '.join(f"{k}=?" for k in fields)
            self._conn.execute(f"UPDATE shows SET {sets} WHERE id=?",
                               list(fields.values()) + [show_id])
            self._conn.commit()
        return self.get_show(show_id)

    def delete_show(self, show_id):
        self._conn.execute("DELETE FROM show_controllers WHERE show_id=?", (show_id,))
        self._conn.execute("DELETE FROM show_tags WHERE show_id=?", (show_id,))
        self._conn.execute("DELETE FROM shows WHERE id=?", (show_id,))
        self._conn.execute(
            "UPDATE defaults SET active_show_id=NULL WHERE active_show_id=?", (show_id,))
        self._conn.commit()

    # roster — a show's expected controllers (a controller may be in many shows)

    def show_controllers(self, show_id):
        cur = self._conn.execute(
            "SELECT controller_mac AS mac FROM show_controllers "
            "WHERE show_id=? ORDER BY controller_mac", (show_id,))
        return [r['mac'] for r in cur.fetchall()]

    def set_show_controllers(self, show_id, macs):
        self._conn.execute("DELETE FROM show_controllers WHERE show_id=?", (show_id,))
        for m in macs:
            if m:
                self._conn.execute(
                    "INSERT OR IGNORE INTO show_controllers VALUES (?, ?)", (show_id, m))
        self._conn.commit()

    def add_show_controller(self, show_id, mac):
        self._conn.execute(
            "INSERT OR IGNORE INTO show_controllers VALUES (?, ?)", (show_id, mac))
        self._conn.commit()

    def shows_for_controller(self, mac):
        cur = self._conn.execute(
            "SELECT show_id FROM show_controllers WHERE controller_mac=?", (mac,))
        return [r['show_id'] for r in cur.fetchall()]

    # show tags (reserved for future use)

    def show_tags(self, show_id):
        cur = self._conn.execute(
            "SELECT t.name FROM tags t JOIN show_tags st ON st.tag_id=t.id "
            "WHERE st.show_id=? ORDER BY t.name", (show_id,))
        return [r['name'] for r in cur.fetchall()]

    def set_show_tags(self, show_id, names):
        self._conn.execute("DELETE FROM show_tags WHERE show_id=?", (show_id,))
        for name in names:
            name = name.strip()
            if name:
                self._conn.execute(
                    "INSERT OR IGNORE INTO show_tags VALUES (?, ?)",
                    (show_id, self._tag_id(name)))
        self._conn.commit()

    # active show

    def get_active_show(self):
        cur = self._conn.execute("SELECT active_show_id FROM defaults WHERE id=1")
        row = cur.fetchone()
        sid = row['active_show_id'] if row else None
        return self.get_show(sid) if sid else None

    def set_active_show(self, show_id):
        self._conn.execute("UPDATE defaults SET active_show_id=? WHERE id=1", (show_id,))
        self._conn.commit()
        return self.get_active_show()

    def close(self):
        self._conn.close()
