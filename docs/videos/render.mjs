// Renders one video to MP4 by stepping the player at 30 fps and piping each frame to ffmpeg.
// Run: node render.mjs <video1|video2> <out.mp4> [--audio file] [--srt file]
// Without --audio the output is silent, for review. Timing comes from timing/<video>.json.
import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { once } from 'node:events';
import { openPlayer, reportMeta } from './lib.mjs';

const FPS = 30;

function parseArgs(argv) {
  const [video, out, ...rest] = argv;
  if (!['video1', 'video2'].includes(video) || !out) {
    console.error('Usage: node render.mjs <video1|video2> <out.mp4> [--audio file] [--srt file]');
    process.exit(2);
  }
  const args = { video, out: resolve(out) };
  for (let i = 0; i < rest.length; i += 2) {
    if (rest[i] === '--audio') args.audio = resolve(rest[i + 1]);
    else if (rest[i] === '--srt') args.srt = resolve(rest[i + 1]);
    else {
      console.error(`Unknown option ${rest[i]}`);
      process.exit(2);
    }
  }
  for (const file of [args.audio, args.srt]) {
    if (file && !existsSync(file)) {
      console.error(`Not found: ${file}`);
      process.exit(2);
    }
  }
  return args;
}

function audioSeconds(file) {
  const probe = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', file], { encoding: 'utf8' });
  return Number(probe.stdout.trim()) || 0;
}

const args = parseArgs(process.argv.slice(2));
const started = Date.now();
mkdirSync(dirname(args.out), { recursive: true });
const player = await openPlayer(args.video);
reportMeta(player.meta);

// The picture always covers the whole voice. If the audio is longer, the last frame holds.
const audioLength = args.audio ? audioSeconds(args.audio) : 0;
if (args.audio && Math.abs(audioLength - player.meta.duration) > 2) {
  console.warn(`warning: audio is ${audioLength.toFixed(2)}s and the timing file says ${player.meta.duration.toFixed(2)}s. Check they belong together.`);
}
const seconds = Math.max(player.meta.duration, audioLength);
const frames = Math.ceil(seconds * FPS);

const ffmpegArgs = ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', 'pipe:0'];
let nextInput = 1;
if (args.audio) ffmpegArgs.push('-i', args.audio);
const audioIndex = args.audio ? nextInput++ : -1;
if (args.srt) ffmpegArgs.push('-i', args.srt);
const srtIndex = args.srt ? nextInput++ : -1;
ffmpegArgs.push('-map', '0:v:0');
if (audioIndex >= 0) ffmpegArgs.push('-map', `${audioIndex}:a:0`);
if (srtIndex >= 0) ffmpegArgs.push('-map', `${srtIndex}:s:0`);
ffmpegArgs.push(
  '-vf', 'scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-r', String(FPS),
  '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
  '-movflags', '+faststart',
);
if (audioIndex >= 0) ffmpegArgs.push('-c:a', 'aac', '-b:a', '192k');
if (srtIndex >= 0) ffmpegArgs.push('-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng', '-metadata:s:s:0', 'title=English');
ffmpegArgs.push(args.out);

const ffmpeg = spawn('ffmpeg', ffmpegArgs, { stdio: ['pipe', 'inherit', 'inherit'] });
let ffmpegFailed = false;
ffmpeg.on('error', () => { ffmpegFailed = true; });
ffmpeg.stdin.on('error', () => { ffmpegFailed = true; });

let frame = null;
let unique = 0;
for (let n = 0; n < frames; n++) {
  const changed = await player.seek(n / FPS);
  if (changed || !frame) {
    frame = await player.shot();
    unique++;
  }
  if (ffmpegFailed) throw new Error('ffmpeg stopped early');
  if (!ffmpeg.stdin.write(frame)) await once(ffmpeg.stdin, 'drain');
  if (n % 300 === 0) console.log(`${args.video}: frame ${n}/${frames}`);
}
ffmpeg.stdin.end();
const [code] = await once(ffmpeg, 'close');
await player.close();
if (code !== 0) throw new Error(`ffmpeg exited with ${code}`);
const elapsed = (Date.now() - started) / 1000;
console.log(JSON.stringify({ out: args.out, seconds: Number(seconds.toFixed(2)), frames, captured: unique, renderSeconds: Number(elapsed.toFixed(1)), audio: !!args.audio, subtitles: !!args.srt }));
process.exit(0);
