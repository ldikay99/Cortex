const OFFLINE = 'no se pudo conectar con el analizador';

function failure(status) {
  if (status === 413) return 'el archivo es demasiado grande para el analizador';
  if (status === 404) return 'el analizador no reconoce esa petición';
  if (status >= 502 && status <= 504) return 'el analizador no está disponible ahora mismo';
  return `el analizador respondió con un error (${status})`;
}

async function request(url, init = {}) {
  let res;
  try {
    res = await fetch(url, { cache: 'no-store', ...init });
  } catch {
    throw new Error(OFFLINE);
  }
  const out = await res.json().catch(() => null);
  if (!res.ok) throw new Error(out?.error || failure(res.status));
  if (!out) throw new Error('el analizador envió una respuesta que no se pudo leer');
  return out;
}

const post = (url, body, type) => request(url, { method: 'POST', body, headers: type ? { 'Content-Type': type } : {} });
const json = (value) => JSON.stringify(value);

export async function checkAnalyzer() {
  try {
    return await request('api/status');
  } catch {
    return null;
  }
}

export const uploadProject = (body, name) => post(`api/upload?name=${encodeURIComponent(name)}`, body);
export const cloneGithub = (url) => post('api/github', json({ url }), 'application/json');
export const analyzeProject = (opts) => post('api/analyze', json(opts), 'application/json');
export const openSaved = (project, version) => post('api/open', json({ project, version }), 'application/json');
export const updateSaved = (project) => post('api/update', json({ project }), 'application/json');
export const importGraph = (file) => post('api/import', file, 'application/json');
export const getTree = () => request('api/tree');
export const listSaved = async () => (await request('api/projects')).projects || [];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function streamProject(hooks, { rate = 4000, retries = 6 } = {}) {
  let received = 0;
  let attempt = 0;
  let stopped = false;

  function handle(o) {
    if (o.t === 'analyzing' || o.t === 'cloning') hooks.onWaiting(o.t, o.project);
    else if (o.t === 'meta') hooks.onMeta(o);
    else if (o.t === 'batch') {
      let nodes = 0;
      for (const it of o.items) if (it.t === 'node') nodes++;
      received = Number.isFinite(o.done) ? Math.max(received, o.done) : received + nodes;
      if (attempt) hooks.onResumed?.();
      attempt = 0;
      hooks.onItems(o.items, o.done, o.total);
    } else if (o.t === 'done') {
      hooks.onDone(o.stats);
      return 'done';
    } else if (o.t === 'error') {
      hooks.onError(o.error || 'el análisis falló');
      return 'fatal';
    } else if (o.t === 'idle' || o.t === 'review') {
      hooks.onError('no hay ningún proyecto listo para tejer');
      return 'fatal';
    }
    return null;
  }

  async function connect() {
    let res;
    try {
      res = await fetch(`api/stream?rate=${rate}${received ? `&from=${received}` : ''}`, { cache: 'no-store' });
    } catch {
      return 'dropped';
    }
    if (!res.ok || !res.body) return 'dropped';
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      let chunk;
      try {
        chunk = await reader.read();
      } catch {
        return 'dropped';
      }
      if (chunk.done) return 'dropped';
      buf += decoder.decode(chunk.value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line) continue;
        let o;
        try {
          o = JSON.parse(line);
        } catch {
          continue;
        }
        const outcome = handle(o);
        if (outcome) {
          reader.cancel().catch(() => {});
          return outcome;
        }
      }
    }
  }

  (async () => {
    for (;;) {
      const outcome = await connect();
      if (outcome !== 'dropped' || stopped) return;
      if (attempt >= retries) {
        hooks.onError(OFFLINE, { lost: true });
        return;
      }
      const wait = Math.min(16000, 1000 * 2 ** attempt);
      attempt++;
      hooks.onReconnect?.(attempt, retries);
      await sleep(wait);
      if (stopped) return;
    }
  })().catch((err) => hooks.onError(err?.message || String(err)));

  return {
    stop() {
      stopped = true;
    },
    get received() {
      return received;
    },
  };
}
