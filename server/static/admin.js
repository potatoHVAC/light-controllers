// Admin: mesh stats, firmware deploy, controller list, config editor, defaults.
let THEMES = [];
let bridgeConnected = false;
let activeEditorMac = null;

function themeOptions(sel, value) {
  sel.innerHTML = '<option value="">—</option>' +
    THEMES.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
  if (value) sel.value = value;
}

function setBridgeState(connected) {
  bridgeConnected = connected;
  el('bridge-banner').classList.toggle('hidden', connected);
  document.querySelectorAll('[data-needs-bridge]').forEach(b => { b.disabled = !connected; });
}

// ── hash debug ──────────────────────────────────────────────────────────────

function toggleHashDebug() {
  const box = el('hashdebug');
  if (box.style.display === 'none') {
    box.style.display = 'block';
    api.get('version_detail').then(d => {
      el('hashdetail').innerHTML =
        `<div style="margin-bottom:6px">Version: <b>${d.version}</b></div>` +
        '<table style="font-size:11px;font-family:monospace;border-collapse:collapse;width:100%">' +
        d.files.map(f => {
          const note = f.excluded ? ' <span class="pill warn">excluded</span>'
                     : f.missing  ? ' <span class="pill off">missing</span>'
                     : '';
          return `<tr style="border-bottom:1px solid var(--line)">
            <td style="padding:3px 6px 3px 0;color:var(--text)">${escapeHtml(f.path)}${note}</td>
            <td style="padding:3px 0;color:var(--muted)">${f.sha256 || '—'}</td>
          </tr>`;
        }).join('') + '</table>';
    }).catch(() => { el('hashdetail').textContent = 'Failed to load.'; });
  } else {
    box.style.display = 'none';
  }
}

// ── deploy ───────────────────────────────────────────────────────────────────

function deployFirmware(action) {
  const s = el('fwstatus'); s.textContent = 'Sending…';
  api.post(action).then(d => {
    s.textContent = (d.ok === false) ? 'Failed to reach bridge.'
      : (d.targets ? `Sent to ${d.targets.length} outdated controller(s).` : 'Sent to all.');
  }).catch(() => s.textContent = 'Error.');
}

function deployConfigs() {
  const s = el('cfgdeploystatus'); s.textContent = 'Sending…';
  api.post('deploy_all_configs').then(d => {
    s.textContent = `Pushed to ${d.pushed} assigned controller(s).`;
  }).catch(() => s.textContent = 'Error.');
}

// ── controller list ──────────────────────────────────────────────────────────

function identify(mac) { api.post('identify', { mac }); }

function renderControllers(list) {
  const box = el('controllers');
  if (!list.length) { box.innerHTML = '<div class="muted">None known.</div>'; return; }

  const named   = list.filter(c => c.has_nickname);
  const unnamed = list.filter(c => !c.has_nickname);

  const renderCard = c => `
    <div id="ctrl-${c.mac}" style="${c.online ? '' : 'opacity:0.45'}">
      <div class="card" style="margin:0 0 8px 0;padding:10px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <div style="min-width:0">
            <span class="dot ${c.online ? 'online' : ''}"></span>
            <b>${escapeHtml(c.nickname)}</b>
            ${c.leader ? '<span class="pill on">leader</span>' : ''}
            ${c.outdated && c.online ? '<span class="pill warn">outdated</span>' : ''}
            <div class="muted">${c.mac}${c.fw ? ' · fw ' + c.fw : ''}</div>
            ${c.tags && c.tags.length ? '<div class="tags">' + c.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('') + '</div>' : ''}
          </div>
          <div class="btn-group">
            <button ${(!c.online || !bridgeConnected) ? 'disabled' : ''} onclick="identify('${c.mac}')">Identify</button>
            <button onclick="editController('${c.mac}')">Edit</button>
          </div>
        </div>
      </div>
    </div>`;

  let html = named.map(renderCard).join('');
  if (named.length && unnamed.length) {
    html += '<div style="border-top:1px solid var(--line);margin:4px 0 12px"></div>';
  }
  html += unnamed.map(renderCard).join('');
  box.innerHTML = html;

  // Re-attach editor if one was open
  if (activeEditorMac) {
    const anchor = el('ctrl-' + activeEditorMac);
    if (anchor) {
      anchor.after(el('config-editor'));
    } else {
      closeEditor();
    }
  }
}

// ── inline editor ────────────────────────────────────────────────────────────

function editController(mac) {
  const editor = el('config-editor');

  if (activeEditorMac === mac) {
    closeEditor();
    return;
  }

  activeEditorMac = mac;
  el('cfgstatus').textContent = '';

  api.get('config?mac=' + mac).then(cfg => {
    el('cfg_mac').value = mac;
    el('editortitle').textContent = 'Edit ' + (cfg && cfg.nickname ? cfg.nickname : mac);
    el('cfg_nickname').value = (cfg && cfg.nickname) || '';
    el('cfg_s1').value = cfg ? cfg.strip1_leds : 0;
    el('cfg_s2').value = cfg ? cfg.strip2_leds : 0;
    el('cfg_s3').value = cfg ? cfg.strip3_leds : 0;
    el('cfg_tags').value  = cfg ? (cfg.tags || []).join(', ') : '';
    themeOptions(el('cfg_theme'), cfg && cfg.default_theme);
    el('cfg_scene').value = (cfg && cfg.default_scene) || '';
    el('cfg_color').value = (cfg && cfg.default_color) || '';

    const anchor = el('ctrl-' + mac);
    if (anchor) {
      anchor.after(editor);
      editor.style.display = 'block';
      editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
}

function closeEditor() {
  el('config-editor').style.display = 'none';
  el('editor-anchor').after(el('config-editor')); // park it back at anchor
  activeEditorMac = null;
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
    el('cfgstatus').textContent = bridgeConnected ? 'Saved and pushed.' : 'Saved (bridge offline — not pushed).';
    closeEditor();
    refresh();
  }).catch(() => el('cfgstatus').textContent = 'Error.');
}

function deleteConfig() {
  const mac = el('cfg_mac').value.trim();
  if (!mac || !confirm('Delete config for ' + mac + '?')) return;
  api.post('delete_config', { mac }).then(() => { closeEditor(); refresh(); });
}

// ── defaults ─────────────────────────────────────────────────────────────────

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

// ── refresh ───────────────────────────────────────────────────────────────────

function refresh() {
  api.get('status').then(s => {
    el('count').textContent   = s.controllers;
    el('theme').textContent   = s.theme || '—';
    el('scene').textContent   = s.scene || '—';
    el('dim').textContent     = Math.round((s.dim || 1) * 100) + '%';
    el('version').textContent = s.version;
    el('bridge').innerHTML    = s.connected
      ? `<span class="pill on">Bridge → ${escapeHtml(s.leader_name || '?')}</span>`
      : '<span class="pill off">bridge offline</span>';
    el('auto').innerHTML      = s.autonomous ? '<span class="pill warn">autonomous</span>' : '';
    setBridgeState(s.connected);
  }).catch(() => {});

  // Skip controller list rebuild while an editor is open to preserve its state.
  if (!activeEditorMac) {
    api.get('controllers').then(renderControllers).catch(() => {});
  }

  api.get('defaults').then(d => {
    themeOptions(el('def_show_theme'), d.show_theme);
    el('def_show_scene').value = d.show_scene || '';
    themeOptions(el('def_theme'), d.unassigned_theme);
    el('def_scene').value = d.unassigned_scene || '';
    el('def_color').value = d.unassigned_color || '';
    el('def_s1').value = d.unassigned_strip1_leds;
    el('def_s2').value = d.unassigned_strip2_leds;
    el('def_s3').value = d.unassigned_strip3_leds;
  }).catch(() => {});

  api.get('server_log').then(e => renderLog(e, 'server-log')).catch(() => {});
  api.get('mesh_log').then(e => renderLog(e, 'mesh-log')).catch(() => {});
}

api.get('themes').then(t => { THEMES = t; refresh(); });
setInterval(refresh, 3000);