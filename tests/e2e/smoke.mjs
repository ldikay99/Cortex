import fs from 'node:fs';
import { chromium } from 'playwright-core';

const BASE = (process.env.CORTEX_URL || 'http://localhost:8090').replace(/\/$/, '');
const CHROME = process.env.CHROME_PATH || '/usr/bin/google-chrome';
const SAVED = process.env.CORTEX_SAVED || 'excalidraw';
const ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'];

const errors = [];
let failures = 0;

async function step(name, fn) {
  const t0 = Date.now();
  try {
    await fn();
    console.log(`  ok    ${name} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
  } catch (err) {
    failures++;
    console.log(`  FALLO ${name}: ${err.message.split('\n')[0]}`);
  }
}

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

async function waitFor(page, fn, arg, timeout, message) {
  try {
    await page.waitForFunction(fn, arg, { timeout, polling: 500 });
  } catch {
    throw new Error(message);
  }
}

const visible = (page, sel) => page.$eval(sel, (el) => !el.hidden && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none');

const browser = await chromium.launch({ executablePath: CHROME, args: ARGS });
const context = await browser.newContext({ viewport: { width: 1280, height: 760 }, acceptDownloads: true });
const page = await context.newPage();
page.on('pageerror', (e) => errors.push(e.message));
page.setDefaultTimeout(30000);

console.log(`Córtex smoke · ${BASE}`);

await step('carga la página y abre el selector de proyectos', async () => {
  await page.goto(`${BASE}/`, { waitUntil: 'load' });
  await waitFor(page, () => window.__cortex && !document.querySelector('#uploader').hidden, null, 30000, 'el selector no se abrió');
  if (await visible(page, '#review-view')) await page.click('#review-cancel');
  assert(await visible(page, '#pick-view'), 'la vista de elección no es visible');
  assert(!(await page.$('meta[name="grok-project-id"]')), 'quedan metadatos de Grok');
});

await step('la ayuda se abre y se cierra', async () => {
  await page.click('#help-btn');
  assert(await visible(page, '#help'), 'la ayuda no se abrió');
  const credits = await page.textContent('#help .credits');
  assert(credits.includes('Jonathan C') && credits.includes('ldikay99'), 'faltan los créditos');
  await page.keyboard.press('Escape');
  assert(!(await visible(page, '#help')), 'Esc no cerró la ayuda');
  await page.keyboard.press('?');
  assert(await visible(page, '#help'), 'la tecla ? no abrió la ayuda');
  await page.mouse.click(8, 380);
  assert(!(await visible(page, '#help')), 'el clic afuera no cerró la ayuda');
});

await step('la leyenda explica los tipos de nodo y los puentes', async () => {
  await page.keyboard.press('?');
  assert(await visible(page, '#help'), 'la ayuda no se abrió');
  const text = await page.textContent('#help .card');
  for (const word of ['endpoint HTTP', 'paquete', 'variable', 'tópico', 'Puentes', 'RPC', 'ver el código']) assert(text.includes(word), `la leyenda no menciona «${word}»`);
  const shapes = await page.$$eval('#help .legend .shape, #help .legend .thread', (els) => els.length);
  assert(shapes >= 8, `faltan símbolos en la leyenda (${shapes})`);
  await page.keyboard.press('Escape');
  assert(!(await visible(page, '#help')), 'Esc no cerró la ayuda');
});

await step('el selector de velocidad cambia y se recuerda', async () => {
  await page.click('#speed');
  assert(await visible(page, '#settings'), 'el panel de velocidad no se abrió');
  await page.click('#settings [data-speed="2"]');
  assert((await page.textContent('#speed')).trim() === '2×', 'el botón no muestra 2×');
  assert((await page.evaluate(() => window.__cortex.speed)) === 2, 'la velocidad interna no cambió');
  await page.reload({ waitUntil: 'load' });
  await waitFor(page, () => !!window.__cortex, null, 30000, 'la página no volvió a cargar');
  assert((await page.textContent('#speed')).trim() === '2×', 'la velocidad no se recordó tras recargar');
  assert((await page.evaluate(() => localStorage.getItem('cortex-velocidad'))) === '2', 'no quedó en localStorage');
});

await step('el modo cine oculta la interfaz y la restaura', async () => {
  await page.mouse.click(640, 600);
  await page.keyboard.press('h');
  await waitFor(page, () => document.body.classList.contains('cine'), null, 5000, 'H no activó el modo cine');
  const hidden = await page.$eval('#topbar', (el) => getComputedStyle(el).visibility === 'hidden');
  const toolsHidden = await page.$eval('#tools', (el) => getComputedStyle(el).visibility === 'hidden');
  assert(hidden && toolsHidden, 'la barra superior sigue visible en modo cine');
  await page.keyboard.press('Escape');
  await waitFor(page, () => !document.body.classList.contains('cine'), null, 5000, 'Esc no salió del modo cine');
  assert(await page.$eval('#topbar', (el) => getComputedStyle(el).visibility === 'visible'), 'la barra no volvió');
  await page.click('#cine');
  assert(await page.evaluate(() => document.body.classList.contains('cine')), 'el botón no activó el modo cine');
  await page.keyboard.press('h');
  assert(!(await page.evaluate(() => document.body.classList.contains('cine'))), 'H no salió del modo cine');
});

await step('grabar un reel produce un archivo no vacío', async () => {
  assert(await page.evaluate(() => window.__cortex.recorder.supported), 'MediaRecorder no está disponible');
  await page.click('#record');
  await waitFor(page, () => window.__cortex.recorder.recording, null, 5000, 'la grabación no empezó');
  assert(await visible(page, '#rec-chip'), 'no aparece el indicador REC');
  await page.waitForTimeout(2500);
  const [download] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), page.click('#record')]);
  const name = download.suggestedFilename();
  assert(/^cortex-[a-z0-9._-]+-\d{8}-\d{4}\.webm$/.test(name), `nombre inesperado: ${name}`);
  const size = fs.statSync(await download.path()).size;
  assert(size > 0, 'el archivo descargado está vacío');
  const last = await page.evaluate(() => window.__cortex.lastRecording);
  assert(last && last.size > 0, 'el gancho de prueba no registró el blob');
  console.log(`        ${name} · ${(size / 1024).toFixed(1)} KB`);
});

await step(`abrir el grafo guardado «${SAVED}» empieza a tejer`, async () => {
  await page.goto(`${BASE}/?velocidad=4`, { waitUntil: 'load' });
  await waitFor(page, (name) => [...document.querySelectorAll('#saved-list li')].some((li) => li.textContent.includes(name)), SAVED, 30000, 'el grafo guardado no aparece');
  assert((await page.evaluate(() => window.__cortex.speed)) === 4, '?velocidad=4 no tuvo efecto');
  const li = page.locator('#saved-list li', { hasText: SAVED }).first();
  await li.locator('[data-act=open]').click();
  await waitFor(page, () => (window.__cortex.project.woven || 0) > 0, null, 240000, 'no avanzó el tejido');
  const width = await page.$eval('#progress i', (el) => parseFloat(el.style.width) || 0);
  assert(width > 0, 'la barra de progreso sigue en 0');
});

await step('el panel de comunidades lista al menos una', async () => {
  await waitFor(page, () => window.__cortex.cosmos.regions.length > 1, null, 120000, 'no llegó ninguna comunidad');
  await page.click('#comms-chip');
  assert(await visible(page, '#comms'), 'el panel no se abrió');
  const count = await page.$$eval('#comms-list li button', (els) => els.length);
  assert(count >= 1, 'el panel no lista comunidades');
  const top = await page.$$eval('#top-list li button', (els) => els.length);
  assert(top >= 1, 'no hay nodos más conectados');
  console.log(`        ${count} comunidades · ${top} nodos destacados`);
  await page.keyboard.press('Escape');
});

await step('el buscador encuentra un nodo', async () => {
  const query = await page.evaluate(() => {
    const m = window.__cortex.cosmos.meta.find(Boolean);
    return m ? m.name.slice(0, 5) : '';
  });
  assert(query.length >= 2, 'no hay nodos para buscar');
  await page.mouse.click(640, 600);
  await page.keyboard.press('/');
  assert(await visible(page, '#search'), '/ no abrió el buscador');
  await page.fill('#search input', query);
  const hits = await page.$$eval('#results li', (els) => els.length);
  assert(hits >= 1, `sin resultados para «${query}»`);
});

await step('el buscador filtra por tipo con prefijo', async () => {
  if (!(await visible(page, '#search'))) {
    await page.mouse.click(640, 600);
    await page.keyboard.press('/');
  }
  await page.fill('#search input', 'archivo:');
  const kinds = await page.$$eval('#results li .kind', (els) => els.map((el) => el.textContent));
  assert(kinds.length >= 1, 'el prefijo archivo: no dio resultados');
  assert(kinds.every((k) => k === 'archivo'), `el filtro dejó pasar otros tipos: ${[...new Set(kinds)].join(', ')}`);
  const withSig = await page.evaluate(() => window.__cortex.cosmos.meta.find((m) => m && m.sig && m.name.length >= 3));
  if (withSig) {
    await page.fill('#search input', withSig.name);
    const codes = await page.$$eval('#results li code', (els) => els.length);
    assert(codes >= 1, 'los resultados no muestran la firma');
  }
  await page.keyboard.press('Escape');
});

await step('la ficha muestra firma, documentación y ver código', async () => {
  const pick = await page.evaluate(() => {
    const c = window.__cortex;
    c.unpin();
    c.closeCode();
    c.film.start();
    const v = { x: 0, y: 0, z: 0 };
    const rect = document.querySelector('#stage').getBoundingClientRect();
    const order = c.cosmos.meta.map((m, i) => [m, i]).filter(([m]) => m).sort((a, b) => (b[0].sig ? 1 : 0) - (a[0].sig ? 1 : 0) || (b[0].doc ? 1 : 0) - (a[0].doc ? 1 : 0));
    for (const [m, i] of order) {
      const p = c.cosmos.pos;
      const P = new c.camera.position.constructor(p[i * 3], p[i * 3 + 1], p[i * 3 + 2]).project(c.camera);
      if (P.z > 1) continue;
      v.x = (P.x * 0.5 + 0.5) * rect.width + rect.left;
      v.y = (-P.y * 0.5 + 0.5) * rect.height + rect.top;
      if (v.x < 80 || v.x > rect.width - 420 || v.y < 120 || v.y > rect.height - 120) continue;
      if (c.pickNode(v.x, v.y, 14) !== i) continue;
      return { i, x: v.x, y: v.y, sig: m.sig || '', doc: m.doc || '', key: c.keyOf(m), project: c.project.name };
    }
    return null;
  });
  try {
    assert(pick, 'no hay ningún nodo visible para pasar el ratón');
    await page.mouse.move(pick.x + 40, pick.y + 40);
    await page.mouse.move(pick.x, pick.y, { steps: 4 });
    await waitFor(page, () => !document.querySelector('#tip').hidden, null, 5000, 'el tooltip no apareció');
    const tip = await page.$eval('#tip', (el) => ({ text: el.textContent, sig: el.querySelector('.sig')?.textContent || '', where: el.querySelector('.where')?.textContent || '' }));
    assert(tip.where.length > 0, 'el tooltip no muestra archivo:línea');
    if (pick.sig) assert(tip.sig && pick.sig.startsWith(tip.sig.replace(/…$/, '')), 'el tooltip no muestra la firma');
    else console.log('        (este grafo no trae firmas)');
    if (pick.doc) assert(tip.text.includes(pick.doc.split(/\n|(?<=[.!?])\s/)[0].slice(0, 40)), 'el tooltip no muestra la documentación');
    await page.mouse.click(pick.x, pick.y);
    await waitFor(page, (i) => window.__cortex.card === i && !document.querySelector('#card').hidden, pick.i, 5000, 'el clic no fijó la ficha');
    const status = await page.evaluate(async (p) => (await fetch(`api/query/symbol?project=${encodeURIComponent(p.project)}&ref=${encodeURIComponent(p.key)}`)).status, pick);
    await page.click('#card [data-act=code]');
    await waitFor(page, () => !document.querySelector('#code').hidden && !document.querySelector('#code-body').textContent.includes('leyendo'), null, 15000, 'el panel de código no terminó de cargar');
    if (status === 200) {
      const lines = await page.$$eval('#code-body .ln', (els) => els.length);
      assert(lines >= 1, 'el panel no muestra líneas de código');
      console.log(`        código: ${lines} líneas`);
    } else {
      const note = await page.textContent('#code-body .note');
      assert(note && note.length > 5, `sin mensaje para el estado ${status}`);
      console.log(`        /api/query/symbol respondió ${status}: «${note}»`);
    }
    await page.keyboard.press('Escape');
    assert(!(await visible(page, '#code')), 'Esc no cerró el panel de código');
    await page.keyboard.press('Escape');
    assert(!(await visible(page, '#card')), 'Esc no cerró la ficha');
  } finally {
    await page.evaluate(() => window.__cortex.film.stop());
  }
});

await step('los puentes listan endpoints y llevan a la araña', async () => {
  const eps = await page.evaluate(() => window.__cortex.cosmos.endpointCount);
  if (!eps) {
    console.log('        (este grafo no tiene endpoints)');
    return;
  }
  await waitFor(page, () => !document.querySelector('#bridges-chip').hidden, null, 5000, 'no aparece el chip de puentes');
  await page.click('#bridges-chip');
  assert(await visible(page, '#bridges'), 'el panel de puentes no se abrió');
  const rows = await page.$$eval('#bridges-list li button', (els) => els.length);
  assert(rows >= 1, 'el panel no lista endpoints');
  await page.click('#bridges-list li button');
  await waitFor(page, () => window.__cortex.card >= 0 && window.__cortex.cosmos.meta[window.__cortex.card].kind === 'endpoint', null, 5000, 'el clic no fijó el endpoint');
  console.log(`        ${eps} endpoints · ${rows} en la lista`);
  await page.keyboard.press('Escape');
});

await step('sin errores de página', async () => {
  assert(!errors.length, errors.join(' | '));
});

await browser.close();
console.log(failures ? `\n${failures} prueba(s) fallaron` : '\ntodas las pruebas pasaron');
process.exit(failures ? 1 : 0);
