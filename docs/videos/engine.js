// Deterministic stage for the Permit Engine explainers.
// window.seek(t) draws the exact frame for time t. Every property of every element is a pure function
// of t, computed from tracks registered at build time. No CSS transitions, timers or randomness.
(function () {
  'use strict';

  const PE = (window.PE = { W: 1920, H: 1080, videos: {}, warnings: [], C: {}, F: {}, data: {}, kit: {} });
  const warn = (message) => {
    PE.warnings.push(message);
    console.warn(message);
  };

  // ---- Easing and values ----------------------------------------------------------------------

  const EASES = {
    soft: (p) => p * p * (3 - 2 * p),
    linear: (p) => p,
    // A steady middle with short soft ends, for the plan's text sliding past.
    cruise: (p) => {
      const a = 0.08;
      const k = 1 / (2 * a * (1 - a));
      if (p < a) return p * p * k;
      if (p > 1 - a) return 1 - (1 - p) * (1 - p) * k;
      return (p - a / 2) / (1 - a);
    },
  };

  const COLOR_PROPS = new Set(['color', 'bg', 'stroke', 'fill', 'border']);

  function parseColor(value) {
    if (Array.isArray(value)) return value;
    const s = String(value).trim();
    if (s === 'transparent') return [255, 255, 255, 0];
    if (s[0] === '#') {
      const h = s.slice(1);
      const long = h.length <= 4 ? h.split('').map((c) => c + c).join('') : h;
      const n = (i) => parseInt(long.slice(i, i + 2), 16);
      return [n(0), n(2), n(4), long.length === 8 ? n(6) / 255 : 1];
    }
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p[3] === undefined ? 1 : p[3]];
    }
    throw new Error(`Cannot read colour ${value}`);
  }
  const lerp = (a, b, p) => a + (b - a) * p;
  const lerpValue = (prop, a, b, p) => {
    if (!COLOR_PROPS.has(prop)) return lerp(a, b, p);
    const x = parseColor(a);
    const y = parseColor(b);
    return `rgba(${Math.round(lerp(x[0], y[0], p))},${Math.round(lerp(x[1], y[1], p))},${Math.round(lerp(x[2], y[2], p))},${lerp(x[3], y[3], p).toFixed(3)})`;
  };

  // ---- Build state ----------------------------------------------------------------------------

  const state = { stage: null, blocks: [], block: null, tweens: [], scenes: [], sceneById: new Map(), timing: null, sections: [], dry: false, cuePlans: new Map(), duration: 0 };

  // ---- Items ----------------------------------------------------------------------------------

  class Item {
    constructor(el, base = {}) {
      this.el = el;
      this.base = { opacity: 1, x: 0, y: 0, scale: 1, ...base };
      this.tracks = {};
      this.cur = {};
      this.fmt = null;
      if (state.block) state.block.items.push(this);
    }

    add(prop, t, dur, to, from, ease = 'soft', exempt = false) {
      (this.tracks[prop] = this.tracks[prop] || []).push({ t0: t, t1: t + dur, to, from, ease: EASES[ease] });
      if (state.block && !state.block.engineOwned) state.tweens.push({ t0: t, t1: t + dur, exempt });
      return this;
    }

    // Moves any properties to new values, starting at t.
    to(props, t, dur = 0.7, opt = {}) {
      for (const prop of Object.keys(props)) this.add(prop, t, dur, props[prop], opt.from ? opt.from[prop] : undefined, opt.ease, opt.exempt);
      return this;
    }

    // Appears. Before t it is invisible.
    in(t, dur = 0.5, opt = {}) {
      this.add('opacity', t, dur, opt.to === undefined ? 1 : opt.to, 0);
      if (opt.dy) this.add('y', t, dur, this.base.y, this.base.y + opt.dy);
      if (opt.dx) this.add('x', t, dur, this.base.x, this.base.x + opt.dx);
      if (opt.scale) this.add('scale', t, dur, this.base.scale, opt.scale);
      return this;
    }

    out(t, dur = 0.5) { return this.add('opacity', t, dur, 0); }
    dim(t, level = 0.25, dur = 0.6) { return this.add('opacity', t, dur, level); }
    lit(t, dur = 0.6) { return this.add('opacity', t, dur, 1); }

    // Traces a path from its start to its end.
    drawIn(t, dur = 0.8) { return this.add('draw', t, dur, 1, 0); }

    // Number count-up. The formatter turns the value into text.
    count(from, to, t, dur = 0.8, fmt, opt = {}) {
      if (fmt) this.fmt = fmt;
      return this.add('count', t, dur, to, from, opt.ease, opt.exempt);
    }

    finalize() {
      for (const prop of Object.keys(this.tracks)) {
        const track = this.tracks[prop];
        track.sort((a, b) => a.t0 - b.t0);
        let value = this.base[prop];
        if (value === undefined) value = prop === 'draw' ? 1 : prop === 'count' ? 0 : undefined;
        for (let i = 0; i < track.length; i++) {
          const tween = track[i];
          if (tween.from === undefined) tween.from = i === 0 ? value : valueOf(track.slice(0, i), tween.t0, prop);
          if (tween.from === undefined) throw new Error(`Tween on ${prop} at ${tween.t0.toFixed(2)}s has no starting value`);
          value = tween.to;
        }
      }
    }

    apply(t) {
      let changed = false;
      let transform = false;
      for (const prop of Object.keys(this.tracks)) {
        const value = valueOf(this.tracks[prop], t, prop);
        if (value === this.cur[prop]) continue;
        this.cur[prop] = value;
        changed = true;
        if (prop === 'x' || prop === 'y' || prop === 'scale') transform = true;
        else this.write(prop, value);
      }
      if (transform) this.writeTransform();
      return changed;
    }

    writeTransform() {
      const x = this.cur.x === undefined ? this.base.x : this.cur.x;
      const y = this.cur.y === undefined ? this.base.y : this.cur.y;
      const s = this.cur.scale === undefined ? this.base.scale : this.cur.scale;
      this.el.style.transform = `translate(${x.toFixed(3)}px,${y.toFixed(3)}px) scale(${s.toFixed(5)})`;
    }

    write(prop, v) {
      const style = this.el.style;
      switch (prop) {
        case 'opacity': style.opacity = v.toFixed(4); break;
        case 'width': style.width = `${v.toFixed(3)}px`; break;
        case 'height': style.height = `${v.toFixed(3)}px`; break;
        case 'color': (this.inner || this.el).style.color = v; break;
        case 'bg': style.backgroundColor = v; break;
        case 'border': style.borderColor = v; break;
        case 'stroke': this.shape.style.stroke = v; break;
        case 'fill': this.shape.style.fill = v; break;
        case 'draw': this.shape.style.strokeDashoffset = (1 - v).toFixed(5); break;
        case 'count': (this.inner || this.el).textContent = this.fmt ? this.fmt(v) : String(v); break;
        default: throw new Error(`Unknown property ${prop}`);
      }
    }
  }

  function valueOf(track, t, prop) {
    if (t < track[0].t0) return track[0].from;
    let i = track.length - 1;
    while (i > 0 && track[i].t0 > t) i--;
    const tween = track[i];
    if (t >= tween.t1 || tween.t1 === tween.t0) return tween.to;
    return lerpValue(prop, tween.from, tween.to, tween.ease((t - tween.t0) / (tween.t1 - tween.t0)));
  }

  const div = (parent, css) => {
    const el = document.createElement('div');
    el.style.cssText = `position:absolute;left:0;top:0;transform-origin:0 0;${css || ''}`;
    parent.appendChild(el);
    return el;
  };

  // A group holds children in its own coordinates and moves or fades them together.
  class Group extends Item {
    constructor(el, base) {
      super(el, base);
      this.writeInitial();
    }

    writeInitial() {
      this.writeTransform();
      if (this.base.opacity !== 1) this.el.style.opacity = this.base.opacity;
    }

    group({ x = 0, y = 0, scale = 1, opacity = 1, clip, w, h, r } = {}) {
      let css = '';
      if (clip) css = `overflow:hidden;width:${w}px;height:${h}px;${r ? `border-radius:${r}px;` : ''}`;
      return new Group(div(this.el, css), { x, y, scale, opacity });
    }

    // A rectangle. x and y are its top left corner.
    box({ x = 0, y = 0, w, h, fill = 'transparent', stroke, sw = 2, r = 0, opacity = 1 }) {
      const el = div(this.el, `width:${w}px;height:${h}px;background:${fill};border-radius:${r}px;${stroke ? `border:${sw}px solid ${stroke};` : ''}`);
      const item = new Item(el, { x, y, opacity, width: w, height: h, bg: fill, border: stroke });
      Group.prototype.writeInitial.call(item);
      return item;
    }

    // One line of text, or wrapped text when w is given. y is always the vertical centre of the text.
    // x is the left edge, the centre or the right edge, following align.
    text(content, { x = 0, y = 0, size = 32, weight = 400, font = 'text', color, align = 'left', w, lh = 1.22, opacity = 1, html = false, tracking, tabular, scale = 1, audit = true }) {
      if (size * scale < 27.9) warn(`Text under 28px: "${String(content).slice(0, 40)}" at ${size * scale}px`);
      const span = w || align === 'left' ? w || 0 : 3000;
      const left = align === 'center' ? -(span / 2) : align === 'right' ? -span : 0;
      const justify = align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start';
      const origin = align === 'center' ? '50% 0' : align === 'right' ? '100% 0' : '0 0';
      const el = div(this.el, `left:${left}px;height:0;display:flex;align-items:center;justify-content:${justify};transform-origin:${origin};${span ? `width:${span}px;` : ''}`);
      const inner = document.createElement('span');
      inner.style.cssText = `display:block;font-family:${PE.F[font]};font-size:${size}px;font-weight:${weight};line-height:${lh};color:${color || PE.C.ink};text-align:${align};${w ? '' : 'white-space:nowrap;'}${tracking ? `letter-spacing:${tracking};` : ''}`;
      if (html) inner.innerHTML = content;
      else inner.textContent = content;
      el.appendChild(inner);
      const item = new Item(el, { x, y, opacity, scale, color: color || PE.C.ink });
      item.inner = inner;
      item.isText = audit;
      item.size = size;
      Group.prototype.writeInitial.call(item);
      item.part = (key) => {
        const node = inner.querySelector(`[data-k="${key}"]`);
        if (!node) throw new Error(`No part ${key}`);
        return new Item(node, { bg: 'transparent', color: getComputedStyle(node).color });
      };
      state.textItems.push(item);
      return item;
    }

    // An SVG path in this group's coordinates. Paths draw in with drawIn.
    path(d, { stroke, width = 4, fill = 'none', cap = 'butt', join = 'round', opacity = 1, dash, marker } = {}) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('width', '1');
      svg.setAttribute('height', '1');
      svg.style.cssText = 'position:absolute;left:0;top:0;overflow:visible;transform-origin:0 0;';
      const shape = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      shape.setAttribute('d', d);
      shape.style.cssText = `fill:${fill};stroke:${stroke || 'none'};stroke-width:${width};stroke-linecap:${cap};stroke-linejoin:${join};`;
      if (dash) shape.style.strokeDasharray = dash;
      else {
        shape.setAttribute('pathLength', '1');
        shape.style.strokeDasharray = '1 1';
        shape.style.strokeDashoffset = '0';
      }
      svg.appendChild(shape);
      this.el.appendChild(svg);
      const item = new Item(svg, { opacity, stroke, fill });
      item.shape = shape;
      Group.prototype.writeInitial.call(item);
      return item;
    }
  }

  // ---- Scenes and cues ------------------------------------------------------------------------

  const normalize = (word) => String(word).toLowerCase().replace(/[’‘]/g, "'").replace(/[^a-z0-9.%']/g, '').replace(/^[.']+|[.']+$/g, '');

  class Scene {
    constructor(info) {
      Object.assign(this, info);
      this.tokens = info.words.map((w) => normalize(w.w));
      this.cueCount = 0;
      this.lastLand = null;
    }

    frac(p) { return this.start + (this.end - this.start) * p; }

    // Finds a phrase's word position. Word by word first, then ignoring how the words were split.
    locate(phrase, nth = 1) {
      const want = phrase.split(/\s+/).map(normalize).filter(Boolean);
      if (!want.length) return null;
      let seen = 0;
      for (let i = 0; i + want.length <= this.tokens.length; i++) {
        if (want.every((w, j) => this.tokens[i + j] === w) && ++seen === nth) return { first: i, last: i + want.length - 1 };
      }
      const joined = want.join('');
      seen = 0;
      for (let i = 0; i < this.tokens.length; i++) {
        let text = '';
        for (let j = i; j < this.tokens.length && text.length < joined.length; j++) {
          text += this.tokens[j];
          if (text === joined && ++seen === nth) return { first: i, last: j };
        }
      }
      return null;
    }

    resolve(phrase, nth) {
      const key = `${phrase}|${nth}`;
      if (state.dry) {
        const log = (state.cuePlans.get(this.id) || state.cuePlans.set(this.id, { order: [], times: new Map() }).get(this.id));
        if (!log.order.includes(key)) log.order.push(key);
        const guess = this.frac(0.5);
        return { start: guess, end: guess };
      }
      return state.cuePlans.get(this.id).times.get(key);
    }

    // The time this phrase starts being spoken in this scene. A phrase that is not found gets a
    // proportional time between its neighbours and a warning, so changed wording cannot break a render.
    cue(phrase, { nth = 1 } = {}) { return this.resolve(phrase, nth).start; }

    // The time this phrase finishes being spoken.
    cueEnd(phrase, { nth = 1 } = {}) { return this.resolve(phrase, nth).end; }

    // Paces the scene. Takes a cue phrase or a time and how long the change takes, and returns when to
    // start it: at the cue, unless the last change has not been seen for long enough. Never so late
    // that the scene cannot end on a settled frame.
    beat(when, dur = 0.5, hold = 0.8) {
      const wanted = typeof when === 'string' ? this.cue(when) : when;
      const earliest = this.lastLand === null ? this.t1 : this.lastLand + hold;
      let start = Math.max(wanted, earliest);
      if (Number.isFinite(this.out0)) start = Math.min(start, this.out0 - 0.5 - dur);
      this.lastLand = Math.max(this.lastLand === null ? 0 : this.lastLand, start + dur);
      return start;
    }
  }

  function planCues(scene) {
    const plan = state.cuePlans.get(scene.id);
    if (!plan) return;
    const entries = plan.order.map((key) => {
      const [phrase, nth] = key.split('|');
      const at = scene.locate(phrase, Number(nth));
      return { key, phrase, at, start: at ? scene.words[at.first].start : null, end: at ? scene.words[at.last].end : null };
    });
    entries.forEach((entry, i) => {
      if (entry.at) return;
      let before = i - 1;
      while (before >= 0 && !entries[before].at) before--;
      let after = i + 1;
      while (after < entries.length && !entries[after].at) after++;
      const lo = before >= 0 ? entries[before].start : scene.start;
      const hi = after < entries.length ? entries[after].start : scene.end;
      const span = after - before;
      const time = Math.min(Math.max(lo, scene.start) + ((Math.max(hi, lo) - lo) * (i - before)) / span, scene.end);
      entry.start = time;
      entry.end = Math.min(time + 0.4, scene.end);
      warn(`Cue "${entry.phrase}" not found in scene ${scene.id}. Using proportional time ${time.toFixed(2)}s.`);
    });
    for (const entry of entries) plan.times.set(entry.key, { start: entry.start, end: entry.end });
  }

  // ---- Transitions ----------------------------------------------------------------------------

  const SCENE_CUT = 0.7;
  const SECTION_CUT = 1.0;
  const SETTLE_AFTER_WORDS = 0.55;
  const NEW_PICTURE_LAG = 0.35;

  function sceneInfos(timing, sections) {
    const sectionOf = new Map();
    sections.forEach((section, i) => section.scenes.forEach((id) => sectionOf.set(id, i)));
    const scenes = timing.scenes;
    const infos = scenes.map((s) => ({ ...s, section: sectionOf.has(s.id) ? sectionOf.get(s.id) : -1, t0: 0, t1: 0, out0: Infinity, out1: Infinity }));
    for (let i = 1; i < infos.length; i++) {
      const before = infos[i - 1];
      const scene = infos[i];
      const major = before.section !== scene.section;
      const cut = major ? SECTION_CUT : SCENE_CUT;
      const t1 = Math.max(scene.start + NEW_PICTURE_LAG, before.end + SETTLE_AFTER_WORDS + cut);
      before.out0 = t1 - cut;
      before.out1 = t1;
      before.major = major;
      scene.t0 = t1 - cut;
      scene.t1 = t1;
    }
    return infos;
  }

  // Engine-owned fades on a block's root, from the timing alone.
  function fadeBlock(block, first, last) {
    const root = block.root;
    state.block = { items: [], engineOwned: true };
    if (first.t1 > 0) root.add('opacity', first.t1 - 0.62 * (first.t1 - first.t0), 0.62 * (first.t1 - first.t0), 1, 0);
    if (Number.isFinite(last.out0)) root.add('opacity', last.out0, 0.62 * (last.out1 - last.out0), 0);
    state.block = null;
    block.from = first.t0;
    block.until = last.out1;
  }

  // ---- The quiet progress strip ---------------------------------------------------------------

  function buildStrip(root, sections, infos) {
    const { C } = PE;
    const n = sections.length;
    const x0 = 80;
    const total = 1760;
    const gap = 24;
    const w = (total - gap * (n - 1)) / n;
    const startOf = sections.map((section) => infos.find((s) => s.id === section.scenes[0]));
    sections.forEach((section, i) => {
      const x = x0 + i * (w + gap);
      const label = root.text(section.name, { x, y: 34, size: 28, weight: 600, color: i === 0 ? C.navy : C.strong });
      const bar = root.box({ x, y: 60, w, h: 4, fill: i === 0 ? C.navy : C.hairline });
      const begin = startOf[i];
      if (i > 0 && begin) {
        label.to({ color: C.navy }, begin.t0, 0.8);
        bar.to({ bg: C.navy }, begin.t0, 0.8);
      }
      const next = startOf[i + 1];
      if (next) {
        label.to({ color: C.strong }, next.t0, 0.8);
        bar.to({ bg: C.sky }, next.t0, 0.8);
      }
    });
  }

  // ---- Shared drawing helpers -----------------------------------------------------------------

  const kit = PE.kit;

  const measureCanvas = document.createElement('canvas').getContext('2d');
  kit.monoAdvance = (size, weight = 500) => {
    measureCanvas.font = `${weight} ${size}px "Martian Mono"`;
    return measureCanvas.measureText('0000000000').width / 10;
  };

  // A captioned note at a fixed place near the bottom of the stage.
  kit.caption = (g, text, { x = 960, y = 1024, align = 'center', size = 30, color } = {}) => g.text(text, { x, y, align, size, color: color || PE.C.inkMuted });

  kit.arrowHead = (x, y, dir, s = 16) => {
    const a = { right: [[-s, -s * 0.7], [-s, s * 0.7]], left: [[s, -s * 0.7], [s, s * 0.7]], up: [[-s * 0.7, s], [s * 0.7, s]], down: [[-s * 0.7, -s], [s * 0.7, -s]] }[dir];
    return `M${x} ${y} L${x + a[0][0]} ${y + a[0][1]} L${x + a[1][0]} ${y + a[1][1]} Z`;
  };

  // A straight arrow that draws from start to end, then shows its head.
  kit.arrow = (g, x1, y1, x2, y2, { color, width = 5, head = 16 } = {}) => {
    const c = color || PE.C.navy;
    const horizontal = Math.abs(x2 - x1) >= Math.abs(y2 - y1);
    const dir = horizontal ? (x2 > x1 ? 'right' : 'left') : y2 > y1 ? 'down' : 'up';
    const line = g.path(`M${x1} ${y1} L${horizontal ? x2 - Math.sign(x2 - x1) * head : x2} ${horizontal ? y2 : y2 - Math.sign(y2 - y1) * head}`, { stroke: c, width });
    const tip = g.path(kit.arrowHead(x2, y2, dir, head), { fill: c });
    return {
      line,
      tip,
      draw(t, dur = 0.7) {
        line.drawIn(t, dur);
        tip.in(t + dur - 0.4, 0.4);
        return this;
      },
    };
  };

  kit.tick = (g, x, y, size = 60, color) => g.path(`M${x - size * 0.42} ${y + size * 0.02} L${x - size * 0.1} ${y + size * 0.34} L${x + size * 0.46} ${y - size * 0.34}`, { stroke: color || PE.C.success, width: size * 0.17, cap: 'round' });

  kit.cross = (g, x, y, size = 60, color) => {
    const c = color || PE.C.danger;
    const s = size * 0.36;
    return g.path(`M${x - s} ${y - s} L${x + s} ${y + s} M${x + s} ${y - s} L${x - s} ${y + s}`, { stroke: c, width: size * 0.17, cap: 'round' });
  };

  // A padlock, drawn from a body and a shackle, centred on x and y.
  kit.padlock = (g, x, y, size = 64, color) => {
    const c = color || PE.C.navy;
    const group = g.group({ x, y });
    const u = size / 64;
    group.path(`M${-16 * u} ${-4 * u} V${-16 * u} A${16 * u} ${16 * u} 0 0 1 ${16 * u} ${-16 * u} V${-4 * u}`, { stroke: c, width: 7 * u });
    group.box({ x: -24 * u, y: -6 * u, w: 48 * u, h: 36 * u, fill: c, r: 6 * u });
    return group;
  };

  // A person at a desk: a head and shoulders.
  kit.person = (g, x, y, size = 80, color) => {
    const c = color || PE.C.navy;
    const u = size / 80;
    const group = g.group({ x, y });
    const head = group.box({ x: -16 * u, y: -38 * u, w: 32 * u, h: 32 * u, fill: c, r: 16 * u });
    const body = group.path(`M${-30 * u} ${34 * u} V${22 * u} A${22 * u} ${22 * u} 0 0 1 ${-8 * u} ${0} H${8 * u} A${22 * u} ${22 * u} 0 0 1 ${30 * u} ${22 * u} V${34 * u} Z`, { fill: c });
    return Object.assign(group, { head, body });
  };

  // A stamp: a bordered word.
  kit.stamp = (g, text, { x, y, w, h = 110, size = 56, color }) => {
    const c = color || PE.C.danger;
    const group = g.group({ x: x + w / 2, y: y + h / 2 });
    group.box({ x: -w / 2, y: -h / 2, w, h, stroke: c, sw: 6, r: 10, fill: PE.C.surface });
    group.text(text, { x: 0, y: 0, align: 'center', size, weight: 800, font: 'display', color: c });
    return group;
  };

  kit.LEVEL_COLORS = () => [PE.C.skyPale, PE.C.sky, PE.C.navy];
  kit.LEVEL_INK = () => [PE.C.navy, PE.C.navy, PE.C.inverse];

  // A bar split into three levels. Its segments can be moved to a new split or a new size.
  kit.levelBar = (g, { x, y, w, h, levels, r = 8, opacity = 1 }) => {
    const group = g.group({ x, y, opacity });
    const colors = kit.LEVEL_COLORS();
    const total = levels.reduce((a, b) => a + b, 0);
    let at = 0;
    const segs = levels.map((level, i) => {
      const width = (level / total) * w;
      const seg = group.box({ x: at, y: 0, w: width, h, fill: colors[i] });
      at += width;
      return seg;
    });
    const bar = {
      group,
      segs,
      w,
      h,
      levels,
      // The centre of a segment, in the bar's parent coordinates.
      center(i, ls = levels, width = w, left = x) {
        let a = 0;
        for (let j = 0; j < i; j++) a += ls[j];
        return left + (a + ls[i] / 2) * width;
      },
      // Changes the split, keeping the bar's position.
      morph(next, t, dur = 0.9, width = w, height = h) {
        let a = 0;
        next.forEach((level, i) => {
          segs[i].to({ x: a * width, width: level * width, height }, t, dur);
          a += level;
        });
        return bar;
      },
      // Grows from the left.
      reveal(t, dur = 0.7) {
        let a = 0;
        levels.forEach((level, i) => {
          segs[i].add('x', t, dur, a * w, 0);
          segs[i].add('width', t, dur, level * w, 0);
          a += level;
        });
        return bar;
      },
    };
    return bar;
  };

  kit.textWidth = (text, size, weight = 400, font = 'text') => {
    measureCanvas.font = `${weight} ${size}px ${PE.F[font]}`;
    return measureCanvas.measureText(text).width;
  };

  // A short label in a filled pill. y is its vertical centre.
  kit.pill = (g, text, { x, y, align = 'left', size = 28, fill, color, weight = 600 }) => {
    const item = g.text(text, { x, y, align, size, weight, color: color || PE.C.inverse });
    item.inner.style.background = fill || PE.C.navy;
    item.inner.style.padding = '6px 20px';
    item.inner.style.borderRadius = '999px';
    return item;
  };

  // A row of monospaced tokens, left aligned from x. Returns each token's item and centre.
  kit.monoRow = (g, tokens, { x, y, size, weight = 500, color, gap = 1, opacity = 1 }) => {
    const adv = kit.monoAdvance(size, weight);
    let at = x;
    return tokens.map((token) => {
      const width = token.length * adv;
      const item = g.text(token, { x: at, y, size, weight, font: 'mono', color, opacity });
      const placed = { item, left: at, right: at + width, center: at + width / 2, width };
      at += width + gap * adv;
      return placed;
    });
  };

  // ---- Boot, seek, lint and audit -------------------------------------------------------------

  async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Could not load ${url}`);
    return res.json();
  }
  async function fetchText(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Could not load ${url}`);
    return res.text();
  }

  function parseStory(text) {
    const table = (letter) => {
      const start = text.indexOf(`=== ${letter}:`);
      const rows = text.slice(start).split('\n').slice(2);
      const out = [];
      for (const row of rows) {
        if (!row.trim() || row.startsWith('===')) break;
        const cells = row.trim().split(/\s+/).map(Number);
        out.push({ reviews: cells[0], loss: cells[2] });
      }
      return out;
    };
    return { corrections: table('A'), every: table('B') };
  }

  function parseAnchors(yaml, scale) {
    const m = yaml.match(new RegExp(`key: risk\\.anchors\\.${scale}\\s*\\n\\s*value: \\[([^\\]]+)\\]`));
    if (!m) throw new Error(`No anchors for ${scale}`);
    return m[1].split(',').map(Number);
  }

  function resolveTokens() {
    const css = getComputedStyle(document.documentElement);
    const token = (name) => css.getPropertyValue(name).trim();
    const names = { navy: '--pe-navy', blue: '--pe-blue', sky: '--pe-sky', skyPale: '--pe-sky-pale', amber: '--pe-amber', sand: '--pe-sand', surface: '--pe-surface', muted: '--pe-surface-muted', sunken: '--pe-surface-sunken', tint: '--pe-surface-tint', heading: '--pe-heading', ink: '--pe-ink', inkMuted: '--pe-ink-muted', inverse: '--pe-ink-inverse', inverseMuted: '--pe-ink-inverse-muted', hairline: '--pe-hairline', strong: '--pe-border-strong', success: '--pe-success', successSoft: '--pe-success-soft', danger: '--pe-danger', dangerSoft: '--pe-danger-soft', warning: '--pe-warning', warningSoft: '--pe-warning-soft', grid: '--pe-chart-grid' };
    for (const key of Object.keys(names)) PE.C[key] = token(names[key]);
    PE.F.display = token('--pe-font-display');
    PE.F.text = token('--pe-font-text');
    PE.F.mono = token('--pe-font-mono');
  }

  async function loadFonts() {
    const specs = ['400 32px "Atkinson Hyperlegible Next"', '600 32px "Atkinson Hyperlegible Next"', '700 32px "Atkinson Hyperlegible Next"', '700 40px "Schibsted Grotesk"', '800 40px "Schibsted Grotesk"', '500 40px "Martian Mono"', '700 40px "Martian Mono"'];
    await Promise.all(specs.map((spec) => document.fonts.load(spec, '0123456789 abc')));
    await document.fonts.ready;
  }

  function buildAll(defs, sections) {
    state.textItems = [];
    state.tweens = [];
    state.blocks = [];
    const stage = state.stage;
    stage.innerHTML = '';
    state.scenes = sceneInfos(state.timing, sections).map((info) => new Scene(info));
    state.sceneById = new Map(state.scenes.map((s) => [s.id, s]));
    if (!state.dry) state.scenes.forEach(planCues);

    state.block = { items: [], engineOwned: true };
    const strip = new Group(div(stage));
    buildStrip(strip, sections, state.scenes);
    const stripBlock = { root: strip, items: state.block.items, from: 0, until: Infinity, visible: true };
    state.block = null;

    for (const def of defs) {
      const handles = def.scenes.map((id) => state.sceneById.get(id));
      if (handles.some((h) => !h)) {
        warn(`Block for ${def.scenes.join(', ')} is missing from the timing file and was skipped.`);
        continue;
      }
      const block = { items: [] };
      state.block = block;
      const root = new Group(div(stage));
      block.root = root;
      def.build(root, ...handles);
      fadeBlock(block, handles[0], handles[handles.length - 1]);
      block.visible = true;
      state.blocks.push(block);
      state.block = null;
    }
    state.blocks.unshift(stripBlock);
    for (const block of state.blocks) {
      for (const item of block.items) item.finalize();
      block.root.finalize();
    }
  }

  function seek(t) {
    let changed = false;
    for (const block of state.blocks) {
      const visible = t >= block.from && t <= block.until;
      if (visible !== block.visible) {
        block.root.el.style.display = visible ? 'block' : 'none';
        block.visible = visible;
        changed = true;
      }
      if (!visible) continue;
      if (block.root.apply(t)) changed = true;
      for (const item of block.items) if (item !== block.root && item.apply(t)) changed = true;
    }
    return changed;
  }
  window.seek = seek;

  // Resolves after the frame for t has been painted. The renderer uses this. It adds no timing of its own.
  window.seekPainted = (t) => {
    const changed = seek(t);
    if (!changed) return Promise.resolve(false);
    return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))));
  };

  // Pacing check, from the registered tweens. It reports. It never changes the picture.
  function lint() {
    for (const tween of state.tweens) {
      const dur = tween.t1 - tween.t0;
      if (dur > 0 && dur < 0.399) warn(`Change of ${dur.toFixed(2)}s at ${tween.t0.toFixed(2)}s is under 0.4s.`);
    }
    const cuts = state.scenes.filter((s) => s.t1 > s.t0).map((s) => [s.t0, s.t1]);
    const spans = [...state.tweens.filter((t) => t.t1 > t.t0).map((t) => [t.t0, t.t1]), ...cuts].sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const span of spans) {
      const last = merged[merged.length - 1];
      if (last && span[0] <= last[1]) last[1] = Math.max(last[1], span[1]);
      else merged.push([span[0], span[1]]);
    }
    const stats = { beats: merged.length, shortHolds: 0, holds: [], longStills: [] };
    for (let i = 1; i < merged.length; i++) {
      const hold = merged[i][0] - merged[i - 1][1];
      if (hold < 0.6) {
        stats.shortHolds++;
        stats.holds.push(`${merged[i][0].toFixed(1)}(${hold.toFixed(2)})`);
      }
      if (hold > 2.5) stats.longStills.push(`${merged[i - 1][1].toFixed(1)}s to ${merged[i][0].toFixed(1)}s`);
    }
    for (const still of stats.longStills) warn(`Nothing changes from ${still}.`);
    for (const scene of state.scenes) {
      if (!Number.isFinite(scene.out0)) continue;
      const land = Math.max(...state.tweens.filter((t) => t.t1 > t.t0 && t.t0 < scene.out0).map((t) => t.t1));
      if (scene.out0 - land < 0.4) warn(`Scene ${scene.id} settles only ${(scene.out0 - land).toFixed(2)}s before its transition.`);
    }
    return stats;
  }

  // Layout check for review: text that clips, overlaps other text, or uses banned wording at the current frame.
  window.__audit = () => {
    const problems = [];
    const seen = [];
    const opacityOf = (el) => {
      let o = 1;
      for (let n = el; n && n !== document.body; n = n.parentElement) {
        const s = getComputedStyle(n);
        if (s.display === 'none') return 0;
        o *= Number(s.opacity);
      }
      return o;
    };
    for (const item of state.textItems) {
      const text = item.inner.textContent;
      const opacity = opacityOf(item.el);
      if (opacity < 0.3 || !text.trim()) continue;
      if (/[—–]/.test(text)) problems.push(`Dash in "${text.slice(0, 40)}"`);
      if (/\bexpert\b/i.test(text) && !/rubric/i.test(text)) problems.push(`"expert" in "${text.slice(0, 40)}"`);
      if (!item.isText) continue;
      const range = document.createRange();
      range.selectNodeContents(item.inner);
      const rect = range.getBoundingClientRect();
      if (rect.left < -1 || rect.top < -1 || rect.right > PE.W + 1 || rect.bottom > PE.H + 1) problems.push(`Off stage: "${text.slice(0, 40)}"`);
      const effective = item.size * (item.inner.getBoundingClientRect().height / (item.inner.offsetHeight || 1));
      if (effective < 27.5) problems.push(`Under 28px (${effective.toFixed(1)}): "${text.slice(0, 40)}"`);
      for (const other of seen) {
        const r = other.rect;
        const overlapX = Math.min(rect.right, r.right) - Math.max(rect.left, r.left);
        const overlapY = Math.min(rect.bottom, r.bottom) - Math.max(rect.top, r.top);
        if (overlapX > 3 && overlapY > 6) problems.push(`Overlap: "${text.slice(0, 30)}" and "${other.text.slice(0, 30)}"`);
      }
      seen.push({ rect, text });
    }
    return problems;
  };

  PE.boot = async (video) => {
    try {
      resolveTokens();
      await loadFonts();
      const [timing, allSections, narration, kase, final, learning, tone, story, settings, events] = await Promise.all([
        fetchJson(`timing/${video}.json`), fetchJson('sections.json'), fetchJson('narration.json'), fetchJson('/data/case.json'), fetchJson('/data/final.json'), fetchJson('/data/learning.json'), fetchJson('/data/tone.json'), fetchText('/data/story.txt'), fetchText('/data/settings.yaml'), fetchJson('/data/events.json'),
      ]);
      PE.data = { case: kase, final, learning, tone, story: parseStory(story), anchors: { likelihood: parseAnchors(settings, 'likelihood'), severity: parseAnchors(settings, 'severity') }, events: events.filter((e) => e.case_id === kase.case_id) };
      for (const scene of narration[video] || []) {
        const timed = timing.scenes.find((s) => s.id === scene.id);
        if (!timed) warn(`Scene ${scene.id} is in narration.json but not in the timing file.`);
        else if (timed.words.map((w) => normalize(w.w)).join(' ') !== scene.text.trim().split(/\s+/).map(normalize).join(' ')) warn(`Scene ${scene.id}: timing words differ from narration.json.`);
      }
      state.stage = document.getElementById('stage');
      state.timing = timing;
      const defs = () => PE.videos[video]();
      state.cuePlans = new Map();
      state.dry = true;
      buildAll(defs(), allSections[video]);
      state.dry = false;
      buildAll(defs(), allSections[video]);
      const last = timing.scenes[timing.scenes.length - 1];
      state.duration = Math.max(timing.duration, last.end + 1);
      const stats = lint();
      // Every frame must draw, so a long render cannot fail partway through.
      for (let n = Math.ceil(state.duration * 30); n >= 0; n--) seek(n / 30);
      seek(0);
      return { video, duration: state.duration, warnings: PE.warnings, stats, scenes: state.scenes.map((s) => ({ id: s.id, start: s.start, end: s.end, t0: s.t0, t1: s.t1, out0: Number.isFinite(s.out0) ? s.out0 : state.duration })) };
    } catch (error) {
      console.error(error);
      return { error: `${error.message}\n${error.stack}` };
    }
  };
})();
