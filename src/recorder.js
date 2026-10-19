const TYPES = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];

function pickType() {
  if (typeof MediaRecorder === 'undefined' || typeof HTMLCanvasElement.prototype.captureStream !== 'function') return null;
  return TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || null;
}

export function createRecorder(canvas, { fps = 60, bitrate = 12_000_000 } = {}) {
  const mime = pickType();
  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;

  return {
    supported: !!mime,
    mime,
    get recording() {
      return !!recorder;
    },
    get elapsed() {
      return recorder ? (performance.now() - startedAt) / 1000 : 0;
    },
    start() {
      if (recorder) return;
      stream = canvas.captureStream(fps);
      chunks = [];
      const next = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: bitrate });
      next.ondataavailable = (e) => {
        if (e.data && e.data.size) chunks.push(e.data);
      };
      next.start(1000);
      recorder = next;
      startedAt = performance.now();
    },
    stop() {
      const active = recorder;
      recorder = null;
      if (!active) return Promise.resolve(null);
      return new Promise((resolve, reject) => {
        active.onstop = () => {
          stream?.getTracks().forEach((t) => t.stop());
          stream = null;
          resolve(new Blob(chunks, { type: 'video/webm' }));
        };
        active.onerror = (e) => reject(e.error || new Error('la grabación falló'));
        active.stop();
      });
    },
  };
}

export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
