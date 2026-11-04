#!/usr/bin/env python3
"""Voices narration.json with ElevenLabs, one clip per scene, and writes the audio track, real timing and subtitles.

Clips are stored by a hash of what was asked for, so a re-run only pays for scenes whose words changed.
The key comes from ELEVENLABS_API_KEY in the repository's .env and is never printed.

Run from anywhere: /usr/bin/python3 docs/videos/voice.py [video1 video2] [--timing-dir timing]
"""
import base64, hashlib, json, re, subprocess, sys, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VOICE = 'EXAVITQu4vr4xnSDxMaL'  # a mature, confident American narrator from the ElevenLabs premade voices
MODEL = 'eleven_multilingual_v2'
SETTINGS = {'stability': 0.55, 'similarity_boost': 0.75, 'style': 0.0, 'use_speaker_boost': True}
SPEED = {'video1': 1.0, 'video2': 1.1}  # spoken numbers slow video 2, so this brings it to about the pace of video 1
SCENE_PAUSE, SECTION_PAUSE, LEAD_IN, TAIL = 0.5, 0.8, 0.4, 1.0
SPOKEN_DIGITS = {'point zero five': '0.05', 'point nine six': '0.96'}


def api_key() -> str:
    match = re.search(r'^ELEVENLABS_API_KEY=(.+)$', (ROOT / '.env').read_text(), re.M)
    if not match:
        sys.exit('ELEVENLABS_API_KEY is not in .env')
    return match.group(1).strip()


def clip(key: str, text: str, previous: str, following: str, speed: float) -> dict:
    """Returns {'mp3': path, 'alignment': ...} for one scene, from the store when it exists."""
    store = HERE / 'audio' / 'clips'
    store.mkdir(parents=True, exist_ok=True)
    ask = {'text': text, 'previous_text': previous, 'next_text': following, 'model_id': MODEL, 'voice_settings': {**SETTINGS, 'speed': speed}, 'voice': VOICE, 'seed': 20261104}
    name = hashlib.sha256(json.dumps(ask, sort_keys=True).encode()).hexdigest()[:20]
    mp3, meta = store / f'{name}.mp3', store / f'{name}.json'
    if not (mp3.exists() and meta.exists()):
        body = {k: v for k, v in ask.items() if k != 'voice' and v != ''}
        request = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps?output_format=mp3_44100_128', data=json.dumps(body).encode(),
                                         headers={'xi-api-key': key, 'Content-Type': 'application/json', 'User-Agent': 'permit-engine-video/1'})
        try:
            with urllib.request.urlopen(request, timeout=120) as reply:
                data = json.load(reply)
        except urllib.error.HTTPError as exc:
            sys.exit(f'ElevenLabs refused a scene: {exc.code} {exc.read()[:300].decode(errors="replace").replace(key, "[key]")}')
        mp3.write_bytes(base64.b64decode(data['audio_base64']))
        meta.write_text(json.dumps(data['alignment']))
        print(f'  voiced: {text[:50]}...')
    return {'mp3': mp3, 'alignment': json.loads(meta.read_text())}


def words_of(alignment: dict) -> list:
    words, current, start = [], '', None
    for char, begin, end in zip(alignment['characters'], alignment['character_start_times_seconds'], alignment['character_end_times_seconds']):
        if char.isspace():
            if current:
                words.append({'w': current, 'start': start, 'end': last})
            current, start = '', None
            continue
        if not current:
            start = begin
        current += char
        last = end
    if current:
        words.append({'w': current, 'start': start, 'end': last})
    return words


def stamp(t: float) -> str:
    ms = int(round(t * 1000))
    return f'{ms // 3600000:02}:{ms % 3600000 // 60000:02}:{ms % 60000 // 1000:02},{ms % 1000:03}'


def subtitles(scenes: list) -> str:
    cues = []
    for scene in scenes:
        line, begin = [], None
        for i, word in enumerate(scene['words']):
            if not line:
                begin = word['start']
            line.append(word['w'])
            text = ' '.join(line)
            at_end = i == len(scene['words']) - 1
            if at_end or len(text) >= 52 or (len(text) >= 26 and word['w'][-1] in ',.:;?'):
                for spoken, digits in SPOKEN_DIGITS.items():
                    text = text.replace(spoken, digits)
                cues.append((begin, word['end'], text))
                line = []
    return ''.join(f'{i}\n{stamp(a)} --> {stamp(b)}\n{t}\n\n' for i, (a, b, t) in enumerate(cues, 1))


def build(video: str, narration: dict, sections: dict, key: str, timing_dir: Path) -> dict:
    scenes_in = narration[video]
    section_of = {sid: i for i, s in enumerate(sections[video]) for sid in s['scenes']}
    t, scenes, placed = LEAD_IN, [], []
    for i, scene in enumerate(scenes_in):
        if i:
            t += SCENE_PAUSE if section_of[scenes_in[i - 1]['id']] == section_of[scene['id']] else SECTION_PAUSE
        previous = scenes_in[i - 1]['text'] if i else ''
        following = scenes_in[i + 1]['text'] if i + 1 < len(scenes_in) else ''
        result = clip(key, scene['text'], previous, following, SPEED[video])
        words = words_of(result['alignment'])
        placed.append((result['mp3'], t))
        timed = [{'w': w['w'], 'start': round(t + w['start'], 3), 'end': round(t + w['end'], 3)} for w in words]
        scenes.append({'id': scene['id'], 'start': round(t, 3), 'end': timed[-1]['end'], 'words': timed})
        t = timed[-1]['end']
    out = {'duration': round(t + TAIL, 3), 'scenes': scenes, 'voice': 'ElevenLabs premade female narrator'}
    timing_dir.mkdir(parents=True, exist_ok=True)
    (timing_dir / f'{video}.json').write_text(json.dumps(out, indent=1) + '\n')
    audio = HERE / 'audio'
    (audio / f'{video}.srt').write_text(subtitles(scenes))
    inputs, parts = [], []
    for n, (path, start) in enumerate(placed):
        inputs += ['-i', str(path)]
        ms = int(round(start * 1000))
        parts.append(f'[{n}:a]adelay={ms}:all=1[a{n}]')
    mix = ''.join(f'[a{n}]' for n in range(len(placed))) + f'amix=inputs={len(placed)}:normalize=0,apad=whole_dur={out["duration"]},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[out]'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(parts) + ';' + mix, '-map', '[out]', '-t', str(out['duration']), '-c:a', 'aac', '-b:a', '160k', str(audio / f'{video}.m4a')], check=True)
    spoken = sum(len(s['words']) for s in scenes)
    talk = sum(s['end'] - s['start'] for s in scenes)
    print(f"{video}: {out['duration']:.1f} s in all, {spoken} words, {spoken / talk:.2f} words per second while speaking")
    for s in scenes:
        print(f"   {s['id']:>5}  {s['start']:7.2f} to {s['end']:7.2f}  ({s['end'] - s['start']:5.2f} s, {len(s['words'])} words)")
    return out


def main():
    args = sys.argv[1:]
    timing_dir = HERE / 'timing'
    if '--timing-dir' in args:
        i = args.index('--timing-dir')
        timing_dir = HERE / args[i + 1]
        del args[i:i + 2]
    videos = args or ['video1', 'video2']
    narration = json.loads((HERE / 'narration.json').read_text())
    sections = json.loads((HERE / 'sections.json').read_text())
    key = api_key()
    for video in videos:
        build(video, narration, sections, key, timing_dir)


if __name__ == '__main__':
    main()
