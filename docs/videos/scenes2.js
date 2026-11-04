// Video 2: inside one decision, and how it was tested. All numbers come from the case file and results.
// Scene code places visuals by cue phrases. It never contains narration or times.
(function () {
  'use strict';

  const HAZARD_ORDER = ['traffic_conflict', 'crowd_pressure', 'medical_emergency'];
  const RULE_WORDS = { traffic_conflict: 'a road closes', crowd_pressure: 'crowd of 300 or more', medical_emergency: 'every race' };
  const CAPTION_SYNTHETIC = 'Synthetic data. Answer key written by the author.';

  // The tree, in stage coordinates. It stays left of the scoreboard.
  const TREE = {
    root: { x: 30, w: 200, cy: 620, h: 170 },
    mid: { x: 400, w: 240, h: 130, cy: [300, 700] },
    leaf: { x: 1040, w: 280, h: 52, rows: [190, 410, 700, 930] },
  };
  const FLOW_WIDTH = 104;
  const BOARD = { x: 1350, y: 100, w: 540, h: 430, right: 1866, left: 1374 };
  const BLEND = { x: 620, w: 690, h: 130, cy: 560 };

  // Equation geometry, shared by the equation block and the scoreboard's first number.
  const EQ = { bar: { x: 60, y: 120, w: 1240, h: 80 }, rowsX: 320, rowY: [350, 450, 550], termSize: 60, resultY: 680, resultSize: 96 };
  const METER = { x: 60, y: 560, w: 1240, h: 90, max: 0.25 };

  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const longDate = (iso) => {
    const [y, m, d] = iso.split('-').map(Number);
    return `${MONTHS[m - 1]} ${d}, ${y}`;
  };
  const curve = (x1, y1, x2, y2) => `M${x1} ${y1} C${(x1 + x2) / 2} ${y1},${(x1 + x2) / 2} ${y2},${x2} ${y2}`;
  const pct = (v) => `${Math.round(v * 100)}%`;
  const flowText = (v) => (v < 0.01 ? v.toFixed(3) : v.toFixed(2));

  PE.videos.video2 = () => {
    const { C, kit, data } = PE;
    const kase = data.case;
    const form = kase.documents.form;
    const hazards = Object.fromEntries(kase.hazards.map((h) => [h.id, h]));
    const traffic = hazards.traffic_conflict;
    const L = traffic.likelihood;
    const S = traffic.severity;
    const [q1, q2] = L.questions;
    const anchors = data.anchors.likelihood;
    const leafAt = (yes1, yes2) => L.leaves.find((l) => l.when[q1.id] === yes1 && l.when[q2.id] === yes2);
    // Leaves top to bottom: escort and plan, escort without plan, plan without escort, neither.
    const leaves = [leafAt(true, true), leafAt(true, false), leafAt(false, true), leafAt(false, false)];
    const THICK = 2;
    const lValue = L.value.toFixed(3);
    const sValue = S.value.toFixed(2);
    const products = HAZARD_ORDER.map((id) => hazards[id].product.toFixed(4));
    const riskValue = kase.risk.toFixed(3);
    const approval = kase.t_low;
    const officerLabel = kase.officer.label;
    const police = kase.evidence.find((e) => e.evidence_type === 'police_escort_letter');
    const verdict = police.verdict[0].toUpperCase() + police.verdict.slice(1);
    const letterDate = police.fields.find((f) => f.name === 'event_date').value;
    const meterX = (v) => METER.x + (v / METER.max) * METER.w;
    const adv = (size, weight = 500) => kit.monoAdvance(size, weight);
    const shared = {};

    // ---- 2.1: the application form.
    function formScene(g, s) {
      g.box({ x: 360, y: 96, w: 1200, h: 910, fill: C.surface, stroke: C.hairline, sw: 2, r: 14 });
      g.text('Made-up application', { x: 420, y: 164, size: 48, weight: 700, font: 'display', color: C.heading });
      const rows = [
        ['Event', form.event_name],
        ['Date', longDate(form.event_date)],
        ['Venue', form.venue],
        ['Organiser', form.organizer],
        ['Expected runners', String(form.expected_runners), 'runners'],
        ['Road closure', form.route.road_closure ? 'Yes' : 'No', 'road'],
      ];
      const made = rows.map(([name, value, key], i) => {
        const y = 284 + i * 118;
        const light = key ? g.box({ x: 392, y: y - 52, w: 1136, h: 104, fill: C.sand, r: 10, opacity: 0 }) : null;
        const row = g.group({});
        row.text(name, { x: 420, y, size: 34, color: C.inkMuted });
        row.text(value, { x: 840, y, size: key ? 64 : 40, weight: 700, font: key ? 'mono' : 'text', color: C.navy });
        return { key, light, row };
      });
      const runners = made.find((m) => m.key === 'runners');
      const road = made.find((m) => m.key === 'road');
      const t1 = s.beat('900 runners', 0.6);
      runners.light.to({ opacity: 1 }, t1, 0.6);
      for (const m of made) if (!m.key) m.row.dim(t1, 0.42, 0.6);
      road.row.dim(t1, 0.42, 0.6);
      const t2 = s.beat('closed road', 0.6, 0.5);
      road.light.to({ opacity: 1 }, t2, 0.6);
      road.row.lit(t2, 0.6);
    }

    // ---- 2.2: three hazards, one at a time.
    function hazardScene(g, s) {
      g.text('Written rules pick the hazards', { x: 100, y: 190, size: 52, weight: 700, font: 'display', color: C.heading });
      const cues = ['traffic', 'crowd pressure', 'medical'];
      HAZARD_ORDER.forEach((id, i) => {
        const card = g.group({});
        const x = 100 + i * 590;
        card.box({ x, y: 300, w: 550, h: 460, fill: C.tint, r: 14 });
        card.text(hazards[id].name, { x: x + 40, y: 400, w: 470, size: 56, weight: 700, font: 'display', color: C.navy, lh: 1.1 });
        card.text('Applies when', { x: x + 40, y: 560, size: 30, color: C.inkMuted });
        card.text(RULE_WORDS[id], { x: x + 40, y: 640, w: 470, size: 44, weight: 600, color: C.ink, lh: 1.14 });
        card.in(s.beat(cues[i], 0.6, 0.15), 0.6, { dy: 16 });
      });
    }

    // Water paths through the tree. Each width is the real share of the case that reaches it.
    function flowPaths() {
      const { root, mid, leaf } = TREE;
      const out = root.x + root.w;
      const yesShare = leaves[0].reach + leaves[1].reach;
      const noShare = leaves[2].reach + leaves[3].reach;
      const top = root.cy - FLOW_WIDTH / 2;
      const branches = [
        { share: yesShare, y1: top + (yesShare * FLOW_WIDTH) / 2, node: 0 },
        { share: noShare, y1: top + yesShare * FLOW_WIDTH + (noShare * FLOW_WIDTH) / 2, node: 1 },
      ].map((b) => ({ ...b, d: curve(out, b.y1, mid.x, mid.cy[b.node]), width: b.share * FLOW_WIDTH }));
      const twigs = [0, 1, 2, 3].map((i) => {
        const node = i < 2 ? 0 : 1;
        const share = node === 0 ? yesShare : noShare;
        const pair = node === 0 ? [leaves[0], leaves[1]] : [leaves[2], leaves[3]];
        const start = mid.cy[node] - (share * FLOW_WIDTH) / 2;
        const before = i % 2 === 0 ? 0 : pair[0].reach;
        const y1 = start + (before + leaves[i].reach / 2) * FLOW_WIDTH;
        return { d: curve(mid.x + mid.w, y1, leaf.x, leaf.rows[i]), width: leaves[i].reach * FLOW_WIDTH };
      });
      return { branches, twigs };
    }

    // The bare tree. Its parts are the same at small and full size.
    function treeOutline(g, between, flows) {
      const { root, mid, leaf } = TREE;
      const lines = [];
      if (flows) {
        for (const b of [...flows.branches, ...flows.twigs]) lines.push(g.path(b.d, { stroke: C.strong, width: 6 }));
      } else {
        mid.cy.forEach((cy) => lines.push(g.path(curve(root.x + root.w, root.cy, mid.x, cy), { stroke: C.strong, width: 7 })));
        leaf.rows.forEach((y, i) => lines.push(g.path(curve(mid.x + mid.w, mid.cy[i < 2 ? 0 : 1], leaf.x, y), { stroke: C.strong, width: 7 })));
      }
      if (between) between();
      const rootBox = g.box({ x: root.x, y: root.cy - root.h / 2, w: root.w, h: root.h, fill: C.skyPale, r: 12 });
      const midBoxes = mid.cy.map((cy) => g.box({ x: mid.x, y: cy - mid.h / 2, w: mid.w, h: mid.h, fill: C.skyPale, r: 12 }));
      const tracks = leaf.rows.map((y) => g.box({ x: leaf.x, y: y - leaf.h / 2, w: leaf.w, h: leaf.h, fill: C.surface, stroke: C.strong, sw: 6, r: 6 }));
      return { lines, rootBox, midBoxes, tracks };
    }

    // ---- 2.3 to 2.7: the trees, from six small ones to one blended bar.
    function treeScenes(g, s23, s24, s25, s26, s27) {
      const small = 0.3;
      const colX = [560, 1270];
      const rowTop = (r) => 170 + r * 290;
      const place = (c, r) => ({ x: colX[c] - small * 30, y: rowTop(r) - small * 165 });
      const { root, mid, leaf } = TREE;

      // 2.3: six small trees, two per hazard.
      const heads = [
        g.text('likelihood', { x: colX[0] + 194, y: 124, align: 'center', size: 36, weight: 700, font: 'display', color: C.heading }),
        g.text('severity (how bad)', { x: colX[1] + 194, y: 124, align: 'center', size: 36, weight: 700, font: 'display', color: C.heading }),
      ];
      const names = HAZARD_ORDER.map((id, r) => g.text(hazards[id].name, { x: 90, y: rowTop(r) + 118, w: 340, size: 40, weight: 600, color: C.heading, lh: 1.1 }));
      const others = [];
      const columns = [[], []];
      HAZARD_ORDER.forEach((id, r) => {
        [0, 1].forEach((c) => {
          if (r === 0 && c === 0) return;
          const tree = g.group({ ...place(c, r), scale: small });
          treeOutline(tree);
          others.push(tree);
          columns[c].push(tree);
        });
      });

      const big = g.group({ ...place(0, 0), scale: small });
      columns[0].push(big);
      const flows = flowPaths();
      const water = { branches: [], twigs: [] };
      const outline = treeOutline(big, () => {
        water.branches = flows.branches.map((b) => big.path(b.d, { stroke: C.navy, width: b.width }));
        water.twigs = flows.twigs.map((b) => big.path(b.d, { stroke: C.navy, width: b.width }));
      }, flows);
      [...water.branches, ...water.twigs].forEach((path) => path.to({ draw: 0 }, 0, 0));
      const rootText = big.text(q1.text, { x: root.x + root.w / 2, y: root.cy, w: root.w - 24, align: 'center', size: 30, weight: 600, color: C.navy, lh: 1.14, opacity: 0 });
      const midTexts = mid.cy.map((cy) => big.text(q2.text, { x: mid.x + mid.w / 2, y: cy, w: mid.w - 24, align: 'center', size: 30, weight: 600, color: C.navy, lh: 1.14, opacity: 0 }));
      const title = g.text(`${traffic.name}: how likely`, { x: 40, y: 118, size: 40, weight: 700, font: 'display', color: C.heading });

      let t = s23.beat('how likely', 0.6);
      columns[1].forEach((tree) => tree.dim(t, 0.28, 0.6));
      heads[1].dim(t, 0.28, 0.6);
      t = s23.beat('how bad', 0.6, 0.3);
      columns[1].forEach((tree) => tree.lit(t, 0.6));
      heads[1].lit(t, 0.6);
      columns[0].forEach((tree) => tree.dim(t, 0.28, 0.6));
      heads[0].dim(t, 0.28, 0.6);
      const tFade = s23.beat('Take one', 0.6, 0.5);
      others.forEach((tree) => tree.out(tFade, 0.6));
      heads.forEach((head) => head.out(tFade, 0.6));
      names.forEach((name) => name.out(tFade, 0.6));
      big.lit(tFade, 0.6);
      const tGrow = s23.beat(tFade + 0.7, 0.9, 0);
      big.to({ x: 0, y: 0, scale: 1 }, tGrow, 0.9);
      title.in(s23.beat('traffic conflict', 0.5, 0.2), 0.5);

      // 2.4: the first question. A fixed value from a code check.
      const answer = g.group({});
      const panelX = 300;
      const dateCards = ['Form', 'Letter'].map((name, i) => {
        const card = answer.group({});
        const x = panelX + i * 500;
        card.box({ x, y: 170, w: 470, h: 130, fill: C.muted, stroke: i ? C.danger : C.hairline, sw: 3, r: 12 });
        card.text(name, { x: x + 28, y: 235, size: 30, color: C.inkMuted });
        card.text(i ? letterDate : longDate(form.event_date), { x: x + 446, y: 235, align: 'right', size: 28, weight: 700, font: 'mono', color: i ? C.danger : C.navy });
        return card;
      });
      const stamp = kit.stamp(answer, verdict, { x: panelX + 500, y: 322, w: 470, h: 100, size: 50 });
      const barY = 490;
      const barW = 970;
      const yesNo = answer.group({});
      yesNo.box({ x: panelX, y: barY, w: barW, h: 64, fill: C.skyPale, r: 6 });
      yesNo.box({ x: panelX, y: barY, w: Math.max(barW * q1.answer, 6), h: 64, fill: C.navy, r: 6 });
      const fixed = answer.text(`yes ${q1.answer.toFixed(2)}, no ${(1 - q1.answer).toFixed(2)}.<br>Fixed value, set by a code check. No AI.`, { x: panelX, y: 620, w: barW, size: 36, weight: 600, color: C.heading, lh: 1.25, html: true });
      const bigNumber = answer.text(q1.answer.toFixed(2), { x: panelX, y: 790, size: 150, weight: 700, font: 'mono', color: C.navy });

      const quietTree = [...outline.lines, ...outline.midBoxes, ...outline.tracks];
      const tAsk = s24.t1;
      outline.rootBox.to({ bg: C.navy }, tAsk, 0.6);
      rootText.in(tAsk, 0.6);
      rootText.to({ color: C.inverse }, tAsk, 0.6);
      quietTree.forEach((item) => item.out(tAsk, 0.6));
      s24.lastLand = tAsk + 0.6;
      const tCards = s24.beat('letter', 0.5, 0.5);
      dateCards[0].in(tCards, 0.5);
      dateCards[1].in(tCards + 0.35, 0.5);
      s24.beat(tCards + 0.35, 0.5, 0);
      stamp.in(s24.beat('wrong date', 0.6, 0.3), 0.6, { scale: 1.06 });
      const tFixed = s24.beat('fixed', 0.6, 0.5);
      yesNo.in(tFixed, 0.6);
      fixed.in(tFixed, 0.6);
      bigNumber.in(s24.beat('point zero five', 0.5, 0.5), 0.5);

      // 2.5: the second question. Jev, slowed down to show the idea.
      const jev = g.group({});
      jev.text(q2.text, { x: 40, y: 124, size: 44, weight: 700, font: 'display', color: C.heading });
      const planWindow = jev.group({ x: 40, y: 180, clip: true, w: 720, h: 830, r: 12 });
      planWindow.box({ x: 0, y: 0, w: 720, h: 830, fill: C.muted });
      const planText = kase.documents.attachments.find((a) => a.name === 'traffic_plan.txt').text;
      const plan = planWindow.text(planText, { x: 36, y: 0, w: 648, size: 30, color: C.ink, lh: 1.42, audit: false });
      plan.inner.style.whiteSpace = 'pre-wrap';
      const planHeight = plan.inner.offsetHeight;
      plan.base.y = planHeight / 2 + 30;
      plan.writeTransform();
      jev.box({ x: 40, y: 180, w: 720, h: 830, stroke: C.hairline, sw: 2, r: 12 });
      jev.text('Jev', { x: 810, y: 290, size: 56, weight: 700, font: 'display', color: C.heading });
      const start = 0.5;
      const prob = jev.text(start.toFixed(2), { x: 810, y: 420, size: 150, weight: 700, font: 'mono', color: C.navy });
      const barLeft = 810;
      const barWide = 500;
      jev.box({ x: barLeft, y: 530, w: barWide, h: 40, fill: C.sunken, r: 6 });
      const probBar = jev.box({ x: barLeft, y: 530, w: barWide * start, h: 40, fill: C.navy, r: 6 });
      jev.text('Jev: AI model. Slowed down to show the idea. Answer stored ahead of time.', { x: 810, y: 710, w: 500, size: 34, weight: 600, color: C.heading, lh: 1.25 });

      answer.out(s25.t0, 0.5);
      outline.rootBox.out(s25.t0, 0.5);
      rootText.out(s25.t0, 0.5);
      title.out(s25.t0, 0.5);
      jev.in(s25.t0 + 0.2, 0.5);
      const climbFrom = s25.t1;
      const climbTo = Math.min(s25.cue('point nine six') + 0.5, s25.out0 - 0.6);
      const distance = Math.min(planHeight - 780, 170 * (climbTo - climbFrom));
      plan.to({ y: plan.base.y - distance }, climbFrom, climbTo - climbFrom, { ease: 'cruise', exempt: true });
      const steps = Math.max(6, Math.round((climbTo - climbFrom) / 0.72));
      const cadence = (climbTo - climbFrom) / steps;
      const stepDur = Math.max(0.42, cadence * 0.62);
      for (let i = 0; i < steps; i++) {
        const stepStart = climbFrom + (i + 1) * cadence - stepDur;
        const from = start + ((q2.answer - start) * i) / steps;
        const to = start + ((q2.answer - start) * (i + 1)) / steps;
        prob.count(from, to, stepStart, stepDur, (v) => v.toFixed(2), { exempt: true });
        probBar.to({ width: barWide * to }, stepStart, stepDur, { exempt: true });
      }
      s25.lastLand = climbTo;

      // 2.6: the tree draws, and the case splits in proportion.
      const whereYesNo = [
        big.text(`yes ${q1.answer.toFixed(2)}, no ${(1 - q1.answer).toFixed(2)}`, { x: root.x, y: root.cy + root.h / 2 + 50, w: root.w + 20, size: 28, color: C.inkMuted, lh: 1.15, opacity: 0 }),
        big.text(`yes ${q2.answer.toFixed(2)}, no ${(1 - q2.answer).toFixed(2)}`, { x: mid.x, y: mid.cy[1] + mid.h / 2 + 34, size: 28, color: C.inkMuted, opacity: 0 }),
      ];
      const treeReturn = s26.t0;
      jev.out(treeReturn, 0.5);
      const back = treeReturn + 0.2;
      outline.lines.forEach((item) => item.lit(back, 0.5));
      outline.midBoxes.forEach((item) => item.lit(back, 0.5));
      outline.tracks.forEach((item) => item.lit(back, 0.5));
      outline.rootBox.lit(back, 0.5);
      outline.rootBox.to({ bg: C.skyPale }, back, 0.5);
      rootText.lit(back, 0.5);
      rootText.to({ color: C.navy }, back, 0.5);
      midTexts.forEach((text) => text.in(back, 0.5));
      whereYesNo.forEach((text) => text.in(back, 0.5));
      title.lit(back, 0.5);
      s26.lastLand = back + 0.5;
      const tFirst = s26.beat('splits', 0.8, 0.1);
      water.branches.forEach((path) => path.to({ draw: 1 }, tFirst, 0.8));
      const tSecond = s26.beat('water', 0.8, 0.1);
      water.twigs.forEach((path) => path.to({ draw: 1 }, tSecond, 0.8));

      const flowY = leaf.rows[THICK];
      const eqWords = `${(1 - q1.answer).toFixed(2)} × ${q2.answer.toFixed(2)} = ${leaves[THICK].reach.toFixed(2)}`;
      const onFlow = big.text(eqWords, { x: (mid.x + mid.w + leaf.x) / 2, y: flowY, align: 'center', size: 28, weight: 700, font: 'mono', color: C.inverse });
      onFlow.in(s26.beat('91 percent', 0.5, 0.5), 0.5);
      const leafWord = big.text('leaf', { x: leaf.x + 8, y: flowY - 50, size: 30, weight: 700, color: C.heading });
      leafWord.in(s26.beat('one leaf', 0.5, 0.5), 0.5);
      const leafName = big.text('No confirmed escort, good plan', { x: leaf.x + leaf.w, y: flowY - 100, align: 'right', size: 30, weight: 700, color: C.heading });
      leafName.in(s26.beat('no confirmed escort', 0.5, 0.5), 0.5);
      outline.tracks[THICK].to({ bg: C.sand }, s26.beat('good plan', 0.5, 0.3), 0.5);

      // 2.7: numbered bars on the leaves, then one blended bar.
      const sliding = g.group({});
      const bars = leaves.map((l, i) => {
        const y = leaf.rows[i];
        const row = sliding.group({});
        const bar = kit.levelBar(row, { x: leaf.x, y: y - leaf.h / 2, w: leaf.w, h: leaf.h, levels: l.levels });
        const numbers = row.text(l.levels.map((v) => Math.round(v * 100)).join(' / '), { x: leaf.x, y: y - 50, size: 28, weight: 500, font: 'mono', color: C.navy });
        return { row, bar, numbers };
      });
      const flowLabels = [0, 1, 3].map((i) => big.text(flowText(leaves[i].reach), { x: leaf.x - 14, y: leaf.rows[i] - 30, align: 'right', size: 28, weight: 500, font: 'mono', color: C.navy }));
      const levelNames = L.level_names.map((name, i) => sliding.text(name, { x: bars[THICK].bar.center(i, leaves[THICK].levels, leaf.w, leaf.x), y: flowY + 52, align: 'center', size: 28, color: C.ink }));

      const tMix = s27.cue('leaf');
      leafWord.out(tMix, 0.5);
      leafName.out(tMix, 0.5);
      bars[THICK].row.in(tMix, 0.5);
      flowLabels.forEach((label) => label.in(tMix + 0.4, 0.5));
      bars[0].row.in(tMix + 0.4, 0.5);
      bars[1].row.in(tMix + 0.8, 0.5);
      bars[3].row.in(tMix + 1.2, 0.5);
      s27.lastLand = tMix + 1.7;
      ['rare', 'possible', 'likely'].forEach((word, i) => levelNames[i].in(s27.beat(word, 0.5, 0.05), 0.5));

      // The tree clears, the leaves slide left, and the flows run on into one bar.
      const tClear = s27.beat('Blended', 0.5, 0.3);
      const clearing = [title, ...outline.lines, ...outline.midBoxes, outline.rootBox, rootText, ...midTexts, ...whereYesNo, ...water.branches, ...water.twigs, onFlow, ...flowLabels, ...levelNames];
      clearing.forEach((item) => item.out(tClear, 0.5));
      outline.tracks.forEach((item) => item.out(tClear, 0.5));
      const shift = 40 - leaf.x;
      const tSlide = s27.beat(tClear + 0.3, 0.7, 0);
      sliding.to({ x: shift }, tSlide, 0.7);
      const tJoin = s27.beat(tSlide + 0.7, 0.5, 0);
      let stack = BLEND.cy - FLOW_WIDTH / 2;
      const joinStart = leaf.x + leaf.w + shift + 8;
      leaves.forEach((l, i) => {
        const w = l.reach * FLOW_WIDTH;
        g.path(curve(joinStart, leaf.rows[i], BLEND.x, stack + w / 2), { stroke: C.navy, width: w }).drawIn(tJoin, 0.5);
        stack += w;
      });
      const newFlowLabels = leaves.map((l, i) => g.text(flowText(l.reach), { x: joinStart + 6, y: leaf.rows[i] + (i === THICK ? 0 : i === 3 ? 28 : -26), size: 28, weight: i === THICK ? 700 : 500, font: 'mono', color: i === THICK ? C.inverse : C.navy }));
      newFlowLabels.forEach((label) => label.in(tJoin, 0.5));

    }

    // ---- 2.7 into 2.8: the blended bar. Its own block, so it stays on screen through the section change.
    function blendedBar(g, s27, s28) {
      const colors = kit.LEVEL_COLORS();
      const inks = kit.LEVEL_INK();
      const { bar } = EQ;
      const made = [];
      let at = 0;
      let barAt = 0;
      L.levels.forEach((share, i) => {
        const w = share * BLEND.w;
        const left = BLEND.x + at;
        const endW = share * bar.w;
        const seg = g.box({ x: left, y: BLEND.cy - BLEND.h / 2, w, h: BLEND.h, fill: colors[i] });
        const number = g.text(pct(share), { x: left + w / 2, y: BLEND.cy - BLEND.h / 2 - 50, align: 'center', size: 56, weight: 700, font: 'mono', color: C.navy });
        const name = g.text(L.level_names[i], { x: left + w / 2, y: BLEND.cy + BLEND.h / 2 + 42, align: 'center', size: 34, weight: 600, color: C.ink });
        made.push({ seg, number, name, w, endX: bar.x + barAt, endW, endCx: bar.x + barAt + endW / 2 });
        at += w;
        barAt += endW;
      });
      ['12', '60', '28'].forEach((word, i) => {
        const when = s27.beat(word, 0.5, 0.05);
        made[i].seg.add('width', when, 0.5, made[i].w, 0);
        made[i].number.in(when, 0.5);
        made[i].name.in(when, 0.5);
      });
      const tRise = Math.max(s28.t1 - 0.2, s28.cue('stands'));
      s28.lastLand = tRise + 0.8;
      made.forEach(({ seg, number, name, endX, endW, endCx }, i) => {
        seg.to({ x: endX, y: bar.y, width: endW, height: bar.h }, tRise, 0.8);
        number.to({ x: endCx, y: bar.y + bar.h / 2, scale: 40 / 56, color: inks[i] }, tRise, 0.8);
        name.out(tRise, 0.5);
      });
    }

    // ---- 2.8 to 2.10: the equations.
    function equationScenes(g, s28, s29, s210) {
      const colors = kit.LEVEL_COLORS();
      const inks = kit.LEVEL_INK();
      const shares = L.levels;
      const { bar } = EQ;
      const aTerm = adv(EQ.termSize);
      const aResult = adv(EQ.resultSize, 700);

      const segs = [];
      let barAt = 0;
      const aAnchor = adv(32);
      shares.forEach((share) => {
        const endW = share * bar.w;
        segs.push({ endCx: bar.x + barAt + endW / 2 });
        barAt += endW;
      });

      // rare = 0.02, possible = 0.10, likely = 0.30, under each segment.
      const anchorY = 244;
      const anchorRow = anchors.map((value, i) => {
        const word = `${L.level_names[i]} = `;
        const num = value.toFixed(2);
        const wordW = kit.textWidth(word, 34, 600);
        const total = wordW + num.length * aAnchor;
        const left = Math.max(60, segs[i].endCx - total / 2);
        const group = g.group({});
        group.text(word, { x: left, y: anchorY, size: 34, weight: 600, color: C.ink });
        group.text(num, { x: left + wordW, y: anchorY, size: 32, weight: 700, font: 'mono', color: C.navy });
        return { group, cx: segs[i].endCx };
      });
      const tAnchors = s28.beat('fixed', 0.5, 0.05);
      anchorRow.forEach((row, i) => row.group.in(tAnchors + i * 0.3, 0.5));
      s28.lastLand = tAnchors + 0.6 + 0.5;

      // One term per row, each joined to its bar segment.
      const chipLeft = EQ.rowsX - 16;
      const termChars = 12;
      const chipRight = EQ.rowsX + termChars * aTerm + 16;
      const links = [
        `M${anchorRow[0].cx} ${anchorY + 26} C${anchorRow[0].cx} ${anchorY + 60},${chipLeft + 90} ${anchorY + 30},${chipLeft + 90} ${EQ.rowY[0] - 42}`,
        `M${anchorRow[1].cx} ${anchorY + 26} C${anchorRow[1].cx} ${anchorY + 52},${chipRight + 44} ${anchorY + 26},${chipRight + 44} ${anchorY + 76} L${chipRight + 44} ${EQ.rowY[1] - 26} Q${chipRight + 44} ${EQ.rowY[1]},${chipRight} ${EQ.rowY[1]}`,
        `M${anchorRow[2].cx} ${anchorY + 26} L${anchorRow[2].cx} ${EQ.rowY[2] - 30} Q${anchorRow[2].cx} ${EQ.rowY[2]},${anchorRow[2].cx - 30} ${EQ.rowY[2]} L${chipRight} ${EQ.rowY[2]}`,
      ];
      const stems = anchorRow.map((row, i) => g.path(`M${row.cx} ${bar.y + bar.h} V${anchorY - 24}`, { stroke: colors[i], width: 8 }));
      const lhs = g.text('L =', { x: 80, y: EQ.rowY[0], size: EQ.termSize, weight: 700, font: 'mono', color: C.navy });
      lhs.in(s28.beat('Multiply', 0.5, 0.05), 0.5);
      s28.lastLand -= 0.5;
      const pieces = shares.map((share, i) => {
        const y = EQ.rowY[i];
        const link = g.path(links[i], { stroke: colors[i], width: 8 });
        const chip = g.box({ x: chipLeft, y: y - 42, w: chipRight - chipLeft, h: 84, fill: colors[i], r: 10 });
        const term = g.text(`${share.toFixed(3)} × ${anchors[i].toFixed(2)}`, { x: EQ.rowsX, y, size: EQ.termSize, weight: 500, font: 'mono', color: inks[i] });
        const plus = i === 0 ? null : g.text('+', { x: EQ.rowsX - 72, y, size: EQ.termSize, weight: 500, font: 'mono', color: C.navy });
        return { link, chip, term, plus };
      });
      ['Multiply', 'share', 'its number'].forEach((phrase, i) => {
        const when = s28.beat(phrase, 0.5, 0.15);
        const piece = pieces[i];
        piece.link.drawIn(when, 0.5);
        stems[i].drawIn(when, 0.5);
        piece.chip.in(when, 0.5);
        piece.term.in(when, 0.5);
        if (piece.plus) piece.plus.in(when, 0.5);
      });

      const equals = g.text('=', { x: EQ.rowsX - 72, y: EQ.resultY, size: EQ.termSize, weight: 500, font: 'mono', color: C.navy });
      const result = g.text(lValue, { x: EQ.rowsX, y: EQ.resultY, size: EQ.resultSize, weight: 700, font: 'mono', color: C.navy });
      const resultWord = g.text('likelihood', { x: EQ.rowsX + lValue.length * aResult + 36, y: EQ.resultY, size: 44, weight: 600, color: C.heading });
      const tResult = s28.beat("That's", 0.5, 0.3);
      shared.tResult = tResult;
      equals.in(tResult, 0.5);
      result.in(tResult, 0.5);
      resultWord.in(tResult, 0.5);

      // 2.9: severity, then the product. The scene is short, so the sum clears in one move.
      const clear = s29.t0;
      const leaving = [...anchorRow.map((r) => r.group), ...stems, lhs, equals, resultWord, ...pieces.flatMap((p) => [p.link, p.chip, p.term, ...(p.plus ? [p.plus] : [])])];
      leaving.forEach((item) => item.out(clear, 0.5));
      const size72 = 72;
      const a72 = adv(size72, 700);
      const lhsTop = g.text('L =', { x: 60, y: 300, size: size72, weight: 700, font: 'mono', color: C.navy });
      const tUp = clear + 0.35;
      result.to({ x: 60 + 4 * a72, y: 300, scale: size72 / EQ.resultSize }, tUp, 0.6);
      lhsTop.in(tUp + 0.2, 0.4);
      const likelyWord = g.text('likelihood', { x: 60, y: 372, size: 34, color: C.inkMuted });
      likelyWord.in(tUp + 0.2, 0.4);
      s29.lastLand = tUp + 0.6;

      const sGroup = g.group({});
      sGroup.text(`S = ${sValue}`, { x: 700, y: 300, size: size72, weight: 700, font: 'mono', color: C.navy });
      sGroup.text('severity (how bad)', { x: 700, y: 372, size: 34, color: C.inkMuted });
      const tS = s29.beat('same way', 0.5, 0.1);
      shared.tS = tS;
      sGroup.in(tS, 0.5);

      const productSize = 76;
      const aProduct = adv(productSize, 700);
      const factorRow = g.text(`${lValue} × ${sValue}`, { x: 60, y: 560, size: productSize, weight: 500, font: 'mono', color: C.navy });
      const equals2 = g.text('=', { x: 60 + 13 * aProduct, y: 560, size: productSize, weight: 500, font: 'mono', color: C.navy });
      const productX = 60 + 15 * aProduct;
      const product = g.text(products[0], { x: productX, y: 560, size: productSize, weight: 700, font: 'mono', color: C.navy });
      const riskWord = g.text("This hazard's risk", { x: 60, y: 650, size: 40, weight: 600, color: C.heading });
      const tFactors = s29.beat('Multiply', 0.5, 0.4);
      factorRow.in(tFactors, 0.5);
      const tProduct = s29.beat('risk', 0.5, 0.3);
      shared.tProduct = tProduct;
      equals2.in(tProduct, 0.5);
      product.in(tProduct, 0.5);
      riskWord.in(tProduct, 0.5);

      // 2.10: the sum across hazards, on the meter. The scene is short, so the meter fills once.
      const sumClear = s210.t0;
      [lhsTop, likelyWord, result, sGroup, factorRow, equals2, riskWord].forEach((item) => item.out(sumClear, 0.5));
      const sumSize = 52;
      const aSum = adv(sumSize);
      const sumY = 220;
      const risk = g.text('Risk =', { x: 60, y: sumY, size: sumSize, weight: 700, font: 'mono', color: C.navy });
      risk.in(sumClear + 0.3, 0.4);
      const termX = (i) => 60 + (7 + i * 9) * aSum;
      product.to({ x: termX(0), y: sumY, scale: sumSize / productSize }, sumClear + 0.25, 0.6);
      const hazardWords = ['traffic', 'crowd', 'medical'];
      const wordsUnder = hazardWords.map((word, i) => g.text(word, { x: termX(i) + 3 * aSum, y: sumY + 62, align: 'center', size: 32, color: C.inkMuted }));
      wordsUnder[0].in(sumClear + 0.7, 0.4);
      const rest = [1, 2].map((i) => ({
        plus: g.text('+', { x: termX(i) - 2 * aSum, y: sumY, size: sumSize, weight: 500, font: 'mono', color: C.navy }),
        value: g.text(products[i], { x: termX(i), y: sumY, size: sumSize, weight: 700, font: 'mono', color: C.navy }),
        word: wordsUnder[i],
      }));
      s210.lastLand = sumClear + 0.85;
      const tTerms = s210.beat('three hazards', 0.5, 0.05);
      shared.tTerms = tTerms;
      rest.forEach((r, i) => {
        const when = tTerms + i * 0.4;
        r.plus.in(when, 0.5);
        r.value.in(when, 0.5);
        r.word.in(when, 0.5);
      });
      s210.lastLand = tTerms + 0.9;
      const total = g.text(`= ${riskValue}`, { x: 60 + 5 * aSum, y: 410, size: 96, weight: 700, font: 'mono', color: C.navy });
      const tTotal = s210.beat('total risk', 0.6, 0.05);
      total.in(tTotal, 0.5);
      shared.tTotal = tTotal;
      shared.tLine = s210.beat('approval line', 0.5, 0.2);
    }

    // ---- 2.10 into 2.11: the meter. Its own block, so it stays on screen through the section change.
    function meterBlock(g) {
      g.box({ x: METER.x, y: METER.y, w: METER.w, h: METER.h, fill: C.muted, stroke: C.hairline, sw: 2, r: 8 });
      const fill = g.box({ x: METER.x, y: METER.y, w: meterX(kase.risk) - METER.x, h: METER.h, fill: C.navy, r: 8 });
      fill.add('width', shared.tTotal, 0.6, meterX(kase.risk) - METER.x, 0);
      const line = g.path(`M${meterX(approval)} ${METER.y - 34} V${METER.y + METER.h + 34}`, { stroke: C.amber, width: 7 });
      line.drawIn(shared.tLine, 0.5);
      const label = g.text(`Approval line ${approval.toFixed(3)}`, { x: meterX(approval), y: METER.y + METER.h + 70, align: 'center', size: 36, weight: 700, color: C.heading });
      label.in(shared.tLine, 0.5);
      for (const item of [fill, line, label]) item.dim(shared.tNo, 0.22, 0.5);
    }

    // ---- The scoreboard, from 2.3 on. It starts blank and fills as each number is reached.
    function scoreboard(g, ...scenes) {
      const by = Object.fromEntries(scenes.map((s) => [s.id, s]));
      const panel = g.group({});
      panel.box({ x: BOARD.x, y: BOARD.y, w: BOARD.w, h: BOARD.h, fill: C.muted, stroke: C.hairline, sw: 2, r: 12 });
      const a = adv(28);
      const gap = a * 0.55;
      const name = (text, y) => panel.text(text, { x: BOARD.left, y, size: 30, weight: 700, color: C.heading });
      const mono = (text, x, y, weight = 500) => panel.text(text, { x, y, size: 28, weight, font: 'mono', color: C.navy });
      const blank = (cx, chars, y) => panel.path(`M${cx - (chars * a) / 2} ${y + 22} h${chars * a}`, { stroke: C.strong, width: 2 });
      const value = (text, cx, y, weight = 700) => g.text(text, { x: cx, y, align: 'center', size: 28, weight, font: 'mono', color: C.navy });

      // Traffic: L ___ × S ___ = ___
      name('traffic', 146);
      const rowY = 196;
      let x = BOARD.left;
      mono('L', x, rowY);
      x += a + gap;
      const lCx = x + (lValue.length * a) / 2;
      blank(lCx, lValue.length, rowY);
      x += lValue.length * a + gap;
      mono('×', x, rowY);
      x += a + gap;
      mono('S', x, rowY);
      x += a + gap;
      const sCx = x + (sValue.length * a) / 2;
      blank(sCx, sValue.length, rowY);
      x += sValue.length * a + gap;
      mono('=', x, rowY);
      x += a + gap;
      const pCx = x + (products[0].length * a) / 2;
      blank(pCx, products[0].length, rowY);

      // Crowd and medical: (same steps) = ___
      const sameRows = [{ word: 'crowd', y: 256, value: products[1] }, { word: 'medical', y: 306, value: products[2] }];
      const sameCx = BOARD.right - (products[1].length * a) / 2;
      for (const row of sameRows) {
        name(row.word, row.y);
        panel.text('(same steps)', { x: BOARD.left + 130, y: row.y, size: 28, color: C.inkMuted });
        mono('=', sameCx - (products[1].length * a) / 2 - gap - a, row.y);
        blank(sameCx, products[1].length, row.y);
      }
      panel.path(`M${BOARD.left} 346 H${BOARD.right}`, { stroke: C.hairline, width: 2 });
      name('total risk', 386);
      const totalCx = BOARD.right - (riskValue.length * a) / 2;
      blank(totalCx, riskValue.length, 386);
      panel.text('approval line', { x: BOARD.left, y: 434, size: 30, color: C.ink });
      panel.text(approval.toFixed(3), { x: BOARD.right, y: 434, align: 'right', size: 28, weight: 500, font: 'mono', color: C.navy });
      const rounded = panel.text('Figures rounded.', { x: BOARD.left, y: 488, size: 28, color: C.inkMuted });

      const s23 = by['2.3'];
      panel.in(s23.cue('traffic conflict'), 0.6);
      rounded.in(by['2.6'].t1, 0.5);

      // Each slot fills in order. Its highlight marks the newest number until the next one arrives.
      const fills = [
        { text: lValue, cx: lCx, y: rowY, t: shared.tResult + 0.5 },
        { text: sValue, cx: sCx, y: rowY, t: shared.tS + 0.25 },
        { text: products[0], cx: pCx, y: rowY, t: shared.tProduct + 0.1 },
        { text: sameRows[0].value, cx: sameCx, y: sameRows[0].y, t: shared.tTerms },
        { text: sameRows[1].value, cx: sameCx, y: sameRows[1].y, t: shared.tTerms + 0.4 },
        { text: riskValue, cx: totalCx, y: 386, t: shared.tTotal + 0.2 },
      ];
      fills.forEach((fill, i) => {
        const w = fill.text.length * a + 14;
        const mark = g.box({ x: fill.cx - w / 2, y: fill.y - 20, w, h: 40, fill: C.sand, r: 6 });
        mark.in(fill.t, 0.5);
        const next = fills[i + 1];
        mark.out(next ? next.t : by['2.11'].cue('No'), 0.5);
        value(fill.text, fill.cx, fill.y).in(fill.t, 0.5);
      });
    }

    // ---- 2.11: rules outrank arithmetic.
    function decisionScene(g, s) {
      const asked = g.text('Approved?', { x: 60, y: 170, size: 80, weight: 800, font: 'display', color: C.heading });
      const no = g.text('No.', { x: 60 + kit.textWidth('Approved?', 80, 800, 'display') + 36, y: 170, size: 80, weight: 800, font: 'display', color: C.danger });
      const rule = g.group({});
      rule.box({ x: 60, y: 250, w: 790, h: 210, fill: C.navy, r: 14 });
      rule.text(kase.decision.text.split(',')[0], { x: 100, y: 355, w: 710, size: 48, weight: 700, font: 'display', color: C.inverse, lh: 1.14 });
      const letterNote = g.text(`Police letter: ${police.verdict}`, { x: 60, y: 498, size: 34, weight: 600, color: C.danger });
      const link = kit.arrow(g, 860, 355, 965, 355, { width: 7, head: 20 });
      const deskGroup = g.group({});
      const desk = deskGroup.box({ x: 975, y: 250, w: 325, h: 210, fill: C.tint, r: 14 });
      const person = kit.person(deskGroup, 1137, 320, 90, C.navy);
      const deskText = deskGroup.text('Officer', { x: 1137, y: 412, align: 'center', size: 44, weight: 700, font: 'display', color: C.navy });
      const caption = kit.caption(g, officerLabel, { x: 680, y: 1000, size: 30 });

      asked.in(s.beat('approved', 0.5, 0.1), 0.5);
      const tNo = s.beat('No', 0.5, 0.1);
      no.in(tNo, 0.5);
      shared.tNo = tNo;
      rule.in(s.beat('Rules', 0.6, 0.2), 0.6);
      letterNote.in(s.beat('wrong-date', 0.5, 0.2), 0.5);
      const tSend = s.beat('sends', 0.6, 0.15);
      link.draw(tSend, 0.6);
      deskGroup.in(tSend, 0.5);
      const tOfficer = s.beat('officer', 0.5, 0.05);
      desk.to({ bg: C.navy }, tOfficer, 0.5);
      deskText.to({ color: C.inverse }, tOfficer, 0.5);
      person.head.to({ bg: C.inverse }, tOfficer, 0.5);
      person.body.to({ fill: C.inverse }, tOfficer, 0.5);
      caption.in(tOfficer, 0.5);
    }

    // ---- 2.12: the real move on the leaf.
    function learningScene(g, s) {
      const change = kase.correction.changes.find((c) => c.tree_id === L.tree_id && c.leaf[q1.id] === false && c.leaf[q2.id] === true);
      if (!change) throw new Error('No correction for the leaf in this case');
      const { before, after } = change;
      const barX = 60;
      const barW = 1240;
      const barY = 500;
      const barH = 130;
      const label = kit.pill(g, officerLabel, { x: 60, y: 130, size: 30 });
      const disagree = g.text('Below the line, but the officer disagrees.', { x: 60, y: 210, size: 40, weight: 600, color: C.heading });
      const stamp = kit.stamp(g, 'Risky', { x: 60, y: 260, w: 280, h: 96, size: 54 });
      g.text('Leaf: no escort, good plan', { x: 60, y: 450, size: 38, weight: 700, color: C.heading });
      const bar = kit.levelBar(g, { x: barX, y: barY, w: barW, h: barH, levels: before });
      const inks = kit.LEVEL_INK();
      const center = (levels, i) => {
        let a = 0;
        for (let j = 0; j < i; j++) a += levels[j];
        return barX + (a + levels[i] / 2) * barW;
      };
      const labels = before.map((v, i) => g.text(pct(v), { x: center(before, i), y: barY + barH / 2, align: 'center', size: i === 2 ? 80 : 44, weight: 700, font: 'mono', color: inks[i] }));
      const names = L.level_names.map((name, i) => g.text(name, { x: center(before, i), y: barY + barH + 42, align: 'center', size: 34, weight: 600, color: C.ink }));
      const oldEdge = barX + (before[0] + before[1]) * barW;
      const newEdge = barX + (after[0] + after[1]) * barW;
      const arrow = kit.arrow(g, oldEdge, barY - 26, newEdge, barY - 26, { width: 7, head: 20 });
      const caption = g.text('Smaller shifts in the other leaves.', { x: 60, y: 760, size: 34, color: C.inkMuted });
      const was = g.text(`was ${pct(before[2])}`, { x: oldEdge + 18, y: barY - 26, size: 30, weight: 500, font: 'mono', color: C.navy });

      const tRisky = s.beat('risky', 0.6, 0.1);
      label.in(s.t1, 0.5);
      disagree.in(tRisky, 0.6);
      stamp.in(tRisky, 0.6, { scale: 1.06 });
      const tMove = s.beat('likely', 0.9, 0.3);
      bar.morph(after, tMove, 0.9);
      arrow.draw(tMove, 0.9);
      was.in(tMove, 0.5);
      labels.forEach((item, i) => {
        item.to({ x: center(after, i) }, tMove, 0.9);
        item.count(before[i] * 100, after[i] * 100, tMove, 0.9, (v) => `${Math.round(v)}%`);
      });
      names.forEach((item, i) => item.to({ x: center(after, i) }, tMove, 0.9));
      caption.in(s.beat("That's", 0.5, 0.4), 0.5);
    }

    // ---- 2.13: does training help?
    function sealedScene(g, s) {
      const arm = (name) => data.final.arms.find((a) => a.name.startsWith(name));
      const rows = [
        { label: 'Trained on labelled cases', value: arm('Trained on labelled').right_level, cue: 'trained trees', spoken: '89' },
        { label: 'Untrained first guess', value: arm('First guess').right_level, cue: 'Untrained', spoken: '68' },
        { label: 'Trained on shuffled answers (control)', value: arm('Shuffled').right_level, cue: 'shuffled', spoken: '55' },
      ];
      const barX = 100;
      const barW = 1240;
      const ys = [300, 490, 680];
      const three = g.text('Three tests', { x: 100, y: 150, size: 56, weight: 700, font: 'display', color: C.heading });
      const firstTest = g.text('Test 1: does training help?', { x: 100, y: 150, size: 56, weight: 700, font: 'display', color: C.heading });
      const seal = g.group({});
      seal.box({ x: 1500, y: 150, w: 320, h: 320, stroke: C.navy, sw: 6, r: 160, fill: C.surface });
      seal.text('Fixed in advance.<br>Run once.', { x: 1660, y: 310, w: 290, align: 'center', size: 34, weight: 700, color: C.navy, lh: 1.25, html: true });
      const caption = kit.caption(g, '100 sealed cases. Scored: top-share level, not the final decision.', { y: 960, size: 34 });
      const made = rows.map((row, i) => {
        const y = ys[i];
        const text = g.text(row.label, { x: barX, y, size: 36, weight: 600, color: C.heading });
        const fill = g.box({ x: barX, y: y + 30, w: barW * row.value, h: 70, fill: i === 0 ? C.navy : i === 1 ? C.sky : C.skyPale, r: 8 });
        const number = g.text(pct(row.value), { x: barX + barW * row.value + 24, y: y + 65, size: 64, weight: 700, font: 'mono', color: C.navy });
        return { ...row, text, fill, number, width: barW * row.value };
      });
      const tFirst = s.beat('First', 0.5);
      three.out(tFirst, 0.5);
      firstTest.in(tFirst, 0.5);
      const tSeal = s.beat('sealed test', 0.6, 0.5);
      seal.in(tSeal, 0.6);
      caption.in(tSeal, 0.6);
      for (const row of made) {
        const t = s.beat(row.cue, 0.8, 0.6);
        row.text.in(t, 0.5);
        row.fill.add('width', t, 0.8, row.width, 0);
        row.number.in(s.beat(row.spoken, 0.5, 0), 0.5);
      }
    }

    // ---- 2.14: which reviews should teach?
    function reviewsScene(g, s) {
      const { corrections, every } = data.story;
      const x0 = 240;
      const x1 = 1300;
      const y0 = 850;
      const y1 = 240;
      const low = 0.4;
      const high = 0.9;
      const maxReviews = corrections[corrections.length - 1].reviews;
      const px = (r) => x0 + (r / maxReviews) * (x1 - x0);
      const py = (v) => y0 - ((v - low) / (high - low)) * (y0 - y1);
      const line = (rows) => `M${rows.map((r) => `${px(r.reviews).toFixed(1)} ${py(r.loss).toFixed(1)}`).join(' L')}`;
      g.text('Test 2: which reviews should teach?', { x: 100, y: 130, size: 52, weight: 700, font: 'display', color: C.heading });
      g.text('Loss, lower is better', { x: x0, y: 196, size: 34, weight: 600, color: C.inkMuted });
      for (const tick of [0.5, 0.7, 0.9]) {
        g.path(`M${x0} ${py(tick)} H${x1}`, { stroke: C.grid, width: 2 });
        g.text(tick.toFixed(1), { x: x0 - 20, y: py(tick), align: 'right', size: 28, font: 'mono', color: C.inkMuted });
      }
      g.path(`M${x0} ${y0} H${x1}`, { stroke: C.strong, width: 3 });
      g.text('0', { x: x0, y: y0 + 36, align: 'center', size: 28, font: 'mono', color: C.inkMuted });
      g.text(String(maxReviews), { x: x1, y: y0 + 36, align: 'center', size: 28, font: 'mono', color: C.inkMuted });
      g.text('Reviews', { x: (x0 + x1) / 2, y: y0 + 36, align: 'center', size: 30, color: C.inkMuted });
      g.text(corrections[0].loss.toFixed(2), { x: x0 + 12, y: py(corrections[0].loss) - 36, size: 40, weight: 700, font: 'mono', color: C.navy });
      kit.caption(g, 'Side experiment: 100 reviews, officer scripted from labels at 90% accuracy.', { y: 980, size: 32 });

      const worse = g.path(line(corrections), { stroke: C.amber, width: 8 });
      const better = g.path(line(every), { stroke: C.navy, width: 8 });
      const endA = corrections[corrections.length - 1];
      const endB = every[every.length - 1];
      const labelA = g.group({});
      labelA.text('Disagreements only', { x: x1 + 26, y: py(endA.loss) - 28, size: 38, weight: 700, color: C.warning });
      labelA.text(endA.loss.toFixed(2), { x: x1 + 26, y: py(endA.loss) + 28, size: 44, weight: 700, font: 'mono', color: C.warning });
      const labelB = g.group({});
      labelB.text('Every review', { x: x1 + 26, y: py(endB.loss) - 28, size: 38, weight: 700, color: C.navy });
      labelB.text(endB.loss.toFixed(2), { x: x1 + 26, y: py(endB.loss) + 28, size: 44, weight: 700, font: 'mono', color: C.navy });
      const tag = kit.pill(g, 'what we use', { x: x1 + 26 + 150, y: py(endB.loss) + 28, size: 30 });

      const tA = s.beat('disagreements', 0.9);
      worse.drawIn(tA, 0.9);
      labelA.in(s.beat('worse', 0.5, 0.2), 0.5);
      const tB = s.beat('agreements', 0.9, 0.4);
      better.drawIn(tB, 0.9);
      const tLabel = s.beat('much better', 0.5, 0.1);
      labelB.in(tLabel, 0.5);
      tag.in(tLabel, 0.5);
    }

    // ---- 2.15: a pushy letter, and the honest limit.
    function toneScene(g, s) {
      const toneNames = { insistent: 'Insistent', mayor: 'Mentions the mayor', persuasive: 'Persuasive' };
      const tones = Object.keys(data.tone.tones);
      const summary = data.learning.tone;
      const shifted = Object.values(summary.evidence_flips).reduce((a, b) => a + b, 0);
      const noiseCompared = data.tone.noise_floor.compared;
      const ys = [230, 430, 630];
      g.text('Test 3: does a pushy letter help?', { x: 100, y: 130, size: 52, weight: 700, font: 'display', color: C.heading });
      const decisionX = 1180;
      const letters = tones.map((tone, i) => {
        const y = ys[i];
        const line = g.path(curve(660, y + 70, decisionX, 400 + i * 40), { stroke: C.navy, width: 6 });
        const card = g.group({});
        card.box({ x: 100, y, w: 560, h: 140, fill: C.surface, stroke: C.strong, sw: 3, r: 10 });
        card.text('Cover letter', { x: 136, y: y + 42, size: 28, color: C.inkMuted });
        card.text(toneNames[tone] || tone, { x: 136, y: y + 92, size: 40, weight: 700, font: 'display', color: C.heading });
        return { line, card };
      });
      const decision = g.group({});
      decision.box({ x: decisionX, y: 330, w: 640, h: 220, fill: C.navy, r: 14 });
      decision.text('One decision', { x: decisionX + 320, y: 400, align: 'center', size: 56, weight: 700, font: 'display', color: C.inverse });
      decision.text(`${summary.decision_flips} of ${summary.compared} changed`, { x: decisionX + 320, y: 480, align: 'center', size: 40, weight: 700, font: 'mono', color: C.inverse });
      const shiftNote = kit.caption(g, `Evidence readings shifted in ${shifted} of ${summary.compared}, close to the ${summary.noise_evidence_flips} of ${noiseCompared} from re-reading the same letters.`, { y: 880, size: 34 });
      const synthetic = kit.caption(g, CAPTION_SYNTHETIC, { y: 980, size: 40, color: C.heading });

      const tLetters = s.beat('cover letter', 0.5, 0.1);
      letters.forEach((letter, i) => letter.card.in(tLetters + i * 0.35, 0.5));
      s.lastLand = tLetters + 1.2;
      const tLines = s.beat('60 comparisons', 0.7, 0.2);
      letters.forEach((letter) => letter.line.drawIn(tLines, 0.7));
      decision.in(s.beat('no decision changed', 0.6, 0.1), 0.6);
      shiftNote.in(s.beat('changed', 0.6, 0.3), 0.6);
      synthetic.in(s.beat('data', 0.6, 0.4), 0.6);
    }

    const boardScenes = ['2.3', '2.4', '2.5', '2.6', '2.7', '2.8', '2.9', '2.10', '2.11', '2.12'];
    return [
      { scenes: ['2.1'], build: formScene },
      { scenes: ['2.2'], build: hazardScene },
      { scenes: ['2.3', '2.4', '2.5', '2.6', '2.7'], build: treeScenes },
      { scenes: ['2.7', '2.8'], build: blendedBar },
      { scenes: ['2.8', '2.9', '2.10'], build: equationScenes },
      { scenes: ['2.11'], build: decisionScene },
      { scenes: ['2.10', '2.11'], build: meterBlock },
      { scenes: ['2.12'], build: learningScene },
      { scenes: boardScenes, build: scoreboard },
      { scenes: ['2.13'], build: sealedScene },
      { scenes: ['2.14'], build: reviewsScene },
      { scenes: ['2.15'], build: toneScene },
    ];
  };
})();
