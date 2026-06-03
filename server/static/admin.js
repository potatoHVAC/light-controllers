// Admin: mesh stats, firmware deploy, controller list, config editor, defaults.
let THEMES = [];

function themeOptions(sel, value) {
  sel.innerHTML = '<option value="">—</option>' +
    THEMES.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
  if (value) sel.value = value;
}

function deploy(action) {
  const s = el('deploystatus'); s.textContent = 'Sending…';
  api.post(action).then(d => {
    s.textContent = (d.ok === false) ? 'Failed to reach bridge.'
      : (d.targets ? `Sent to ${d.targets.length} outdated controller(s).` : 'Sent to all.');
  }).catch(() => s.textContent = 'Error.');
}

function identify(mac) { api.post('identify', { mac }); }

function editController(mac) {
  api.get('config?mac=' + mac).then(cfg => {
    el('cfg_mac').value      = mac;
    el('editortitle').textContent = 'Edit ' + mac;
    el('cfg_nickname').value = (cfg && cfg.nickname) || '';
    el('cfg_s1').value = cfg ? cfg.strip1_leds : 0;
    el('cfg_s2').value = cfg ? cfg.strip2_leds : 0;
    el('cfg_s3').value = cfg ? cfg.strip3_leds : 0;
    el('cfg_tags').value  = cfg ? (cfg.tags || []).join(', ') : '';
    themeOptions(el('cfg_theme'), cfg && cfg.default_theme);
    el('cfg_scene').value = (cfg && cfg.default_scene) || '';
    el('cfg_color').value = (cfg && cfg.default_color) || '';
    window.scrollTo(0, document.body.scrollHeight);
  });
}

function clearEditor() {
  ['cfg_mac', 'cfg_nickname', 'cfg_tags', 'cfg_scene', 'cfg_color'].forEach(i => el(i).value = '');
  ['cfg_s1', 'cfg_s2', 'cfg_s3'].forEach(i => el(i).value = 0);
  el('editortitle').textContent = 'Add config (enter a MAC)';
  el('cfg_mac').value = '';
  themeOptions(el('cfg_theme'), '');
}

function saveConfig() {
  const mac = el('cfg_mac').value.trim() || prompt('Controller MAC?');
  if (!mac) return;
  const body = {
    mac,
    fields: {
      nickname: el('cfg_nickname').value.trim() || null,
      strip1_leds: +el('cfg_s1').value || 0,
      strip2_leds: +el('cfg_s2').value || 0,
      strip3_leds: +el('cfg_s3').value || 0,
      default_theme: el('cfg_theme').value || null,
      default_scene: el('cfg_scene').value.trim() || null,
      default_color: el('cfg_color').value.trim() || null,
    },
    tags: el('cfg_tags').value.split(',').map(t => t.trim()).filter(Boolean),
  };
  el('cfgstatus').textContent = 'Saving…';
  api.post('save_config', body).then(() => {
    el('cfgstatus').textContent = 'Saved and pushed.';
    refresh();
  }).catch(() => el('cfgstatus').textContent = 'Error.');
}

function deleteConfig() {
  const mac = el('cfg_mac').value.trim();
  if (!mac || !confirm('Delete config for ' + mac + '?')) return;
  api.post('delete_config', { mac }).then(() => { clearEditor(); refresh(); });
}

function saveDefaults() {
  const fields = {
    show_theme: el('def_show_theme').value || null,
    show_scene: el('def_show_scene').value.trim() || null,
    unassigned_theme: el('def_theme').value || null,
    unassigned_scene: el('def_scene').value.trim() || null,
    unassigned_color: el('def_color').value.trim() || null,
    unassigned_strip1_leds: +el('def_s1').value || 0,
    unassigned_strip2_leds: +el('def_s2').value || 0,
    unassigned_strip3_leds: +el('def_s3').value || 0,
  };
  el('defstatus').textContent = 'Saving…';
  api.post('defaults', { fields }).then(() => el('defstatus').textContent = 'Saved.');
}

function refresh() {
  api.get('status').then(s => {
    el('count').textContent  = s.controllers;
    el('theme').textContent  = s.theme || '—';
    el('scene').textContent  = s.scene || '—';
    el('dim').textContent    = Math.round((s.dim || 1) * 100) + '%';
    el('version').textContent = s.version;
    el('bridge').innerHTML   = pill(s.connected, 'bridge connected', 'bridge offline');
    el('auto').innerHTML     = s.autonomous ? '<span class="pill warn">autonomous</span>' : '';
  }).catch(() => {});

  api.get('controllers').then(list => {
    const box = el('controllers');
    if (!list.length) { box.innerHTML = '<div class="muted">None known.</div>'; return; }
    box.innerHTML = list.map(c => `
      <div class="card" style="margin:0 0 8px 0;padding:10px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <span class="dot ${c.online ? 'online' : ''}"></span>
            <b>${escapeHtml(c.nickname)}</b>
            ${c.leader ? '<span class="pill on">leader</span>' : ''}
            ${c.outdated && c.online ? '<span class="pill warn">outdated</span>' : ''}
            <div class="muted">${c.mac}${c.fw ? ' · fw ' + c.fw : ''}</div>
            ${c.tags && c.tags.length ? '<div class="tags">' + c.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('') + '</div>' : ''}
          </div>
          <div class="row" style="margin:0;flex:0">
            ${c.online ? `<button onclick="identify('${c.mac}')">Identify</button>` : ''}
            <button onclick="editController('${c.mac}')">Edit</button>
          </div>
        </div>
      </div>`).join('');
  }).catch(() => {});

  api.get('defaults').then(d => {
    themeOptions(el('def_show_theme'), d.show_theme);
    el('def_show_scene').value = d.show_scene || '';
    themeOptions(el('def_theme'), d.unassigned_theme);
    el('def_scene').value = d.unassigned_scene || '';
    el('def_color').value = d.unassigned_color || '';
    el('def_s1').value = d.unassigned_strip1_leds; el('def_s2').value = d.unassigned_strip2_leds; el('def_s3').value = d.unassigned_strip3_leds;
  }).catch(() => {});

  api.get('log').then(renderLog).catch(() => {});
}

api.get('themes').then(t => { THEMES = t; clearEditor(); refresh(); });
setInterval(refresh, 3000);
