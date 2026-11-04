// Writes one PNG contact sheet so a person can review a video quickly.
// Run: node contact.mjs <video1|video2>                  a frame from the middle of each scene, in out/<video>-contact.png
// Options for closer review:
//   --at <0..1>            where in each scene to take the frame (0.5 is the middle, 1 is the scene's last settled frame)
//   --times 10.2,10.4,...  exact times, for consecutive frames around a scene change
//   --boundary <id>        six consecutive frames across the change into scene <id>
//   --scene <id> --n <n>   n frames spread across one scene
//   --cols <n>  --width <px>  --out <file>
//   --audit                also check text overlap, clipping and banned wording at the middle and end of each scene
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { HERE, openPlayer, reportMeta } from './lib.mjs';

const argv = process.argv.slice(2);
const video = argv[0];
if (!['video1', 'video2'].includes(video)) {
  console.error('Usage: node contact.mjs <video1|video2> [--at f] [--times a,b] [--boundary id] [--scene id --n n] [--cols n] [--width px] [--out file] [--audit]');
  process.exit(2);
}
const option = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i < 0 ? fallback : argv[i + 1];
};
const flag = (name) => argv.includes(`--${name}`);

const player = await openPlayer(video);
reportMeta(player.meta);
const { scenes } = player.meta;

function plan() {
  const times = option('times');
  if (times) return times.split(',').map((t) => ({ t: Number(t), label: `t=${Number(t).toFixed(2)}` }));
  const boundary = option('boundary');
  if (boundary) {
    const scene = scenes.find((s) => s.id === boundary);
    if (!scene) throw new Error(`No scene ${boundary}`);
    const from = scene.t0 - 0.2;
    const step = (scene.t1 - scene.t0 + 0.4) / 5;
    return [0, 1, 2, 3, 4, 5].map((i) => ({ t: from + i * step, label: `into ${boundary} t=${(from + i * step).toFixed(2)}` }));
  }
  const sceneId = option('scene');
  if (sceneId) {
    const scene = scenes.find((s) => s.id === sceneId);
    if (!scene) throw new Error(`No scene ${sceneId}`);
    const n = Number(option('n', 6));
    const a = scene.t1;
    const b = Math.min(scene.out0, player.meta.duration - 0.05);
    return Array.from({ length: n }, (_, i) => {
      const t = a + ((b - a) * i) / Math.max(1, n - 1);
      return { t, label: `${sceneId} t=${t.toFixed(2)}` };
    });
  }
  const at = Number(option('at', 0.5));
  return scenes.map((s) => {
    const a = s.t1;
    const b = Math.min(s.out0, player.meta.duration - 0.05);
    const t = a + (b - a) * at - (at >= 1 ? 0.04 : 0);
    return { t, label: `${s.id}  t=${t.toFixed(2)}` };
  });
}

if (flag('audit')) {
  let problems = 0;
  for (const s of scenes) {
    const end = Math.min(s.out0, player.meta.duration - 0.05) - 0.04;
    for (const t of [s.t1 + (end - s.t1) * 0.5, end]) {
      const found = await player.chrome.evaluate(`window.seek(${t}), window.__audit()`);
      for (const f of found) {
        console.log(`audit ${s.id} t=${t.toFixed(2)}: ${f}`);
        problems++;
      }
    }
  }
  console.log(`audit: ${problems} problem(s)`);
}

const shots = [];
for (const { t, label } of plan()) {
  await player.seek(t);
  shots.push({ label, data: (await player.shot()).toString('base64') });
}

const cols = Number(option('cols', shots.length <= 6 ? 3 : 4));
const width = Number(option('width', 640));
const height = Math.round((width * 9) / 16);
const rows = Math.ceil(shots.length / cols);
const pad = 12;
const caption = 34;
const sheetW = cols * (width + pad) + pad;
const sheetH = rows * (height + caption + pad) + pad;
await player.chrome.send('Emulation.setDeviceMetricsOverride', { width: sheetW, height: sheetH, deviceScaleFactor: 1, mobile: false });
await player.chrome.evaluate(`(async (shots) => {
  document.documentElement.removeAttribute('style');
  document.body.setAttribute('style', 'margin:0;background:#d8dee6;overflow:hidden;font:600 22px system-ui,sans-serif;color:#13202f');
  document.body.innerHTML = '<div id="sheet" style="display:grid;grid-template-columns:repeat(${cols},${width}px);gap:${pad}px;padding:${pad}px"></div>';
  const sheet = document.getElementById('sheet');
  for (const shot of shots) {
    const cell = document.createElement('div');
    const img = new Image();
    img.src = 'data:image/png;base64,' + shot.data;
    img.width = ${width};
    img.height = ${height};
    img.style.display = 'block';
    const label = document.createElement('div');
    label.textContent = shot.label;
    label.style.height = '${caption}px';
    label.style.lineHeight = '${caption}px';
    cell.append(label, img);
    sheet.append(cell);
    await img.decode();
  }
})(${JSON.stringify(shots)})`);
const png = await player.shot();
const defaultName = option('at') ? `${video}-contact-at-${option('at')}.png` : `${video}-contact.png`;
const out = resolve(option('out', join(HERE, 'out', defaultName)));
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, png);
await player.close();
console.log(out);
process.exit(0);
