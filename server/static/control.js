// Control panel: live status, show controls, and a soloist grid.
let soloing = null;
let bridgeConnected = false;

function act(action) {
  api.post(action).then(refresh);
  if (action === 'release_solo') soloing = null;
}

function soloController(mac) {
  if (!bridgeConnected) return;
  soloing = mac;
  api.post('solo', { mac }).then(refresh);
}

function setBridgeState(connected) {
  bridgeConnected = connected;
  el('bridge-banner').classList.toggle('hidden', connected);
  document.querySelectorAll('[data-needs-bridge]').forEach(b => { b.disabled = !connected; });
}

function refresh() {
  api.get('status').then(s => {
    el('theme').textContent = s.theme || '—';
    el('scene').textContent = s.scene || '—';
    el('dim').textContent   = Math.round((s.dim || 1) * 100) + '%';
    el('count').textContent = s.controllers;
    el('bridge').innerHTML  = pill(s.connected, 'bridge connected', 'bridge offline');
    el('auto').innerHTML    = s.autonomous ? '<span class="pill warn">autonomous</span>' : '';
    setBridgeState(s.connected);
  }).catch(() => {});

  api.get('controllers').then(list => {
    const grid = el('grid');
    if (!list.length) { grid.innerHTML = '<div class="muted">No controllers online.</div>'; return; }
    grid.innerHTML = list.map(c => {
      const cls = ['ctrl'];
      if (!c.online) cls.push('offline');
      if (c.leader) cls.push('leader');
      if (c.mac === soloing) cls.push('soloing');
      const clickable = c.online && bridgeConnected;
      if (clickable) cls.push('clickable');
      const onclick = clickable ? `onclick="soloController('${c.mac}')"` : '';
      return `<div class="${cls.join(' ')}" ${onclick}>
        <div class="name">${escapeHtml(c.nickname)}</div>
        <div class="meta">${c.online ? (c.theme || '—') : 'offline'}</div>
      </div>`;
    }).join('');
  }).catch(() => {});

  api.get('log').then(renderLog).catch(() => {});
}

setInterval(refresh, 2000);
refresh();