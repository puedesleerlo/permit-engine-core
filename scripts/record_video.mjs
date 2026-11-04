// Records a captioned tour of the replay with headless Chrome and ffmpeg. No npm dependencies.
// Needs the replay served locally. Run: node scripts/record_video.mjs [http://127.0.0.1:8791/] [export/demo-video.mp4]
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const BASE = process.argv[2] || 'http://127.0.0.1:8791/';
const OUT = resolve(process.argv[3] || 'export/demo-video.mp4');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9333;
const W = 1600, H = 900;
const CASE = process.env.TOUR_CASE || 'R0229-plain';

const work = mkdtempSync(join(tmpdir(), 'permit-video-'));
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(work, 'profile')}`, `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200);
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    target = list.find((t) => t.type === 'page');
  } catch { /* Chrome is still starting */ }
}
if (!target) throw new Error('Chrome did not start');

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0;
const pending = new Map();
const frames = [];
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg.result);
    pending.delete(msg.id);
  } else if (msg.method === 'Page.screencastFrame') {
    const { data, metadata, sessionId } = msg.params;
    const file = join(work, `f${String(frames.length).padStart(6, '0')}.jpg`);
    writeFileSync(file, Buffer.from(data, 'base64'));
    frames.push({ file, t: metadata.timestamp });
    send('Page.screencastFrameAck', { sessionId });
  }
};
const send = (method, params = {}) => new Promise((r) => {
  const n = ++id;
  pending.set(n, r);
  ws.send(JSON.stringify({ id: n, method, params }));
});
const run = (expression) => send('Runtime.evaluate', { expression, awaitPromise: true });

const CAPTION = `(text) => {
  let el = document.getElementById('__caption');
  if (!el) {
    el = document.createElement('div');
    el.id = '__caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:44px;transform:translateX(-50%);z-index:99999;max-width:1100px;background:#0f2747;color:#fff;font:600 24px/1.35 system-ui,sans-serif;padding:16px 26px;border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.28);text-align:center';
    document.body.appendChild(el);
  }
  el.textContent = text;
}`;
const caption = (text) => run(`(${CAPTION})(${JSON.stringify(text)})`);
const go = (hash) => run(`location.hash = ${JSON.stringify(hash)}`);
const clickText = (text) => run(`(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim().includes(${JSON.stringify(text)})); if (b) b.click(); return !!b; })()`);
const SCROLLER = `(() => { const all = [document.scrollingElement, ...document.querySelectorAll('main, main *, [class*="content" i]')]; return all.filter((e) => e && e.scrollHeight > e.clientHeight + 40 && getComputedStyle(e).overflowY !== 'hidden').sort((a, b) => b.scrollHeight - a.scrollHeight)[0] || document.scrollingElement; })()`;
const top = () => run(`${SCROLLER}.scrollTop = 0`);
async function glide(pixels, seconds) {
  const steps = Math.round(seconds * 30);
  for (let i = 0; i < steps; i++) {
    await run(`${SCROLLER}.scrollBy(0, ${pixels / steps})`);
    await sleep(1000 / 30);
  }
}
const toHeading = (text) => run(`(() => { const h = [...document.querySelectorAll('h1,h2,h3')].find((x) => x.textContent.includes(${JSON.stringify(text)})); if (h) h.scrollIntoView({ block: 'start' }); ${SCROLLER}.scrollBy(0, -90); return !!h; })()`);

await send('Page.enable');
await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: `${BASE}?speed=8` });
await sleep(1500);
await send('Page.startScreencast', { format: 'jpeg', quality: 82, maxWidth: W, maxHeight: H, everyNthFrame: 1 });

await caption('120 made-up street race applications replay in your browser. Nothing here is a real event.');
await sleep(9000);
await caption('Each one is read, checked and scored. It is then approved, or sent to an officer.');
await sleep(9000);
await caption('An LLM stands in for the officer in this demo. A real deployment would use a person.');
await sleep(9000);
await caption('Every officer review teaches the trees. Right risk level is the number that rises.');
await sleep(10000);
await caption('Precision holds, and about a third of cases can never be automatic, so that share stays near flat.');
await sleep(9000);

await go(`#/case/${CASE}`);
await sleep(1200);
await top();
await caption('Any case can be opened, from the documents through to the rule that fired.');
await sleep(5000);
await toHeading('What was found');
await caption('An agentic LLM finds each kind of proof and must quote the words it relied on. Code checks every quote.');
await sleep(5000);
await glide(420, 6);
await caption('This police letter names another date, so the case goes to an officer. The system does not settle that alone.');
await sleep(5000);
await toHeading('Which hazards');
await glide(0, 0.1);
await caption('Each hazard has a likelihood tree and a severity tree. Jev answers the questions, and rules answer the rest.');
await glide(650, 8);
await caption('Likelihood times severity, summed over hazards, is compared with the thresholds.');
await glide(650, 7);
await caption('The officer rules with a one-line reason, and we can see exactly which weights moved.');
await glide(800, 8);

await go('#/problems');
await sleep(1000);
await top();
await caption('Problem cases: why each one went to an officer, with the two failure modes counted separately.');
await sleep(6000);
await go('#/rulings');
await sleep(1000);
await top();
await caption('Every ruling by the simulated officer, labelled as simulated, with its measured accuracy.');
await sleep(6000);

await caption('On cases set aside, the right risk level rose over the officer reviews. Loss fell.');
await clickText('Jump to end');
await sleep(800);
await go('#/learning');
await sleep(1200);
await top();
await sleep(7000);
await glide(560, 6);
await toHeading('Results from the finished run');
await caption('Then one sealed test, run once, on cases nothing had seen. It is compared with a control and two simpler systems.');
await sleep(4000);
await glide(450, 7);
await caption('The labels were written by the author. This shows the mechanism works, not that the levels describe real events.');
await sleep(7000);

await send('Page.stopScreencast');
await sleep(300);
ws.close();
chrome.kill();

let list = '';
frames.forEach((frame, i) => {
  const next = frames[i + 1] ? frames[i + 1].t : frame.t + 0.5;
  list += `file '${frame.file}'\nduration ${Math.max(next - frame.t, 0.001).toFixed(4)}\n`;
});
list += `file '${frames[frames.length - 1].file}'\n`;
const listFile = join(work, 'frames.txt');
writeFileSync(listFile, list);
const out = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', listFile, '-vf', `fps=30,scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p`, '-c:v', 'libx264', '-crf', '24', '-preset', 'medium', '-movflags', '+faststart', OUT], { stdio: 'inherit' });
if (out.status !== 0) throw new Error('ffmpeg failed');
console.log(JSON.stringify({ frames: frames.length, seconds: frames[frames.length - 1].t - frames[0].t, out: OUT }));
rmSync(work, { recursive: true, force: true });
process.exit(0);
