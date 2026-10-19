const MAX = 3;
let root = null;
const live = new Map();

function host() {
  if (!root) {
    root = document.querySelector('#toasts');
    if (!root) {
      root = document.createElement('div');
      root.id = 'toasts';
      document.body.appendChild(root);
    }
  }
  return root;
}

function dismiss(text) {
  const item = live.get(text);
  if (!item) return;
  live.delete(text);
  clearTimeout(item.timer);
  item.el.classList.add('out');
  setTimeout(() => item.el.remove(), 300);
}

export function toast(message, { kind = 'info', ms = 3600 } = {}) {
  const text = String(message || '').trim();
  if (!text) return;
  const known = live.get(text);
  if (known) {
    clearTimeout(known.timer);
    known.timer = setTimeout(() => dismiss(text), ms);
    return;
  }
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.textContent = text;
  host().appendChild(el);
  live.set(text, { el, timer: setTimeout(() => dismiss(text), ms) });
  while (live.size > MAX) dismiss(live.keys().next().value);
}
