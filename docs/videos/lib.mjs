// Shared by render.mjs and contact.mjs: a local file server on a free port, and Chrome driven over CDP.
// No npm dependencies. Node 22's global WebSocket talks to Chrome.
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, rmSync, existsSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../..');
const DESIGN_DIST = resolve(REPO, '../gov_design/dist');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const FORBIDDEN_PORTS = new Set([8765, 8766, 8791, 5173]);
export const W = 1920;
export const H = 1080;

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8', '.yaml': 'text/plain; charset=utf-8' };

// Only these files are reachable. The case and results live outside this folder.
const DATA_FILES = {
  '/data/case.json': 'export/demo/cases/R0229-plain.json',
  '/data/final.json': 'reports/final.json',
  '/data/learning.json': 'export/demo/learning.json',
  '/data/events.json': 'export/demo/events.json',
  '/data/tone.json': 'reports/tone.json',
  '/data/story.txt': 'experiments/results/story_variants_real.txt',
  '/data/settings.yaml': 'settings/settings.yaml',
};

function locate(pathname) {
  if (DATA_FILES[pathname]) return join(REPO, DATA_FILES[pathname]);
  // For trying other timing without touching timing/.
  if (process.env.PE_TIMING_DIR && pathname.startsWith('/timing/')) return join(resolve(process.env.PE_TIMING_DIR), pathname.slice('/timing/'.length));
  const parts = pathname.split('/').filter(Boolean);
  if (parts.some((p) => p.startsWith('.'))) return null;
  const base = parts[0] === 'design' ? DESIGN_DIST : HERE;
  const rel = parts[0] === 'design' ? parts.slice(1) : parts;
  const full = resolve(base, ...rel);
  return full === base || full.startsWith(base + sep) ? full : null;
}

export function startServer() {
  const server = createServer((req, res) => {
    const full = locate(decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!full || !existsSync(full) || !statSync(full).isFile()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { 'content-type': TYPES[extname(full)] || 'application/octet-stream', 'cache-control': 'no-store' });
    res.end(readFileSync(full));
  });
  return new Promise((ok, fail) => {
    const listen = () => server.listen(0, '127.0.0.1');
    server.on('error', fail);
    server.on('listening', () => {
      const { port } = server.address();
      if (FORBIDDEN_PORTS.has(port)) {
        server.close(listen);
        return;
      }
      ok({ url: `http://127.0.0.1:${port}`, close: () => new Promise((done) => server.close(done)) });
    });
    listen();
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function startChrome() {
  const profile = mkdtempSync(join(tmpdir(), 'permit-videos-'));
  const chrome = spawn(CHROME, ['--headless=new', '--hide-scrollbars', '--disable-gpu', '--disable-lcd-text', '--font-render-hinting=none', '--force-color-profile=srgb', '--remote-debugging-port=0', `--user-data-dir=${profile}`, `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
  const portFile = join(profile, 'DevToolsActivePort');
  let port;
  for (let i = 0; i < 100 && !port; i++) {
    await sleep(100);
    if (existsSync(portFile)) port = Number(readFileSync(portFile, 'utf8').split('\n')[0]) || undefined;
  }
  if (!port) throw new Error('Chrome did not start');
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t) => t.type === 'page');
    } catch { /* still starting */ }
    if (!target) await sleep(100);
  }
  if (!target) throw new Error('Chrome has no page');

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r, x) => { ws.onopen = r; ws.onerror = x; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { ok, fail } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) fail(new Error(msg.error.message));
      else ok(msg.result);
    }
  };
  const send = (method, params = {}) => new Promise((ok, fail) => {
    const n = ++id;
    pending.set(n, { ok, fail });
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(`Page error: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
    return r.result.value;
  };
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });

  process.on('exit', () => chrome.kill());
  // An interrupted run must not leave Chrome behind.
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => process.exit(1));
  // Waits for Chrome to exit before removing its profile, which it writes to until the end.
  const close = async () => {
    try { ws.close(); } catch { /* already closed */ }
    const exited = new Promise((done) => chrome.once('exit', done));
    chrome.kill();
    await Promise.race([exited, sleep(5000)]);
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch { /* the temp folder is cleared by the system */ }
  };
  return { send, evaluate, close };
}

// Opens the player for one video and waits until fonts, data and timelines are ready.
export async function openPlayer(video) {
  const server = await startServer();
  const chrome = await startChrome();
  await chrome.send('Page.navigate', { url: `${server.url}/player.html?video=${video}` });
  let meta = null;
  for (let i = 0; i < 150 && !meta; i++) {
    await sleep(100);
    try { meta = await chrome.evaluate('window.ready ? window.ready.then((m) => m) : null'); } catch (error) {
      if (i > 20) throw error;
    }
  }
  if (!meta) throw new Error('Player did not become ready');
  if (meta.error) throw new Error(meta.error);
  return {
    meta,
    chrome,
    seek: (t) => chrome.evaluate(`window.seekPainted(${t})`),
    shot: async (format = 'png') => Buffer.from((await chrome.send('Page.captureScreenshot', { format, optimizeForSpeed: true, captureBeyondViewport: false })).data, 'base64'),
    close: async () => { await chrome.close(); await server.close(); },
  };
}

export function reportMeta(meta) {
  for (const warning of meta.warnings) console.warn(`warning: ${warning}`);
  console.log(`pacing: ${meta.stats.beats} changes, ${meta.stats.shortHolds} holds under 0.6s, ${meta.warnings.length} warnings, ${meta.duration.toFixed(2)}s`);
  if (process.env.PACING) console.log(`short holds at: ${meta.stats.holds.join(' ')}`);
}
