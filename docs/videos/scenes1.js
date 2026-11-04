// Video 1: what it is and why it matters. One diagram of four question boxes runs through the video.
// Scene code places visuals by cue phrases. It never contains narration or times.
(function () {
  'use strict';

  const QUESTIONS = ['What supports it?', 'What could go wrong?', 'What do the rules say?', 'Does it need a person?'];
  const X0 = 100;
  const BOX_W = 400;
  const BOX_GAP = 40;
  const boxX = (i) => X0 + i * (BOX_W + BOX_GAP);
  const boxCx = (i) => boxX(i) + BOX_W / 2;
  const COMPACT = { y: 88, h: 104, textScale: 0.68, textDy: 52 };
  const BIG = { y: 360, h: 200, textScale: 1, textDy: 100 };
  const TALL = { y: 360, h: 300, textScale: 1, textDy: 92 };
  const SEALED = { x: 700, y: 340, w: 520, h: 400 };
  const CAPTION_SAME = 'Same pattern. Not built or tested here.';
  const CAPTION_SYNTHETIC = 'Synthetic data. Answer key written by the author.';

  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const longDate = (iso) => {
    const [y, m, d] = iso.split('-').map(Number);
    return `${MONTHS[m - 1]} ${d}, ${y}`;
  };

  function logLines(g, { x = X0, y0, step = 54 }) {
    const { C, data } = PE;
    const events = ['evidence.judged', 'risk.computed', 'decision.made', 'correction.made'].map((type) => {
      const found = data.events.find((e) => e.type === type);
      if (!found) throw new Error(`Case has no ${type} event`);
      return found;
    });
    return events.map((event, i) => {
      const row = g.group({});
      row.text(event.sim_time.slice(11, 16), { x, y: y0 + i * step, size: 28, font: 'mono', weight: 500, color: C.inkMuted });
      row.text(event.summary, { x: x + 140, y: y0 + i * step, size: 30, color: C.ink });
      return row;
    });
  }

  PE.videos.video1 = () => {
    const { C, kit, data } = PE;
    const kase = data.case;
    const officerLabel = kase.officer.label;

    // ---- 1.1: one sealed box. It stays under the diagram until the box opens in 1.2.
    function sealedBox(g, a, b) {
      const doc = g.group({});
      doc.box({ x: 110, y: 370, w: 320, h: 340, fill: C.surface, stroke: C.strong, sw: 3, r: 10 });
      const docLabel = doc.text('Street race request', { x: 270, y: 540, w: 260, align: 'center', size: 40, weight: 700, font: 'display', color: C.heading });
      const inArrow = kit.arrow(g, 440, 540, 680, 540);
      const sealed = g.box({ x: SEALED.x, y: SEALED.y, w: SEALED.w, h: SEALED.h, fill: C.navy, r: 16 });
      const sealedText = g.text('One AI model', { x: 960, y: 540, align: 'center', size: 52, weight: 700, font: 'display', color: C.inverse });
      const outArrow = kit.arrow(g, 1240, 540, 1440, 540);
      const answer = g.group({});
      answer.box({ x: 1460, y: 450, w: 360, h: 180, fill: C.tint, r: 12 });
      answer.text('Approved?', { x: 1640, y: 540, align: 'center', size: 52, weight: 700, font: 'display', color: C.heading });
      const mark = g.text('?', { x: 960, y: 240, align: 'center', size: 170, weight: 800, font: 'display', color: C.amber });
      const empty = g.text('Nothing to check or fix', { x: 960, y: 810, align: 'center', size: 40, weight: 600, color: C.ink });

      docLabel.in(a.beat('request', 0.6), 0.6);
      const t = a.beat('AI model', 0.7);
      inArrow.draw(t, 0.7);
      sealed.in(t, 0.7);
      sealedText.in(t, 0.7);
      const t2 = a.beat('yes or no', 0.7);
      outArrow.draw(t2, 0.7);
      answer.in(t2, 0.7);
      mark.in(a.beat('wrong', 0.6), 0.6, { dy: 16 });
      empty.in(a.beat('nothing to check', 0.5), 0.5);

      // Clearing the stage is one move. The box itself is handed to the diagram at "splits".
      for (const item of [doc, answer, mark, empty, inArrow.line, inArrow.tip, outArrow.line, outArrow.tip]) item.out(b.t0, 0.6);
      const open = b.cue('splits');
      sealed.out(open, 0.4);
      sealedText.out(Math.max(b.t1, open - 0.4), 0.4);
    }

    // ---- The diagram: four question boxes, compact at the top or large in the middle.
    function diagram(g, ...scenes) {
      const by = Object.fromEntries(scenes.map((s) => [s.id, s]));
      const open = by['1.2'];
      const boxes = QUESTIONS.map((_, i) => g.box({ x: SEALED.x + i * (SEALED.w / 4), y: SEALED.y, w: SEALED.w / 4, h: SEALED.h, fill: C.navy, r: 12, opacity: 0 }));
      const texts = QUESTIONS.map((q, i) => g.text(q, { x: boxCx(i), y: BIG.y + BIG.textDy, w: 340, align: 'center', size: 44, weight: 700, font: 'display', color: C.inverse, lh: 1.14, opacity: 0 }));

      const light = (i, t, dur = 0.6) => {
        boxes[i].to({ bg: C.navy }, t, dur);
        texts[i].to({ color: C.inverse }, t, dur);
      };
      const quiet = (i, t, dur = 0.6) => {
        boxes[i].to({ bg: C.tint }, t, dur);
        texts[i].to({ color: C.navy }, t, dur);
      };
      const moveAll = (place, t, dur = 0.9) => {
        boxes.forEach((box, i) => box.to({ x: boxX(i), y: place.y, height: place.h }, t, dur));
        texts.forEach((text, i) => text.to({ x: boxCx(i), y: place.y + place.textDy, scale: place.textScale }, t, dur));
      };

      // 1.2: the box opens. Each part slides out in turn, then the questions show.
      const tOpen = open.cue('splits');
      boxes.forEach((box, i) => {
        box.to({ opacity: 1 }, tOpen, 0);
        const t = tOpen + i * 0.3;
        box.to({ x: boxX(i), y: BIG.y, width: BOX_W, height: BIG.h }, t, 0.8);
      });
      const landed = tOpen + 0.9 + 0.8;
      open.beat(landed - 0.5, 0.5);
      const tQuiet = open.beat(open.frac(0.42), 0.6, 0.3);
      texts.forEach((text) => text.in(tQuiet, 0.6));
      QUESTIONS.forEach((_, i) => quiet(i, tQuiet));

      const traceLabel = g.text('Trace', { x: X0, y: 610, size: 34, weight: 700, font: 'display', color: C.heading });
      const log = logLines(g, { y0: 668 });
      const room = open.end - open.lastLand - 0.1;
      const step = Math.max(1.0, room / 4);
      log.forEach((row, i) => {
        const t = open.beat(open.lastLand + (i === 0 ? 0.3 : step - 0.6), 0.6, 0.3);
        if (i > 0) quiet(i - 1, t);
        light(i, t);
        row.in(t, 0.6);
      });
      traceLabel.in(open.cue('every step'), 0.5);

      // 1.3: the diagram moves to the top and box 1 lights.
      const evidence = by['1.3'];
      quiet(3, evidence.t0);
      log.forEach((row) => row.out(evidence.t0, 0.6));
      traceLabel.out(evidence.t0, 0.6);
      moveAll(COMPACT, evidence.t0, 0.7);
      light(0, evidence.cue('evidence'));

      // 1.4: boxes 2, 3 and 4 light in turn.
      const escalate = by['1.4'];
      quiet(0, escalate.t0);
      light(1, escalate.cue('trees'));
      light(2, escalate.cue('contradiction'));
      light(3, escalate.cue('officer'));

      // 1.5: a return arrow from box 4 to box 2, and a padlock on box 3.
      const learn = by['1.5'];
      quiet(2, learn.t0);
      const yUnder = COMPACT.y + COMPACT.h;
      const back = g.path(`M${boxCx(3)} ${yUnder} V${yUnder + 34} H${boxCx(1)} V${yUnder + 12}`, { stroke: C.navy, width: 6 });
      const backTip = g.path(kit.arrowHead(boxCx(1), yUnder, 'up', 18), { fill: C.navy });
      const tBack = learn.cue('reviews');
      back.drawIn(tBack, 0.8);
      backTip.in(tBack + 0.5, 0.4);
      const lock = kit.padlock(g, boxX(2) + BOX_W - 42, COMPACT.y + COMPACT.h / 2 - 6, 60, C.navy);
      lock.in(learn.cue('written rules'), 0.6, { dy: -12 });

      // 1.6: the diagram goes quiet while the chart speaks.
      const results = by['1.6'];
      quiet(1, results.t0);
      quiet(3, results.t0);

      // 1.7 to 1.9: large again, with labels that change.
      const bank = by['1.7'];
      back.out(bank.t0, 0.5);
      backTip.out(bank.t0, 0.5);
      lock.out(bank.t0, 0.5);
      moveAll(TALL, bank.t0 + 0.1, 0.9);
      const gov = by['1.8'];
      const agent = by['1.9'];
      const closing = by['1.10'];

      const appLabel = g.text('Application:', { x: X0, y: 280, size: 34, color: C.inkMuted });
      const appX = X0 + kit.textWidth('Application:', 34) + 18;
      const caption = g.text(CAPTION_SAME, { x: 960, y: 760, align: 'center', size: 36, weight: 600, color: C.inkMuted });
      const domains = [
        { scene: bank, app: 'Loan file', labels: ['Income papers', 'Fraud, default', 'Lending rules', 'Analyst'] },
        { scene: gov, app: 'Benefit claim', labels: ['Claim papers', 'Wrong payment', 'The law', 'Caseworker'] },
        { scene: agent, app: 'Move money, delete data', labels: ['Request, approvals', 'Money lost, data gone', 'Written limits', 'Its owner'] },
      ];
      // The highlight sits under the text it marks.
      const appMark = g.box({ x: appX - 14, y: 250, w: kit.textWidth(domains[2].app, 40, 700, 'display') + 28, h: 60, fill: C.sand, r: 8, opacity: 0 });
      const made = domains.map((d) => ({
        app: g.text(d.app, { x: appX, y: 280, size: 40, weight: 700, font: 'display', color: C.heading }),
        labels: d.labels.map((label, i) => {
          const item = g.text(label, { x: boxCx(i), y: TALL.y + 218, w: 350, align: 'center', size: 36, weight: 600, color: C.navy, lh: 1.14 });
          return item;
        }),
      }));
      const showLabel = (d, i, t, active) => {
        const item = made[d].labels[i];
        item.in(t, 0.5);
        if (active) item.to({ color: C.inverse }, t, 0.5);
      };
      const clearDomain = (d, t) => {
        made[d].app.out(t, 0.5);
        made[d].labels.forEach((item) => item.out(t, 0.5));
      };

      let t = bank.beat('bank', 0.5);
      appLabel.in(t, 0.5);
      made[0].app.in(t, 0.5);
      caption.in(t, 0.5);
      t = bank.beat('income papers', 0.5, 0.5);
      light(0, t);
      showLabel(0, 0, t, true);
      const tRisk = bank.beat('fraud', 0.5, 0.5);
      quiet(0, tRisk);
      made[0].labels[0].to({ color: C.navy }, tRisk, 0.5);
      light(1, tRisk);
      showLabel(0, 1, tRisk, true);
      const tRules = bank.beat('mismatch', 0.5, 0.5);
      quiet(1, tRules);
      made[0].labels[1].to({ color: C.navy }, tRules, 0.5);
      showLabel(0, 2, tRules, false);
      const tAnalyst = bank.beat('analyst', 0.5, 0.4);
      light(3, tAnalyst);
      showLabel(0, 3, tAnalyst, true);

      quiet(3, gov.t0);
      clearDomain(0, gov.t0);
      t = gov.beat('government', 0.5, 0.3);
      made[1].app.in(t, 0.5);
      showLabel(1, 0, t + 0.3, false);
      showLabel(1, 1, t + 0.6, false);
      gov.beat(t + 0.6, 0.5, 0);
      t = gov.beat('law', 0.5, 0.4);
      light(2, t);
      showLabel(1, 2, t, true);
      t = gov.beat('caseworker', 0.5, 0.6);
      quiet(2, t);
      made[1].labels[2].to({ color: C.navy }, t, 0.5);
      light(3, t);
      showLabel(1, 3, t, true);

      quiet(3, agent.t0);
      clearDomain(1, agent.t0);
      t = agent.beat('move money', 0.5, 0.3);
      made[2].app.in(t, 0.5);
      t = agent.beat('treat', 0.6, 0.5);
      appMark.to({ opacity: 1 }, t, 0.6);
      appMark.out(agent.cue('What supports it'), 0.5);
      showLabel(2, 2, agent.beat('application', 0.5, 0.2), false);
      t = agent.beat('What supports it', 0.5, 0.5);
      light(0, t);
      showLabel(2, 0, t, true);
      t = agent.beat('What could go wrong', 0.5, 0.5);
      quiet(0, t);
      made[2].labels[0].to({ color: C.navy }, t, 0.5);
      light(1, t);
      showLabel(2, 1, t, true);
      t = agent.beat('Does it need a person', 0.5, 0.5);
      quiet(1, t);
      made[2].labels[1].to({ color: C.navy }, t, 0.5);
      light(3, t);
      showLabel(2, 3, t, true);

      // 1.10: the diagram waits at the top, then comes back together for the closing phrases.
      quiet(3, closing.t0);
      clearDomain(2, closing.t0);
      appLabel.out(closing.t0, 0.5);
      caption.out(closing.t0, 0.5);
      moveAll(COMPACT, closing.t0, 0.7);
      const together = closing.cue('Automatic') - 0.9;
      moveAll(BIG, together, 0.9);
      QUESTIONS.forEach((_, i) => light(i, together + 0.3));
    }

    // ---- 1.3: evidence.
    function evidenceScene(g, s) {
      const letter = kase.documents.attachments.find((a) => a.name === 'police_letter.txt').text.split('\n').filter((l) => l.trim());
      const police = kase.evidence.find((e) => e.evidence_type === 'police_escort_letter');
      const dateField = police.fields.find((f) => f.name === 'event_date');
      const signer = police.fields.find((f) => f.name === 'signed_by').value;
      const [before, after] = dateField.quote.split(dateField.value);
      const verdict = police.verdict[0].toUpperCase() + police.verdict.slice(1);

      const paper = g.group({});
      paper.box({ x: 90, y: 240, w: 900, h: 760, fill: C.surface, stroke: C.hairline, sw: 2, r: 12 });
      paper.text(letter[0], { x: 140, y: 310, size: 34, weight: 700, font: 'display', color: C.heading });
      paper.text(letter[1], { x: 140, y: 362, size: 30, color: C.inkMuted });
      paper.text(letter.find((l) => l.startsWith('Re:')), { x: 140, y: 450, size: 32, color: C.ink });
      const quote = paper.text(`<span data-k="q">${before}<span data-k="d">${dateField.value}</span>${after}</span>`, { x: 140, y: 640, w: 800, size: 44, html: true, lh: 1.32, color: C.ink });
      paper.text(signer, { x: 140, y: 880, size: 32, color: C.ink });
      const llm = kit.pill(g, 'agentic LLM', { x: 950, y: 310, align: 'right' });
      const q = quote.part('q');
      const d = quote.part('d');

      const tickIcon = kit.tick(g, 1090, 300, 64);
      const tickText = g.text('The quote is in the document', { x: 1140, y: 300, w: 690, size: 38, weight: 600 });
      const codeCheck = kit.pill(g, 'code check', { x: 1060, y: 412 });
      const dateCards = ['Form', 'Letter'].map((name, i) => {
        const card = g.group({});
        const x = 1060 + i * 385;
        card.box({ x, y: 450, w: 365, h: 170, fill: C.muted, stroke: i === 1 ? C.danger : C.hairline, sw: 3, r: 12 });
        card.text(name, { x: x + 182, y: 495, align: 'center', size: 30, color: C.inkMuted });
        card.text(i === 0 ? longDate(kase.documents.form.event_date) : dateField.value, { x: x + 182, y: 565, align: 'center', size: 32, weight: 700, font: 'mono', color: i === 1 ? C.danger : C.navy });
        return card;
      });
      const crossIcon = kit.cross(g, 1090, 690, 64);
      const crossText = g.text('The date matches', { x: 1140, y: 690, size: 38, weight: 600 });
      const stamp = kit.stamp(g, verdict, { x: 1060, y: 780, w: 600, h: 130, size: 64 });

      const tQuote = s.beat('quote', 0.7);
      q.to({ bg: C.sand }, tQuote, 0.7);
      llm.in(tQuote, 0.7);
      const tTick = s.beat('This police letter', 0.6, 0.5);
      tickIcon.drawIn(tTick, 0.6);
      tickText.in(tTick, 0.6);
      const tDate = s.beat('wrong date', 0.7);
      d.to({ bg: C.dangerSoft, color: C.danger }, tDate, 0.7);
      const tCompare = s.beat('separate check', 0.5);
      codeCheck.in(tCompare, 0.5);
      const tCards = s.beat('compares', 0.5, 0.3);
      dateCards[0].in(tCards, 0.5);
      dateCards[1].in(tCards + 0.35, 0.5);
      s.beat(tCards + 0.35, 0.5, 0);
      const tCross = s.beat('rejects', 0.5, 0.4);
      crossIcon.drawIn(tCross, 0.5);
      crossText.in(tCross, 0.5);
      stamp.in(s.beat('the letter', 0.6, 0.3), 0.6, { scale: 1.06 });
    }

    // ---- 1.4: escalation.
    function escalationScene(g, s) {
      const paths = [
        { label: 'Contradiction', y: 330, cue: 'contradiction' },
        { label: 'Missing insurance', y: 450, cue: 'missing insurance' },
        { label: 'Risk not clearly low', y: 570, cue: 'clearly low' },
      ];
      const caseY = 580;
      const officerY = 450;
      const flowD = (x1, y1, x2, y2) => `M${x1} ${y1} C${(x1 + x2) / 2} ${y1},${(x1 + x2) / 2} ${y2},${x2} ${y2}`;

      const trees = g.text('Trees score risk', { x: boxCx(1), y: 234, align: 'center', size: 30, weight: 600, color: C.heading });

      const low = g.group({ opacity: 0.62 });
      low.path(`${flowD(310, caseY, 520, 820)} H1020 ${flowD(1020, 820, 1380, 820).replace(/^M\S+ \S+/, '')}`, { stroke: C.strong, width: 5 });
      low.box({ x: 520, y: 776, w: 500, h: 88, fill: C.surface, stroke: C.strong, sw: 2, r: 10 });
      low.text('Low risk, clean evidence', { x: 770, y: 820, align: 'center', size: 34 });
      low.box({ x: 1380, y: 770, w: 460, h: 100, fill: C.successSoft, r: 12 });
      low.text('Approved', { x: 1610, y: 820, align: 'center', size: 44, weight: 700, font: 'display', color: C.success });

      const made = paths.map((p) => {
        const line = g.path(`${flowD(310, caseY, 520, p.y)} H1020 ${flowD(1020, p.y, 1380, officerY).replace(/^M\S+ \S+/, '')}`, { stroke: C.navy, width: 7 });
        const card = g.group({});
        card.box({ x: 520, y: p.y - 44, w: 500, h: 88, fill: C.tint, stroke: C.navy, sw: 2, r: 10 });
        card.text(p.label, { x: 770, y: p.y, align: 'center', size: 36, weight: 600, color: C.navy });
        return { ...p, line, card };
      });

      g.box({ x: 80, y: caseY - 70, w: 230, h: 140, fill: C.surface, stroke: C.strong, sw: 3, r: 12 });
      g.text('Case', { x: 195, y: caseY, align: 'center', size: 44, weight: 700, font: 'display', color: C.heading });

      const desk = g.box({ x: 1380, y: 310, w: 460, h: 280, fill: C.tint, r: 14 });
      const person = kit.person(g, 1610, 410, 100, C.navy);
      const deskText = g.text('Officer', { x: 1610, y: 510, align: 'center', size: 48, weight: 700, font: 'display', color: C.navy });
      const reason = g.text('Reason attached', { x: 1610, y: 638, align: 'center', size: 34, weight: 600, color: C.heading });
      kit.caption(g, officerLabel, { y: 1000, size: 30 });

      trees.in(s.beat('trees', 0.5), 0.5);
      for (const p of made) {
        const t = s.beat(p.cue, 0.7, 0.5);
        p.line.drawIn(t, 0.7);
        p.card.in(t, 0.5);
      }
      const t = s.beat('officer', 0.6, 0.5);
      desk.to({ bg: C.navy }, t, 0.6);
      deskText.to({ color: C.inverse }, t, 0.6);
      person.head.to({ bg: C.inverse }, t, 0.6);
      person.body.to({ fill: C.inverse }, t, 0.6);
      reason.in(s.beat('reason attached', 0.5, 0.5), 0.5);
    }

    // ---- 1.5: learning, on the real tree and the real correction.
    function learningScene(g, s) {
      const tree = kase.hazards.find((h) => h.id === 'traffic_conflict').likelihood;
      const [qa, qb] = tree.questions.map((q) => q.id);
      const changes = kase.correction.changes.filter((c) => c.tree_id === tree.tree_id);
      const rows = [true, false].flatMap((a) => [true, false].map((b) => {
        const when = (o) => o[qa] === a && o[qb] === b;
        const leaf = tree.leaves.find((l) => when(l.when));
        const change = changes.find((c) => when(c.leaf));
        return { a, b, leaf, before: change ? change.before : leaf.levels, after: change ? change.after : leaf.levels, label: `${a ? 'Escort' : 'No escort'}, ${b ? 'good plan' : 'poor plan'}` };
      }));
      const ys = [340, 490, 640, 790];
      const midY = [415, 715];
      const rootY = 565;
      const curve = (x1, y1, x2, y2) => `M${x1} ${y1} C${(x1 + x2) / 2} ${y1},${(x1 + x2) / 2} ${y2},${x2} ${y2}`;
      const treeGroup = g.group({});
      rows.forEach((row, i) => {
        const mid = midY[i < 2 ? 0 : 1];
        treeGroup.path(curve(380, mid, 640, ys[i]), { stroke: C.navy, width: Math.max(2, 18 * row.leaf.reach) });
      });
      [0, 1].forEach((j) => {
        const share = rows[j * 2].leaf.reach + rows[j * 2 + 1].leaf.reach;
        treeGroup.path(curve(120, rootY, 380, midY[j]), { stroke: C.navy, width: Math.max(2, 18 * share) });
      });
      treeGroup.box({ x: 100, y: rootY - 20, w: 40, h: 40, fill: C.navy, r: 20 });
      midY.forEach((y) => treeGroup.box({ x: 362, y: y - 18, w: 36, h: 36, fill: C.navy, r: 18 }));

      const bars = rows.map((row, i) => {
        const y = ys[i];
        const text = treeGroup.text(row.label, { x: 660, y, size: 32, weight: i === 2 ? 700 : 400, color: i === 2 ? C.heading : C.ink });
        const bar = kit.levelBar(treeGroup, { x: 1000, y: y - 26, w: 480, h: 52, levels: row.before });
        const likelyNow = Math.round(row.before[2] * 100);
        const likelyAfter = Math.round(row.after[2] * 100);
        const value = treeGroup.text(`${likelyNow}%`, { x: 1510, y, size: i === 2 ? 44 : 34, weight: 700, font: 'mono', color: C.navy });
        const word = treeGroup.text('likely', { x: 1510 + (i === 2 ? 118 : 90), y, size: 32, color: C.inkMuted });
        return { row, bar, value, word, text, likelyNow, likelyAfter };
      });
      // The level names sit under the leaf that moves.
      const mover = bars[2];
      const names = tree.level_names.map((name, i) => treeGroup.text(name, { x: mover.bar.center(i, mover.row.after), y: ys[2] + 56, align: 'center', size: 28, color: C.inkMuted }));
      kit.caption(g, officerLabel, { y: 1000, size: 30 });

      const tTree = s.beat('numbers', 0.7);
      treeGroup.in(tTree, 0.7);
      const tMove = s.beat('those trees', 0.9, 0.5);
      for (const b of bars) {
        b.bar.morph(b.row.after, tMove, 0.9);
        if (b.likelyNow !== b.likelyAfter) b.value.count(b.likelyNow, b.likelyAfter, tMove, 0.9, (v) => `${Math.round(v)}%`);
      }
      const tDim = s.beat('written rules', 0.6, 0.3);
      treeGroup.dim(tDim, 0.45, 0.6);
      const locked = g.text('Written rules: locked', { x: boxCx(2), y: 268, align: 'center', size: 32, weight: 600, color: C.heading });
      locked.in(s.beat('never change', 0.5, 0.2), 0.5);
    }

    // ---- 1.6: what the demo showed.
    function resultsScene(g, s) {
      const curve = data.learning.curve;
      const first = curve[0];
      const last = curve[curve.length - 1];
      const x0 = 260;
      const x1 = 1660;
      const y0 = 880;
      const y1 = 330;
      const low = 0.5;
      const high = 1;
      const px = (c) => x0 + ((c - first.corrections) / (last.corrections - first.corrections)) * (x1 - x0);
      const py = (r) => y0 - ((r - low) / (high - low)) * (y0 - y1);
      const label = kit.pill(g, officerLabel, { x: 960, y: 278, align: 'center', size: 32 });
      const axes = g.group({});
      for (const tick of [0.6, 0.8, 1]) {
        axes.path(`M${x0} ${py(tick)} H${x1}`, { stroke: C.grid, width: 2 });
        axes.text(`${Math.round(tick * 100)}%`, { x: x0 - 20, y: py(tick), align: 'right', size: 28, font: 'mono', color: C.inkMuted });
      }
      axes.path(`M${x0} ${y0} H${x1}`, { stroke: C.strong, width: 3 });
      axes.text(String(first.corrections), { x: x0, y: y0 + 36, align: 'center', size: 28, font: 'mono', color: C.inkMuted });
      axes.text('Officer reviews', { x: 960, y: y0 + 36, align: 'center', size: 30, color: C.inkMuted });
      const lastTick = g.text(String(last.corrections), { x: x1, y: y0 + 36, align: 'center', size: 28, font: 'mono', weight: 700, color: C.navy });
      const line = g.path(`M${curve.map((c) => `${px(c.corrections).toFixed(1)} ${py(c.right_level).toFixed(1)}`).join(' L')}`, { stroke: C.navy, width: 7 });
      const startValue = g.text(`${Math.round(first.right_level * 100)}%`, { x: x0 + 30, y: py(first.right_level) + 62, size: 76, weight: 700, font: 'mono', color: C.navy });
      const endValue = g.text(`${Math.round(last.right_level * 100)}%`, { x: x1, y: py(last.right_level) + 70, align: 'right', size: 76, weight: 700, font: 'mono', color: C.navy });
      const caption = kit.caption(g, `Right risk level on ${first.held_out_cases} set-aside cases. The officer's rubric is the source of the answer key.`, { y: 1006, size: 30 });

      label.in(s.beat('AI plays', 0.6), 0.6);
      const tAxes = s.beat('cases set aside', 0.6, 0.6);
      axes.in(tAxes, 0.6);
      caption.in(tAxes, 0.6);
      startValue.in(s.beat('70 percent', 0.5, 0.5), 0.5);
      const tLine = s.beat('at first', 1.2, 0.3);
      line.drawIn(tLine, 1.2);
      endValue.in(s.beat('87 percent', 0.5, 0.2), 0.5);
      lastTick.in(s.beat('115', 0.5, 0.2), 0.5);
    }

    // ---- 1.10: the honest limit, then the closing phrases.
    function closingScene(g, s) {
      const statement = g.text(CAPTION_SYNTHETIC, { x: 960, y: 420, align: 'center', size: 56, weight: 700, font: 'display', color: C.heading });
      const yes = g.group({});
      kit.tick(yes, 560, 560, 56);
      yes.text('Shows the method can learn', { x: 610, y: 560, size: 44, weight: 600 });
      const no = g.group({});
      kit.cross(no, 560, 660, 56);
      no.text('Not that it predicts real risk', { x: 610, y: 660, size: 44, weight: 600 });

      statement.in(s.beat('made-up permits', 0.6), 0.6);
      yes.in(s.beat('method can learn', 0.5, 0.5), 0.5);
      no.in(s.beat('predicts real risk', 0.5, 0.5), 0.5);

      const together = s.cue('Automatic') - 0.9;
      yes.out(together, 0.5);
      no.out(together, 0.5);
      statement.to({ y: 1024, scale: 0.56 }, together, 0.9);
      s.lastLand = together + 0.9;

      const bracket = g.path(`M${boxX(0)} 340 V322 H${boxX(2) + BOX_W} V340`, { stroke: C.navy, width: 4 });
      const auto = g.text('Automatic where it can be', { x: (boxX(0) + boxX(2) + BOX_W) / 2, y: 288, align: 'center', size: 44, weight: 700, font: 'display', color: C.heading });
      const person = g.text('A person for the hard cases', { x: boxCx(3), y: 272, w: 400, align: 'center', size: 40, weight: 700, font: 'display', color: C.heading, lh: 1.14 });
      const log = logLines(g, { y0: 700 });
      const traced = g.text('Traceable every time', { x: 960, y: 620, align: 'center', size: 44, weight: 700, font: 'display', color: C.heading });

      const tAuto = s.beat('Automatic', 0.6, 0.1);
      bracket.drawIn(tAuto, 0.6);
      auto.in(tAuto, 0.6);
      const tTraced = s.beat('traceable', 0.6, 0.5);
      traced.in(tTraced, 0.6);
      log.forEach((row) => row.in(tTraced, 0.6));
      person.in(s.beat('a person', 0.6, 0.5), 0.6);
    }

    const all = ['1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7', '1.8', '1.9', '1.10'];
    return [
      { scenes: ['1.1', '1.2'], build: sealedBox },
      { scenes: all, build: diagram },
      { scenes: ['1.3'], build: evidenceScene },
      { scenes: ['1.4'], build: escalationScene },
      { scenes: ['1.5'], build: learningScene },
      { scenes: ['1.6'], build: resultsScene },
      { scenes: ['1.10'], build: closingScene },
    ];
  };
})();
