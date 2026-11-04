// Estimates timing/video1.json and timing/video2.json from narration.json, so visuals can be reviewed
// before a voice exists. The real voice's timing overwrites these files in the same shape.
// All times are seconds from the start of the video. Run: node make_estimated_timing.mjs
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORDS_PER_SECOND = 2.3;
const SCENE_PAUSE = 0.5;
const SECTION_PAUSE = 0.9;
const LEAD_IN = 0.4;
const TAIL = 1.5;

const round = (x) => Math.round(x * 1000) / 1000;
const narration = JSON.parse(readFileSync(join(HERE, 'narration.json'), 'utf8'));
const sections = JSON.parse(readFileSync(join(HERE, 'sections.json'), 'utf8'));
mkdirSync(join(HERE, 'timing'), { recursive: true });

for (const video of Object.keys(narration)) {
  const sectionOf = new Map();
  sections[video].forEach((section, i) => section.scenes.forEach((id) => sectionOf.set(id, i)));
  let t = LEAD_IN;
  const scenes = narration[video].map((scene, i, all) => {
    if (i > 0) t += sectionOf.get(all[i - 1].id) === sectionOf.get(scene.id) ? SCENE_PAUSE : SECTION_PAUSE;
    const start = t;
    const words = scene.text.trim().split(/\s+/).map((w) => {
      const word = { w, start: round(t), end: round(t + 1 / WORDS_PER_SECOND) };
      t += 1 / WORDS_PER_SECOND;
      return word;
    });
    return { id: scene.id, start: round(start), end: round(t), words };
  });
  const out = { duration: round(t + TAIL), scenes };
  writeFileSync(join(HERE, 'timing', `${video}.json`), `${JSON.stringify(out, null, 1)}\n`);
  console.log(`${video}: ${scenes.length} scenes, ${out.duration}s`);
}
