// Shared API helpers and small DOM utilities.
const api = {
  get:  (p)      => fetch('/api/' + p).then(r => r.json()),
  post: (p, b)   => fetch('/api/' + p, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify(b || {}),
                    }).then(r => r.json()),
};

const el = (id) => document.getElementById(id);

function renderLog(entries, targetId = 'log') {
  const box = el(targetId);
  if (!box || !entries || !entries.length) return;
  box.innerHTML = entries.slice(-200)
    .map(e => `<div class="entry ${e.type}">${escapeHtml(e.msg)}</div>`).join('');
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function pill(on, onText, offText) {
  return `<span class="pill ${on ? 'on' : 'off'}">${on ? onText : offText}</span>`;
}
