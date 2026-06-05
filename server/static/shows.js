// Shows editor: list shows, add/edit/delete/deploy, select the active show.
let THEMES        = [];
let CONTROLLERS   = [];   // known controllers (for the roster picker)
let activeEditId  = null; // show id currently being edited, or 0 for a new show

function themeOptions(sel, value) {
  sel.innerHTML = '<option value="">—</option>' +
    THEMES.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
  if (value) sel.value = value;
}

function sceneOptions(sel, themeName, currentScene) {
  const theme = THEMES.find(t => t.name === themeName);
  const scenes = theme ? theme.scenes : [];
  sel.innerHTML = '<option value="">—</option>' +
    scenes.map(s => `<option value="${s}">${s}</option>`).join('');
  if (currentScene) sel.value = currentScene;
}

// ── list ──────────────────────────────────────────────────────────────────────

function refresh() {
  api.get('shows').then(d => {
    const list = el('shows-list');
    // Active-show selector
    const sel = el('active-select');
    sel.innerHTML = '<option value="">— none —</option>' +
      d.shows.map(s => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('');
    if (d.active_id) sel.value = d.active_id;

    if (!d.shows.length) {
      list.innerHTML = '<div class="muted">No shows yet. Add one above.</div>';
      return;
    }
    list.innerHTML = d.shows.map(s => {
      const def = [s.default_theme, s.default_scene, s.default_color]
        .filter(Boolean).join(' · ') || 'no defaults';
      const isActive = s.id === d.active_id;
      return `<div id="show-${s.id}">
        <div class="card" style="margin:0 0 8px 0;padding:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
            <div style="min-width:0">
              <b>${escapeHtml(s.name)}</b>
              ${isActive ? '<span class="pill on">active</span>' : ''}
              <div class="muted">${escapeHtml(def)} · ${s.controllers.length} controller(s)</div>
            </div>
            <div class="btn-group">
              <button class="warnbtn" onclick="selectShow(${s.id})">Select</button>
              <button onclick="editShow(${s.id})">Edit</button>
              <button class="danger" onclick="deleteShowById(${s.id}, '${escapeHtml(s.name)}')">Delete</button>
            </div>
          </div>
        </div>
      </div>`;
    }).join('');

    // re-attach editor if open
    if (activeEditId) {
      const anchor = activeEditId === 0 ? el('new-show-anchor') : el('show-' + activeEditId);
      if (anchor) anchor.after(el('show-editor'));
      else closeEditor();
    }
  });
}

// ── activate / deploy ─────────────────────────────────────────────────────────

function activateSelected() {
  const id = el('active-select').value;
  if (!id) return;
  api.post('activate_show', { id: +id }).then(refresh);
}

function selectShow(id) {
  // Make this show active and apply its theme/scene/color to the rig.
  api.post('activate_show', { id }).then(refresh);
}

function deleteShowById(id, name) {
  if (!confirm('Delete show "' + name + '"? Controller configs are not affected.')) return;
  api.post('delete_show', { id }).then(() => { if (activeEditId === id) closeEditor(); refresh(); });
}

// ── editor ────────────────────────────────────────────────────────────────────

function renderRoster(selectedMacs) {
  const sel = new Set(selectedMacs || []);
  el('show_roster').innerHTML = CONTROLLERS.length
    ? CONTROLLERS.map(c => `
        <label class="roster-item">
          <input type="checkbox" value="${c.mac}" ${sel.has(c.mac) ? 'checked' : ''}>
          ${escapeHtml(c.nickname)} <span class="muted">${c.mac.slice(-6)}</span>
        </label>`).join('')
    : '<div class="muted">No known controllers yet.</div>';
}

function rosterSelection() {
  return [...el('show_roster').querySelectorAll('input:checked')].map(i => i.value);
}

function newShow() {
  activeEditId = 0;
  el('show-editor-title').textContent = 'New show';
  el('show_id').value = '';
  el('show_name').value = '';
  themeOptions(el('show_theme'), '');
  sceneOptions(el('show_scene'), '', '');
  el('show_color').value = '';
  el('show_tags').value = '';
  renderRoster([]);
  el('show-status').textContent = '';
  const editor = el('show-editor');
  el('new-show-anchor').after(editor);
  editor.style.display = 'block';
  editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function editShow(id) {
  if (activeEditId === id) { closeEditor(); return; }
  api.get('show?id=' + id).then(s => {
    activeEditId = id;
    el('show-editor-title').textContent = 'Edit ' + s.name;
    el('show_id').value = s.id;
    el('show_name').value = s.name || '';
    themeOptions(el('show_theme'), s.default_theme);
    sceneOptions(el('show_scene'), s.default_theme, s.default_scene);
    el('show_color').value = s.default_color || '';
    el('show_tags').value = (s.tags || []).join(', ');
    renderRoster(s.controllers);
    el('show-status').textContent = '';
    const editor = el('show-editor');
    el('show-' + id).after(editor);
    editor.style.display = 'block';
    editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
}

function saveShow() {
  const id = el('show_id').value;
  const body = {
    id: id ? +id : null,
    fields: {
      name: el('show_name').value.trim() || 'New Show',
      default_theme: el('show_theme').value || null,
      default_scene: el('show_scene').value || null,
      default_color: el('show_color').value.trim() || null,
    },
    controllers: rosterSelection(),
    tags: el('show_tags').value.split(',').map(t => t.trim()).filter(Boolean),
  };
  el('show-status').textContent = 'Saving…';
  api.post('save_show', body).then(() => { closeEditor(); refresh(); });
}

function deleteShow() {
  const id = el('show_id').value;
  if (!id || !confirm('Delete this show? Controller configs are not affected.')) return;
  api.post('delete_show', { id: +id }).then(() => { closeEditor(); refresh(); });
}

function closeEditor() {
  el('show-editor').style.display = 'none';
  el('new-show-anchor').after(el('show-editor'));   // park it
  activeEditId = null;
}

// ── init ──────────────────────────────────────────────────────────────────────

Promise.all([api.get('themes'), api.get('controllers')]).then(([themes, controllers]) => {
  THEMES = themes;
  CONTROLLERS = controllers.filter(c => c.has_nickname)
    .concat(controllers.filter(c => !c.has_nickname))
    .sort((a, b) => a.nickname.localeCompare(b.nickname));
  refresh();
});
setInterval(refresh, 5000);
