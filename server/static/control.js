// Control panel: live status, show controls, and a soloist grid.
let soloing = null;
let bridgeConnected = false;
let lightsOffActive = false;
let dimBeforeLightsOff = 100;

function act(action) {
  api.post(action).then(refresh);
  if (action === 'release_solo') soloing = null;
}

function soloController(mac) {
  if (!bridgeConnected) return;
  soloing = mac;
  api.post('solo', { mac }).then(refresh);
}

function onDimChange(input) {
  // Manual slider move releases lights-off without restoring the saved level.
  if (lightsOffActive) releaseLightsOff(false);
  api.post('dim', { dim: input.value / 100 });
}

function toggleLightsOff() {
  if (lightsOffActive) {
    releaseLightsOff(true);
  } else {
    dimBeforeLightsOff = parseInt(el('dimslider').value);
    lightsOffActive = true;
    el('lights-off-btn').classList.add('lights-off-active');
    el('dimslider').value = 0;
    el('dimval').textContent = '0';
    api.post('dim', { dim: 0 });
  }
}

function releaseLightsOff(restore) {
  lightsOffActive = false;
  el('lights-off-btn').classList.remove('lights-off-active');
  if (restore) {
    el('dimslider').value = dimBeforeLightsOff;
    el('dimval').textContent = dimBeforeLightsOff;
    api.post('dim', { dim: dimBeforeLightsOff / 100 });
  }
}

function setBridgeState(connected) {
  bridgeConnected = connected;
  el('bridge-banner').classList.toggle('hidden', connected);
  if (!connected && lightsOffActive) releaseLightsOff(false);
  document.querySelectorAll('[data-needs-bridge]').forEach(b => { b.disabled = !connected; });
}

function refresh() {
  api.get('status').then(s => {
    el('theme').textContent = s.theme || '—';
    el('scene').textContent = s.scene || '—';
    el('dim').textContent   = Math.round((s.dim || 0) * 100) + '%';
    el('count').textContent = s.controllers;
    el('bridge').innerHTML  = pill(s.connected, 'bridge connected', 'bridge offline');
    el('auto').innerHTML    = s.autonomous ? '<span class="pill warn">autonomous</span>' : '';
    setBridgeState(s.connected);
  }).catch(() => {});

  api.get('controllers').then(list => {
    const grid = el('grid');
    const named = list.filter(c => c.has_nickname);

    if (!named.length) { grid.innerHTML = '<div class="muted">No controllers online.</div>'; return; }
    grid.innerHTML = named.map(c => {
      const cls = ['ctrl'];
      if (!c.online) cls.push('offline');
      if (c.leader) cls.push('leader');
      if (c.mac === soloing) cls.push('soloing');
      const clickable = c.online && bridgeConnected;
      if (clickable) cls.push('clickable');
      const onclick = clickable ? `onclick="soloController('${c.mac}')"` : '';
      return `<div class="${cls.join(' ')}" ${onclick}>
        <div class="name">${escapeHtml(c.nickname)}</div>
      </div>`;
    }).join('');
  }).catch(() => {});
}

setInterval(refresh, 2000);
refresh();