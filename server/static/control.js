// Control panel: live status, show controls, and a soloist grid.
let soloing    = null;   // mac of soloing controller, or null
let soloingTag = null;   // tag name being soloed, or null
let bridgeConnected  = false;
let lightsOffActive  = false;
let dimBeforeLightsOff = 100;

function bgDim() { return parseInt(el('bgdimslider').value) / 100; }

function updateReleaseSoloBtn() {
  el('release-solo-btn').classList.toggle('available', soloing !== null || soloingTag !== null);
}

function act(action) {
  api.post(action).then(refresh);
  if (action === 'release_solo') { soloing = null; soloingTag = null; updateReleaseSoloBtn(); }
}

function soloController(mac) {
  if (!bridgeConnected) return;
  if (soloing === mac) { act('release_solo'); return; }   // double-tap releases
  soloing = mac;
  soloingTag = null;
  updateReleaseSoloBtn();
  api.post('solo', { mac, dim: bgDim() }).then(refresh);
}

function soloTag(tag) {
  if (!bridgeConnected) return;
  if (soloingTag === tag) { act('release_solo'); return; }  // double-tap releases
  soloingTag = tag;
  soloing = null;
  updateReleaseSoloBtn();
  api.post('solo_tag', { tag, dim: bgDim() }).then(refresh);
}

function onDimChange(input) {
  if (lightsOffActive) releaseLightsOff(false);
  api.post('dim', { dim: input.value / 100 });
}

function onBgDimChange() {
  // Re-send the active solo so non-soloists update live to the new level.
  if (!bridgeConnected) return;
  if (soloing)         api.post('solo', { mac: soloing, dim: bgDim() });
  else if (soloingTag) api.post('solo_tag', { tag: soloingTag, dim: bgDim() });
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
    el('bridge').innerHTML  = s.connected
      ? `<span class="pill on">Bridge → ${escapeHtml(s.leader_name || '?')}</span>`
      : '<span class="pill off">bridge offline</span>';
    el('auto').innerHTML    = s.autonomous ? '<span class="pill warn">autonomous</span>' : '';
    setBridgeState(s.connected);
  }).catch(() => {});

  api.get('controllers').then(list => {
    // no-solo tag removes a controller from individual solo selection
    // (they can still participate in tag-group solos)
    const named = list.filter(c => c.has_nickname && !(c.tags || []).includes('no-solo'));

    // Soloist grid
    const grid = el('grid');
    if (!named.length) {
      grid.innerHTML = '<div class="muted">No controllers online.</div>';
    } else {
      grid.innerHTML = named.map(c => {
        const cls = ['ctrl'];
        if (!c.online) cls.push('offline');
        if (c.leader)  cls.push('leader');
        if (c.mac === soloing) cls.push('soloing');
        const clickable = c.online && bridgeConnected;
        if (clickable) cls.push('clickable');
        const onclick = clickable ? `onclick="soloController('${c.mac}')"` : '';
        return `<div class="${cls.join(' ')}" ${onclick}>
          <div class="name">${escapeHtml(c.nickname)}</div>
        </div>`;
      }).join('');
    }

    // Tag solo buttons — one per active tag across online named controllers
    const activeTags = [...new Set(
      named.filter(c => c.online).flatMap(c => c.tags || [])
    )].sort();
    el('tag-solo-btns').innerHTML = activeTags.map(tag => {
      const active = tag === soloingTag;
      return `<button data-needs-bridge ${!bridgeConnected ? 'disabled' : ''}
        class="tag-solo${active ? ' active' : ''}"
        onclick="soloTag('${escapeHtml(tag)}')">${escapeHtml(tag)}</button>`;
    }).join('');
  }).catch(() => {});
}

setInterval(refresh, 2000);
refresh();