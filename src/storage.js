const area = (kind) => {
  try {
    return kind === 'session' ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
};

export function load(key, fallback = null, kind = 'local') {
  try {
    const value = area(kind)?.getItem(key);
    return value === null || value === undefined ? fallback : value;
  } catch {
    return fallback;
  }
}

export function save(key, value, kind = 'local') {
  try {
    area(kind)?.setItem(key, String(value));
  } catch {}
}

export function forget(key, kind = 'local') {
  try {
    area(kind)?.removeItem(key);
  } catch {}
}
