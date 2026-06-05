"""Application logic for the control panel and admin pages.

Pure-ish: every method operates on injected db / link / firmware root, so the
HTTP layer in app.py is a thin dispatcher and this is unit-testable.
"""
import random

from server import firmware


def short_mac(mac):
    """Default human id for a controller with no nickname: last 6 hex, upper."""
    return mac[-6:].upper() if mac else '??????'


def _parse_color(value):
    """'#rrggbb' (or 'rrggbb') -> [r, g, b], or None if unparseable."""
    if not value:
        return None
    s = value.lstrip('#')
    if len(s) != 6:
        return None
    try:
        return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]
    except ValueError:
        return None


class Api:
    def __init__(self, db, link, log, root, themes):
        self._db     = db
        self._link   = link
        self._log    = log
        self._root   = root
        self._themes = themes
        self._link.on_checkin = self._auto_sync_config

    def _auto_sync_config(self, mac, reported_cfg):
        """Push config to a controller that checks in with a stale config version."""
        cfg = self._db.get_controller(mac)
        if not cfg:
            return
        db_version = cfg.get('config_version', 1)
        if (reported_cfg or 0) < db_version:
            self._push_config(mac, cfg)
            self._log.write(
                f'Auto-synced config for {short_mac(mac)} '
                f'(controller v{reported_cfg} → db v{db_version})'
            )

    # ── read views ───────────────────────────────────────────────────────────

    def status(self):
        s = dict(self._link.mesh_state)
        s['connected']   = self._link.connected()
        s['controllers'] = len(self._link.online())
        s['version']     = firmware.current_version(self._root)
        online = self._link.online()
        leader_mac = next((mac for mac, info in online.items() if info.get('leader')), None)
        if leader_mac:
            cfg = self._db.get_controller(leader_mac)
            s['leader_name'] = (cfg or {}).get('nickname') or short_mac(leader_mac)
        else:
            s['leader_name'] = None
        active = self._db.get_active_show()
        s['show_name'] = active['name'] if active else None
        return s

    def controllers(self):
        """Merge live registry with stored configs. Each entry carries online
        status, assignment, firmware freshness, and the current theme/scene."""
        version = firmware.current_version(self._root)
        online  = self._link.online()
        out = {}
        for mac, info in online.items():
            cfg = self._db.get_controller(mac)
            out[mac] = {
                'mac': mac,
                'nickname': (cfg or {}).get('nickname') or short_mac(mac),
                'has_nickname': bool((cfg or {}).get('has_custom_nickname')),
                'assigned': cfg is not None,
                'online': True,
                'leader': info['leader'],
                'theme': info['theme'], 'scene': info['scene'], 'dim': info['dim'],
                'fw': info['fw'],
                'outdated': info['fw'] != version,
                'cfg': info.get('cfg'),
                'cfg_stale': bool(cfg and (info.get('cfg') or 0) < cfg.get('config_version', 1)),
                'update_failed': info.get('update_failed'),
                'tags': (cfg or {}).get('tags', []),
                'default_theme': (cfg or {}).get('default_theme'),
                'default_scene': (cfg or {}).get('default_scene'),
                'default_color': (cfg or {}).get('default_color'),
            }
        for cfg in self._db.list_controllers():
            if cfg['mac'] not in out:
                out[cfg['mac']] = {
                    'mac': cfg['mac'],
                    'nickname': cfg.get('nickname') or short_mac(cfg['mac']),
                    'has_nickname': bool(cfg.get('has_custom_nickname')),
                    'assigned': True, 'online': False, 'leader': False,
                    'theme': None, 'scene': None, 'dim': 1.0,
                    'fw': None, 'outdated': True, 'update_failed': None,
                    'tags': cfg.get('tags', []),
                    'default_theme': cfg.get('default_theme'),
                    'default_scene': cfg.get('default_scene'),
                    'default_color': cfg.get('default_color'),
                }
        # Named controllers first (alphabetical), then unnamed (MAC order).
        return sorted(out.values(), key=lambda c: (
            not c['has_nickname'],
            c['nickname'].lower() if c['has_nickname'] else c['mac'].lower(),
        ))

    def defaults(self):
        return self._db.get_defaults()

    def tags(self):
        return self._db.list_tags()

    def themes(self):
        return self._themes

    def config(self, mac):
        return self._db.get_controller(mac)

    def log(self):
        return self._log.entries()

    def server_log(self):
        return self._log.entries(source='server')

    def mesh_log(self):
        return self._log.entries(source='mesh')

    # ── show control ─────────────────────────────────────────────────────────

    def _theme(self, name):
        return next((t for t in self._themes if t['name'] == name), None)

    def _change(self, theme, scene):
        t = self._theme(theme)
        cmd = {'type': 'change', 'theme': theme, 'scene': scene}
        if t and t['color']:
            cmd['color'] = t['color']
        # Optimistically update mesh_state so a follow-up next_scene/next_theme
        # call reads the correct theme without waiting for a controller heartbeat.
        if theme is not None:
            self._link.mesh_state['theme'] = theme
        if scene is not None:
            self._link.mesh_state['scene'] = scene
        return self._link.send_command(cmd)

    def next_scene(self):
        t = self._theme(self._link.mesh_state.get('theme'))
        if not t:
            return False
        scenes = t['scenes']
        i = next((i for i, s in enumerate(scenes) if s == self._link.mesh_state.get('scene')), -1)
        return self._change(t['name'], scenes[(i + 1) % len(scenes)])

    def next_theme(self):
        cur = self._link.mesh_state.get('theme')
        i = next((i for i, t in enumerate(self._themes) if t['name'] == cur), -1)
        nxt = self._themes[(i + 1) % len(self._themes)]
        return self._change(nxt['name'], nxt['scenes'][0])

    def random_scene(self):
        """Keep the theme, let each controller pick its own scene."""
        name = self._link.mesh_state.get('theme') or self._themes[0]['name']
        return self._change(name, None)

    def random_theme_scene(self):
        """Random theme; each controller picks its own scene within it."""
        return self._change(random.choice(self._themes)['name'], None)

    def release_solo(self):
        return self._link.send_command({'type': 'solo', 'active': False, 'dim': 1.0})

    def solo_controller(self, mac, dim=0.25):
        return self._link.send_command({'type': 'solo_request', 'dim': float(dim)}, target=mac)

    def solo_tag(self, tag, dim=0.25):
        """Broadcast a tag-group solo — controllers with matching tags become soloists."""
        return self._link.send_command({'type': 'solo_tag', 'tag': tag, 'active': True, 'dim': float(dim)})

    def dim(self, value):
        return self._link.send_command({'type': 'dim', 'dim': float(value)})

    def default_show(self):
        d = self._db.get_defaults()
        if not d.get('unassigned_theme'):
            return False
        return self._change(d['unassigned_theme'], d.get('unassigned_scene'))

    def default_user(self):
        """Send every controller to its own stored personal default scene."""
        return self._link.send_command({'type': 'default'})


    # ── firmware / config push ───────────────────────────────────────────────

    def deploy_all(self):
        self._log.write('Firmware deploy requested — updating all controllers')
        return self._link.send_command({'type': 'ota_update'})

    def deploy_outdated(self):
        version = firmware.current_version(self._root)
        targets = [mac for mac, info in self._link.online().items() if info['fw'] != version]
        for mac in targets:
            self._link.send_command({'type': 'ota_update'}, target=mac)
        self._log.write(f'Deploy to {len(targets)} outdated controller(s)')
        return {'targets': targets}

    def deploy_all_configs(self):
        """Push every stored config to its controller over ESP-NOW."""
        configs = self._db.list_controllers()
        for cfg in configs:
            self._push_config(cfg['mac'], cfg)
        self._log.write(f'Config deploy to {len(configs)} assigned controller(s)')
        return {'pushed': len(configs)}

    def identify(self, mac):
        return self._link.send_command({'type': 'identify'}, target=mac)

    def deploy_controller(self, mac):
        """Send a targeted firmware update to one controller. Config is preserved
        across OTA (device_config.json is at the filesystem root, not in the slot),
        and will be auto-synced on check-in if the DB version is newer."""
        self._log.write(f'Deploy firmware to {short_mac(mac)}')
        return self._link.send_command({'type': 'ota_update'}, target=mac)

    def deploy_controller(self, mac):
        """Send a targeted firmware update to one controller.
        device_config.json lives at the filesystem root and survives OTA, so
        the existing config is automatically preserved after the update."""
        self._log.write(f'Deploy to {mac[-6:].upper()}')
        return self._link.send_command({'type': 'ota_update'}, target=mac)

    def force_leader(self, mac):
        """Force a specific controller to become the bridge leader (admin action)."""
        return self._link.send_command({'type': 'force_leader'}, target=mac)

    def save_config(self, mac, fields, tags=None):
        cfg = self._db.upsert_controller(mac, **fields)
        if tags is not None:
            self._db.set_tags(mac, tags)
            cfg = self._db.get_controller(mac)
        self._push_config(mac, cfg)        # notify the controller to update
        self._log.write(f'Config saved for {cfg.get("nickname") or short_mac(mac)}')
        return cfg

    def push_config(self, mac):
        cfg = self._db.get_controller(mac)
        if not cfg:
            return False
        return self._push_config(mac, cfg)

    def _push_config(self, mac, cfg):
        return self._link.send_command({'type': 'set_config', 'config': _wire_config(cfg)},
                                       target=mac)

    def delete_config(self, mac):
        self._db.delete_controller(mac)
        return True

    def update_defaults(self, fields):
        return self._db.update_defaults(**fields)

    # ── shows ──────────────────────────────────────────────────────────────────

    def shows(self):
        active = self._db.get_active_show()
        return {
            'shows': self._db.list_shows(),
            'active_id': active['id'] if active else None,
        }

    def show(self, show_id):
        return self._db.get_show(int(show_id))

    def save_show(self, show_id, fields, controllers=None, tags=None):
        """Create (show_id falsy) or update a show, plus its roster and tags."""
        if show_id:
            show = self._db.update_show(int(show_id), **fields)
        else:
            name = fields.get('name') or 'New Show'
            rest = {k: v for k, v in fields.items() if k != 'name'}
            show = self._db.create_show(name, **rest)
        sid = show['id']
        if controllers is not None:
            self._db.set_show_controllers(sid, controllers)
        if tags is not None:
            self._db.set_show_tags(sid, tags)
        self._log.write(f'Show saved: {show.get("name")}')
        return self._db.get_show(sid)

    def delete_show(self, show_id):
        self._db.delete_show(int(show_id))
        return True

    def activate_show(self, show_id):
        """Make a show active and push its defaults (theme/scene/color) to the mesh."""
        show = self._db.set_active_show(int(show_id))
        if not show:
            return False
        self._log.write(f'Activated show: {show.get("name")}')
        if show.get('default_theme'):
            return self._change_color(show['default_theme'], show.get('default_scene'),
                                      show.get('default_color'))
        return True

    def deploy_show(self, show_id):
        """Push the active-show defaults to the mesh without changing selection."""
        show = self._db.get_show(int(show_id))
        if not show or not show.get('default_theme'):
            return False
        return self._change_color(show['default_theme'], show.get('default_scene'),
                                  show.get('default_color'))

    def _change_color(self, theme, scene, color):
        """Like _change but with an explicit color override (shows carry their own)."""
        cmd = {'type': 'change', 'theme': theme, 'scene': scene}
        if color:
            cmd['color'] = _parse_color(color)
        if theme is not None:
            self._link.mesh_state['theme'] = theme
        if scene is not None:
            self._link.mesh_state['scene'] = scene
        return self._link.send_command(cmd)


def _wire_config(cfg):
    """The subset of a config a controller needs, in a compact form."""
    return {
        'nickname': cfg.get('nickname'),
        'strips': [cfg.get('strip1_leds', 0), cfg.get('strip2_leds', 0), cfg.get('strip3_leds', 0)],
        'default_theme': cfg.get('default_theme'),
        'default_scene': cfg.get('default_scene'),
        'default_color': cfg.get('default_color'),
        'tags': cfg.get('tags', []),   # needed so controllers can answer tag-group solos
        'version': cfg.get('config_version', 1),
    }
