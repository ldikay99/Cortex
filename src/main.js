import { toast } from './toast.js';

const describe = (value) => {
  if (!value) return 'error desconocido';
  if (typeof value === 'string') return value;
  return value.message || String(value);
};

window.addEventListener('error', (e) => {
  if (!e.message && !e.error) return;
  toast(`algo salió mal: ${describe(e.error || e.message)}`, { kind: 'error', ms: 5200 });
});
window.addEventListener('unhandledrejection', (e) => {
  toast(`algo salió mal: ${describe(e.reason)}`, { kind: 'error', ms: 5200 });
});

function webgl2() {
  try {
    const probe = document.createElement('canvas');
    const gl = probe.getContext('webgl2');
    if (!gl) return false;
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
}

function fallback() {
  document.querySelector('#fallback').hidden = false;
  document.querySelector('#topbar').hidden = true;
  document.querySelector('#tools').hidden = true;
  document.querySelector('#follow').hidden = true;
  document.querySelector('#hint').hidden = true;
}

if (!webgl2()) fallback();
else
  import('./cortex.js').catch((err) => {
    if (String(err?.message || err).startsWith('webgl')) return fallback();
    toast(`Córtex no pudo arrancar: ${describe(err)}`, { kind: 'error', ms: 8000 });
    console.error(err);
  });
