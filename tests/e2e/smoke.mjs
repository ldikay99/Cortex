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

await step('sin errores de página', async () => {
  assert(!errors.length, errors.join(' | '));
});

await browser.close();
console.log(failures ? `\n${failures} prueba(s) fallaron` : '\ntodas las pruebas pasaron');
process.exit(failures ? 1 : 0);
