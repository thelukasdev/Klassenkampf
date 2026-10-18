/* Canvas-Renderer fuer alle 7 Spiele. Logische Aufloesung 240x280.
   drawGame(gid, s, role, ctx, R)  – R haelt persistente Zeichen-Zustaende. */
(function () {
  const W = 240, H = 280;
  const COL = {
    BG: '#000', FRAME: '#181C18', P1: '#73D363', P2: '#FFA600',
    HEAD: '#ffffff', TEXT: '#ffffff', DIM: '#7B7D7B', BALL: '#FFFF00',
    SHOT1: '#94EB84', SHOT2: '#FFCB00', TRACK: '#424142',
    SHOCK: '#CE82FF', SHIELD: '#FFFF00', GRASS: '#006500',
    P3: '#4FC3FF', P4: '#FF5FD2',
  };
  const PC = [COL.P1, COL.P2, COL.P3, COL.P4];   // Spielerfarben nach Rolle
  const WR = { 0: '#00FFFF', 1: '#FFFF00', 2: '#00FF00', 3: '#FF00FF' }; // U D L R

  function text(ctx, str, x, y, c, size, bold, align) {
    ctx.fillStyle = c; ctx.textAlign = align || 'center'; ctx.textBaseline = 'alphabetic';
    ctx.font = (bold ? 'bold ' : '') + (size || 12) + 'px sans-serif';
    ctx.fillText(str, x, y);
  }
  function rect(ctx, x, y, w, h, c) { ctx.fillStyle = c; ctx.fillRect(x, y, w, h); }
  function strokeRect(ctx, x, y, w, h, c, lw) { ctx.strokeStyle = c; ctx.lineWidth = lw || 1; ctx.strokeRect(x + .5, y + .5, w, h); }
  function circle(ctx, x, y, r, c, fill) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7); if (fill) { ctx.fillStyle = c; ctx.fill(); } else { ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.stroke(); }
  }

  function endOverlay(ctx, title, tcol, line2) {
    const bx = 20, by = 110, bw = 200, bh = 90;
    rect(ctx, bx, by, bw, bh, COL.BG); strokeRect(ctx, bx, by, bw, bh, COL.TEXT, 1);
    text(ctx, title, 120, by + 34, tcol, 18, true);
    if (line2) text(ctx, line2, 120, by + 60, COL.TEXT, 14, false);
    text(ctx, 'Runde beendet', 120, by + 80, COL.DIM, 11, false);
  }

  // ---------------- TRON ----------------
  // Spur zwischen zwei Kopfpositionen luecklos fuellen (Bewegung ist achsenparallel).
  function fillTrail(trail, gh, from, to, v) {
    const [x1, y1] = to;
    if (!from) { trail[x1 * gh + y1] = v; return; }
    const [x0, y0] = from;
    if (x0 === x1) { for (let y = Math.min(y0, y1); y <= Math.max(y0, y1); y++) trail[x1 * gh + y] = v; }
    else if (y0 === y1) { for (let x = Math.min(x0, x1); x <= Math.max(x0, x1); x++) trail[x * gh + y1] = v; }
    else { trail[x0 * gh + y0] = v; trail[x1 * gh + y1] = v; }  // (Abbiegung im uebersprungenen Frame)
  }
  function tron(ctx, s, role, R) {
    const [gw, gh] = s.gsz, cell = s.cell, [ox, oy] = s.off, n = s.h.length;
    if (R.tRnd !== s.rnd) { R.tRnd = s.rnd; R.trail = new Uint8Array(gw * gh); R.tSnap = null; R.th = []; }
    if (R.tSnap !== s) {
      R.tSnap = s;
      if (s.st === 0) s.h.forEach((h, i) => {
        if (!s.act[i]) return;
        fillTrail(R.trail, gh, R.th[i], [h[0], h[1]], i + 1);
        R.th[i] = [h[0], h[1]];
      });
    }
    strokeRect(ctx, 5, 25, 230, 230, COL.FRAME, 1);
    for (let x = 0; x < gw; x++) for (let y = 0; y < gh; y++) {
      const v = R.trail[x * gh + y];
      if (v) rect(ctx, ox + x * cell, oy + y * cell, cell, cell, PC[v - 1]);
    }
    if (s.st === 0) s.h.forEach(h => { if (h[2]) rect(ctx, ox + h[0] * cell, oy + h[1] * cell, cell, cell, COL.HEAD); });
    // Punkte aller Spieler nebeneinander, der eigene unterstrichen
    for (let i = 0; i < n; i++) {
      const x = 240 * (i + 0.5) / n;
      text(ctx, '' + s.sc[i], x, 18, s.act[i] ? PC[i] : COL.DIM, 16, true);
      if (i === role - 1) rect(ctx, x - 6, 21, 12, 2, PC[i]);
    }
    if (s.st !== 0) {
      const t = s.rw === role ? 'RUNDE GEWONNEN' : s.rw ? 'P' + s.rw + ' GEWINNT' : 'UNENTSCHIEDEN';
      endOverlay(ctx, t, s.rw ? PC[s.rw - 1] : COL.TEXT, s.sc.join(' : ') + `   (bis ${s.win})`);
    }
  }

  // ---------------- PONG ----------------
  function pong(ctx, s, role) {
    const mir = role === 1;
    // Spielfeld-Mitte (Rahmen 28..278) = 153 -> um diese Achse spiegeln,
    // damit die Paddles perspektiv-unabhaengig im Rahmen bleiben.
    const my = (y) => mir ? (306 - y) : y;
    text(ctx, `${role === 1 ? s.s1 : s.s2} : ${role === 1 ? s.s2 : s.s1}`, 120, 18, COL.TEXT, 15, true);
    strokeRect(ctx, 0, 28, 240, 250, COL.FRAME, 1);
    ctx.strokeStyle = COL.DIM; ctx.lineWidth = 1;
    for (let x = 6; x < 234; x += 10) { ctx.beginPath(); ctx.moveTo(x, 153); ctx.lineTo(x + 6, 153); ctx.stroke(); }
    // Paddles (Besitzerfarbe)
    let p1y = mir ? (306 - s.p1y - s.ph) : s.p1y;
    let p2y = mir ? (306 - s.p2y - s.ph) : s.p2y;
    rect(ctx, s.p1x, p1y, s.pw, s.ph, COL.P1);
    rect(ctx, s.p2x, p2y, s.pw, s.ph, COL.P2);
    circle(ctx, s.bx, my(s.by), s.br, COL.BALL, true);
    if (s.cd) text(ctx, '' + s.cd, 120, 168, COL.TEXT, 46, true);
    if (s.st === 1 || s.st === 2) {
      const iWon = (s.st === 1 && role === 1) || (s.st === 2 && role === 2);
      endOverlay(ctx, iWon ? 'GEWONNEN' : 'VERLOREN', iWon ? COL.P1 : COL.P2,
        `${role === 1 ? s.s1 : s.s2} : ${role === 1 ? s.s2 : s.s1}`);
    }
  }

  // ---------------- DUEL ----------------
  function ship(ctx, sh, c, role) {
    if (sh.iv && (Date.now() / 80 | 0) & 1) return; // Blinken
    const a = sh.a, pts = [[9, 0], [-6, -5], [-6, 5]];
    ctx.strokeStyle = c; ctx.lineWidth = 1.4; ctx.beginPath();
    pts.forEach((p, i) => {
      const x = sh.x + p[0] * Math.cos(a) - p[1] * Math.sin(a);
      const y = sh.y + p[0] * Math.sin(a) + p[1] * Math.cos(a);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.closePath(); ctx.stroke();
    if (sh.sh) { circle(ctx, sh.x, sh.y, 12, c, false); circle(ctx, sh.x, sh.y, 13, c, false); }
  }
  function duel(ctx, s, role) {
    text(ctx, `${s.s1}   :   ${s.s2}`, 120, 24, COL.TEXT, 15, true);
    // eigener Schild-Balken
    const me = s.s[String(role)], myc = role === 1 ? COL.P1 : COL.P2;
    strokeRect(ctx, 20, 4, 200, 4, COL.FRAME, 1);
    rect(ctx, 21, 5, (me.ch * 198 / s.shmax), 2, me.lk ? COL.DIM : myc);
    ctx.strokeStyle = COL.FRAME; ctx.beginPath(); ctx.moveTo(0, 30); ctx.lineTo(240, 30); ctx.stroke();
    s.sh.forEach(sh => rect(ctx, sh[0] - 1, sh[1] - 1, 2, 2, sh[2] === 1 ? COL.SHOT1 : COL.SHOT2));
    if (s.s['1'].al) ship(ctx, s.s['1'], COL.P1, role);
    if (s.s['2'].al) ship(ctx, s.s['2'], COL.P2, role);
    if (s.st !== 0) {
      const iWon = (s.st === role);
      endOverlay(ctx, iWon ? 'GEWONNEN' : 'VERLOREN', iWon ? COL.P1 : COL.P2, `${s.s1}  :  ${s.s2}`);
    }
  }

  // ---------------- TANKS ----------------
  function tanks(ctx, s, role, R) {
    // Terrain aus dem echten Pixel-Gitter (zeigt Hohlraeume & Einsturz)
    const g = R && R.tgrid;
    if (g) {
      const ROWS = 180;
      ctx.fillStyle = COL.TRACK;
      const tops = [];
      for (let x = 0; x < 240; x++) {
        let gy = 0;
        while (gy < ROWS) {
          let idx = x * ROWS + gy;
          if ((g[idx >> 3] >> (idx & 7)) & 1) {
            const start = gy;
            while (gy < ROWS) { const j = x * ROWS + gy; if ((g[j >> 3] >> (j & 7)) & 1) gy++; else break; }
            ctx.fillRect(x, 100 + start, 1, gy - start);   // Saeule/Segment
            tops.push(x, 100 + start);                     // Oberkante -> Highlight
          } else gy++;
        }
      }
      ctx.fillStyle = COL.TEXT;
      for (let i = 0; i < tops.length; i += 2) ctx.fillRect(tops[i], tops[i + 1], 1, 1);
    }
    // Panzer
    for (let i = 0; i < 2; i++) {
      const c = i === 0 ? COL.P1 : COL.P2, x = s.tx[i], y = s.ty[i];
      rect(ctx, x - 6, y - 4, 12, 4, c); rect(ctx, x - 5, y - 7, 10, 3, c);
      if (s.act === i + 1 && s.ph === 0) {
        const rad = s.ang[i] * Math.PI / 180; let dx = Math.cos(rad), dy = -Math.sin(rad);
        if (i === 1) dx = -dx;
        ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.beginPath();
        ctx.moveTo(x, y - 6); ctx.lineTo(x + dx * 14, y - 6 + dy * 14); ctx.stroke();
      }
      // Schild
      const sh = s.sh[i];
      if (sh) { ctx.fillStyle = COL.SHIELD; sh.forEach(seg => { const ang = seg / 32 * 6.283; ctx.fillRect(x + Math.cos(ang) * 22 - 1, y + Math.sin(ang) * 22 - 1, 2, 2); }); }
    }
    // Aktiv-Pfeil
    const ax = s.tx[s.act - 1], ac = s.act === 1 ? COL.P1 : COL.P2;
    ctx.fillStyle = ac; ctx.beginPath(); ctx.moveTo(ax - 5, s.ty[s.act - 1] - 34); ctx.lineTo(ax + 5, s.ty[s.act - 1] - 34); ctx.lineTo(ax, s.ty[s.act - 1] - 26); ctx.fill();
    // Projektil
    if (s.prj) circle(ctx, s.prj[0], s.prj[1], 2, s.prj[2] === 1 ? COL.SHOT1 : COL.SHOT2, true);
    // Explosion
    if (s.exp) {
      const [ex, ey, mr, fr, cc] = s.exp; let r = mr;
      if (fr < 18) r = mr * fr / 18; else if (fr >= 20) r = mr * (1 - (fr - 20) / 18);
      const c = cc === 'SHOCK' ? COL.SHOCK : cc === 'SHIELD' ? COL.SHIELD : (s.act === 1 ? COL.P2 : COL.P1);
      circle(ctx, ex, ey, Math.max(1, r), c, true);
    }
    // HUD
    strokeRect(ctx, 17, 10, 60, 12, COL.FRAME, 1); rect(ctx, 18, 11, s.hp[0] * 58 / s.maxhp, 10, COL.P1);
    strokeRect(ctx, 163, 10, 60, 12, COL.FRAME, 1); rect(ctx, 164, 11, s.hp[1] * 58 / s.maxhp, 10, COL.P2);
    text(ctx, `${s.wins[0]} - ${s.wins[1]}`, 120, 16, COL.TEXT, 13, true);
    // Wind
    strokeRect(ctx, 88, 24, 64, 9, COL.FRAME, 1);
    const wc = 120, wl = s.wind * 3;
    rect(ctx, wl >= 0 ? wc : wc + wl, 26, Math.abs(wl), 5, s.wind === 0 ? COL.DIM : COL.TEXT);
    text(ctx, 'Wind', 120, 44, COL.DIM, 9, false);
    // Aim-HUD unten
    const ai = s.act - 1;
    strokeRect(ctx, 15, 244, 130, 18, COL.FRAME, 1);
    rect(ctx, 16, 245, (s.pow[ai] - 10) * 128 / 90, 16, s.act === 1 ? COL.P1 : COL.P2);
    text(ctx, ('00' + s.ang[ai]).slice(-3) + '°', 172, 258, s.act === 1 ? COL.P1 : COL.P2, 15, true);
    const wn = s.wn[ai] + (s.ammo[ai] >= 0 ? ` (${s.ammo[ai]})` : '');
    text(ctx, wn, 120, 276, COL.TEXT, 11, false);
    if (s.rw >= 0) text(ctx, s.rw === 0 ? 'UNENTSCHIEDEN' : 'RUNDE: P' + s.rw, 120, 150, s.rw === 1 ? COL.P1 : s.rw === 2 ? COL.P2 : COL.TEXT, 20, true);
    if (s.ph === 4) {
      const iWon = (s.wins[0] > s.wins[1] ? 1 : 2) === role;
      endOverlay(ctx, iWon ? 'GEWONNEN' : 'VERLOREN', iWon ? COL.P1 : COL.P2, `${s.wins[0]} : ${s.wins[1]}`);
    }
  }

  // ---------------- WNR ----------------
  function arrow(ctx, cx, cy, dir, c, fill) {
    const h = 11, pts = { 0: [[0, -h], [-h, h], [h, h]], 1: [[0, h], [-h, -h], [h, -h]], 2: [[-h, 0], [h, -h], [h, h]], 3: [[h, 0], [-h, -h], [-h, h]] }[dir];
    ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(cx + p[0], cy + p[1]) : ctx.moveTo(cx + p[0], cy + p[1])); ctx.closePath();
    if (fill) { ctx.fillStyle = c; ctx.fill(); } else { ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.stroke(); }
  }
  function wnrField(ctx, x, y, dir, active) {
    const c = WR[dir], cx = x + 37, cy = y + 33;
    if (active) {
      ctx.strokeStyle = c; ctx.lineWidth = 2;
      roundRect(ctx, x, y, 74, 66, 8); ctx.stroke();
      arrow(ctx, cx, cy, dir, COL.TEXT, true);
    } else {
      ctx.strokeStyle = COL.DIM; ctx.lineWidth = 1; roundRect(ctx, x, y, 74, 66, 8); ctx.stroke();
      arrow(ctx, cx, cy, dir, c, false);
    }
  }
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function wnr(ctx, s, role) {
    if (s.ph >= 4) {
      const t = s.ph === 4 ? 'P1 GEWINNT' : s.ph === 5 ? 'P2 GEWINNT' : 'UNENTSCHIEDEN';
      const iWon = (s.ph === 3 + role);
      text(ctx, t, 120, 120, s.ph === 4 ? COL.P1 : s.ph === 5 ? COL.P2 : COL.TEXT, 22, true);
      text(ctx, 'Länge ' + s.len, 120, 158, COL.TEXT, 15, true);
      text(ctx, iWon ? 'Du hast gewonnen!' : (s.ph === 6 ? 'Remis' : 'Du hast verloren'), 120, 200, iWon ? COL.P1 : COL.DIM, 14, false);
      return;
    }
    // Rahmen in eigener Farbe, wenn man am Zug ist
    if (s.yourturn) { strokeRect(ctx, 0, 20, 240, 240, role === 1 ? COL.P1 : COL.P2, 2); }
    const lit = s.flash;
    wnrField(ctx, 83, 29, 0, lit === 0 || (s.invite));
    wnrField(ctx, 83, 185, 1, lit === 1 || (s.invite));
    wnrField(ctx, 5, 107, 2, lit === 2 || (s.invite));
    wnrField(ctx, 161, 107, 3, lit === 3 || (s.invite));
    circle(ctx, 120, 140, 19, COL.FRAME, false); circle(ctx, 120, 140, 18, COL.FRAME, false);
    text(ctx, '' + s.len, 120, 147, COL.TEXT, 16, true);
    const status = s.yourturn ? (s.ph === 1 ? 'MERKEN…' : s.ph === 2 ? 'WIEDERHOLEN' : 'NEUE RICHTUNG!') : 'Gegner ist dran';
    text(ctx, status, 120, 275, s.yourturn ? (role === 1 ? COL.P1 : COL.P2) : COL.DIM, 12, true);
  }

  // ---------------- CONNECT4 ----------------
  function c4(ctx, s, role) {
    const [NX, NY, OX, OY, CW, CH, PR] = s.geo;
    const pc = s.pl === 1 ? COL.P1 : COL.P2;
    if (s.st === 0) text(ctx, s.pl === 1 ? 'P1 ist am Zug' : 'P2 ist am Zug', 120, 18, pc, 14, true);
    else text(ctx, s.st === 1 ? 'P1 GEWINNT' : s.st === 2 ? 'P2 GEWINNT' : 'UNENTSCHIEDEN', 120, 18, s.st === 3 ? COL.TEXT : (s.st === 1 ? COL.P1 : COL.P2), 15, true);
    if (s.st === 0) {
      const cx = OX + s.cur * CW + CW / 2;
      circle(ctx, cx, 32, 9, pc, false); circle(ctx, cx, 32, 8, pc, true);
      ctx.fillStyle = pc; ctx.beginPath(); ctx.moveTo(cx - 4, 42); ctx.lineTo(cx + 4, 42); ctx.lineTo(cx, 47); ctx.fill();
    }
    strokeRect(ctx, OX - 2, OY - 2, NX * CW + 4, NY * CH + 4, COL.FRAME, 1);
    for (let c = 0; c < NX; c++) for (let r = 0; r < NY; r++) {
      const cx = OX + c * CW + CW / 2, cy = OY + r * CH + CH / 2, v = s.board[c][r];
      if (!v) circle(ctx, cx, cy, PR, COL.DIM, false);
      else { circle(ctx, cx, cy, PR, v === 1 ? COL.P1 : COL.P2, true); circle(ctx, cx, cy, PR, COL.TEXT, false); if (s.st === 0 && s.last[0] === c && s.last[1] === r) circle(ctx, cx, cy, PR - 4, COL.TEXT, false); }
    }
    if (s.st !== 0) {
      const iWon = s.st === role;
      endOverlay(ctx, iWon ? 'GEWONNEN' : (s.st === 3 ? 'UNENTSCHIEDEN' : 'VERLOREN'), iWon ? COL.P1 : (s.st === 3 ? COL.TEXT : COL.P2), '');
    }
  }

  // ---------------- DOTS ----------------
  function lineCenter(idx) {
    const NUM_H = 40;
    if (idx < NUM_H) { const c = idx % 5, r = (idx / 5 | 0); return ['H', c, r, 20 + (c + 0.5) * 40, 44 + r * 31]; }
    const v = idx - NUM_H, c = v % 6, r = (v / 6 | 0); return ['V', c, r, 20 + c * 40, 44 + (r + 0.5) * 31];
  }
  function dots(ctx, s, role) {
    const [NX, NY, OX, OY, CW, CH] = s.geo;
    text(ctx, '' + s.s1, 30, 22, COL.P1, 15, true);
    text(ctx, '' + s.s2, 210, 22, COL.P2, 15, true);
    if (s.st === 0) text(ctx, s.pl === 1 ? 'P1' : 'P2', 120, 22, s.pl === 1 ? COL.P1 : COL.P2, 14, true);
    else text(ctx, s.st === 1 ? 'P1 SIEGT' : s.st === 2 ? 'P2 SIEGT' : 'REMIS', 120, 22, COL.TEXT, 14, true);
    ctx.strokeStyle = COL.FRAME; ctx.beginPath(); ctx.moveTo(0, 30); ctx.lineTo(240, 30); ctx.stroke();
    // Boxen
    for (let c = 0; c < NX - 1; c++) for (let r = 0; r < NY - 1; r++) {
      const o = s.boxes[c][r]; if (!o) continue;
      const x = OX + c * CW + 4, y = OY + r * CH + 4, w = CW - 7, h = CH - 7, col = o === 1 ? COL.P1 : COL.P2;
      strokeRect(ctx, x, y, w, h, col, 1);
      text(ctx, '' + o, x + w / 2, y + h / 2 + 5, col, 12, true);
    }
    // gezeichnete Linien
    for (let i = 0; i < s.lines.length; i++) {
      if (!s.lines[i]) continue; const [o, c, r] = lineCenter(i);
      ctx.fillStyle = COL.TEXT;
      // mittig auf der Punktreihe (Punkte liegen auf 20+40c / 44+31r)
      if (o === 'H') ctx.fillRect(20 + 40 * c, 44 + 31 * r - 1, 40, 2); else ctx.fillRect(20 + 40 * c - 1, 44 + 31 * r, 2, 31);
    }
    // Cursor (blinkt) – exakt dieselbe Geometrie wie eine gesetzte Linie
    if (s.st === 0 && (Date.now() / 250 | 0) & 1) {
      const [o, c, r] = lineCenter(s.cur), col = s.pl === 1 ? COL.P1 : COL.P2;
      ctx.fillStyle = col;
      if (o === 'H') ctx.fillRect(20 + 40 * c, 44 + 31 * r - 1, 40, 2); else ctx.fillRect(20 + 40 * c - 1, 44 + 31 * r, 2, 31);
    }
    // Punkte
    ctx.fillStyle = COL.TEXT;
    for (let c = 0; c < NX; c++) for (let r = 0; r < NY; r++) { ctx.beginPath(); ctx.arc(20 + 40 * c, 44 + 31 * r, 2, 0, 7); ctx.fill(); }
    if (s.st !== 0) { const iWon = s.st === role; endOverlay(ctx, iWon ? 'GEWONNEN' : (s.st === 3 ? 'REMIS' : 'VERLOREN'), iWon ? COL.P1 : (s.st === 3 ? COL.TEXT : COL.P2), `${s.s1} : ${s.s2}`); }
  }

  // ---------------- DYNABLASTER ----------------
  function bomber(ctx, s, role) {
    const cs = s.cs, ox = s.ox, oy = s.oy, cols = s.cols, rows = s.rows;
    const now = Date.now();
    // Boden + Gitter
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const v = s.grid[r * cols + c], x = ox + c * cs, y = oy + r * cs;
      if (v === '1') {
        rect(ctx, x, y, cs, cs, '#484848');
        rect(ctx, x, y, cs, 3, '#6f6f6f');
        rect(ctx, x, y, 3, cs, '#5c5c5c');
      } else if (v === '2') {
        rect(ctx, x, y, cs, cs, '#7a5533');
        rect(ctx, x, y, cs, 3, '#9c7248');
        rect(ctx, x + 2, y + cs - 3, cs - 4, 2, '#5c3f26');
      } else {
        rect(ctx, x, y, cs, cs, (c + r) % 2 ? '#2a8a3e' : '#248038');
      }
    }
    // Power-ups
    s.pw.forEach(([c, r, t]) => {
      const x = ox + c * cs, y = oy + r * cs;
      rect(ctx, x + 3, y + 3, cs - 6, cs - 6, '#182028');
      const col = t === 'b' ? COL.HEAD : COL.SHOT2;
      strokeRect(ctx, x + 3, y + 3, cs - 6, cs - 6, col, 1);
      text(ctx, t === 'b' ? 'B' : 'F', x + cs / 2, y + cs / 2 + 4, col, 11, true);
    });
    // Bomben
    s.bombs.forEach(([c, r, t]) => {
      const x = ox + c * cs + cs / 2, y = oy + r * cs + cs / 2;
      const puls = 1 + 0.12 * Math.sin(now / 90);
      const rad = cs * 0.34 * puls;
      const danger = t < 14 && (now / 90 | 0) % 2 === 0;
      circle(ctx, x, y, rad, danger ? '#c33' : '#141414', true);
      circle(ctx, x, y, rad, '#000', false);
      rect(ctx, x - 1, y - rad - 2, 2, 3, '#8a6a2a');       // Zünder
      circle(ctx, x - rad * 0.35, y - rad * 0.35, 1.4, '#888', true);
    });
    // Flammen
    s.fl.forEach(([c, r]) => {
      const x = ox + c * cs, y = oy + r * cs;
      const f = 0.5 + 0.5 * Math.abs(Math.sin(now / 60));
      rect(ctx, x + 1, y + 1, cs - 2, cs - 2, '#ff7a00');
      const inset = 3 + 2 * f;
      rect(ctx, x + inset, y + inset, cs - 2 * inset, cs - 2 * inset, '#ffe000');
    });
    // Spieler
    for (let i = 0; i < s.p.length; i++) {
      const pl = s.p[i]; if (!pl.al) continue;
      const col = PC[i];
      circle(ctx, pl.x, pl.y, cs * 0.34, col, true);
      circle(ctx, pl.x, pl.y, cs * 0.34, '#0a140a', false);
      rect(ctx, pl.x - 3, pl.y - 2, 2, 3, '#fff');
      rect(ctx, pl.x + 1, pl.y - 2, 2, 3, '#fff');
    }
    // HUD oben
    // je Spieler Bomben/Reichweite (1 und 3 links, 2 und 4 rechts)
    const slots = [[4, 'left'], [236, 'right'], [62, 'left'], [178, 'right']];
    s.p.forEach((pl, i) => {
      const [x, al] = slots[i];
      text(ctx, `B${pl.b} F${pl.f}`, x, 13, pl.al ? PC[i] : COL.DIM, 10, true, al);
    });
    text(ctx, `${s.t}s`, 120, 13, COL.TEXT, 11, true);
    if (s.st !== 0) {
      const iWon = s.w === role;
      endOverlay(ctx, iWon ? 'GEWONNEN' : (s.w === 0 ? 'UNENTSCHIEDEN' : 'VERLOREN'),
        iWon ? COL.P1 : (s.w === 0 ? COL.TEXT : COL.P2), s.w && !iWon ? 'Sieger: P' + s.w : '');
    }
  }

  // ---------------- Jump'n'Bump ----------------
  // Originalgrafik (jnb_assets.js, aus den PCX-Dateien des Originals erzeugt):
  // Level 352x256 in 1:1-Pixeln, sichtbar 240x256 unter einer 24 px hohen
  // Kopfzeile; die Kamera folgt waagerecht dem eigenen Hasen. Sprites sitzen
  // mit ihrem Hotspot auf der Position; die Vordergrundebene (Maske) wird
  // zuletzt darueber gelegt, damit Hasen hinter Gras, Baeumen und unter der
  // Wasseroberflaeche verschwinden - wie put_pob() im Original.
  // Jump'n'Bump (c) 1998 Brainchild Design, GPL2+.
  const JW = 352, JVW = 240, JOY = 24;
  const JNB_RABBIT = [2, 3, 0, 1];    // Atlas-Hase je Spieler: grau, braun, weiss, hellbraun
  const JA = {};                      // geladene Bilder + Hotspot-Tabellen
  function jnbAssets() {
    if (JA.ready) return true;
    const src = window.JNB_ASSETS; if (!src) return false;
    if (!JA.img) {
      JA.img = {};
      for (const k of ['level', 'fg']) { JA.img[k] = new Image(); JA.img[k].src = src[k]; }
      for (const k of ['rabbit', 'objects', 'numbers']) { JA.img[k] = new Image(); JA.img[k].src = src[k].img; JA[k] = src[k].g; }
    }
    JA.ready = Object.values(JA.img).every(i => i.complete && i.naturalWidth);
    return JA.ready;
  }
  // Sprite n aus Atlas 'set' mit Hotspot an (x, y) zeichnen
  function pob(ctx, set, n, x, y) {
    const g = JA[set][n]; if (!g) return;
    ctx.drawImage(JA.img[set], g[0], g[1], g[2], g[3], x - g[4], y - g[5], g[2], g[3]);
  }
  // Hintergrund mit dauerhaften Blutflecken (eingebrannte Fleischsprites)
  function jnbWorld(stains) {
    const cv = document.createElement('canvas'); cv.width = JW; cv.height = 256;
    const c = cv.getContext('2d');
    c.drawImage(JA.img.level, 0, 0);
    for (let i = 0; i < stains.length; i += 3) pob(c, 'objects', stains[i + 2], stains[i], stains[i + 1]);
    return cv;
  }
  function jnb(ctx, s, role, R) {
    if (!jnbAssets()) { text(ctx, 'Lade Grafik ...', 120, 140, COL.DIM, 12, false); return; }
    const me = role - 1;
    const st = s.sx || [];
    if (!R.jWorld || R.jStains !== st.length) { R.jWorld = jnbWorld(st); R.jStains = st.length; }
    // Kamera ruhig dem eigenen Hasen nachfuehren (hoechstens 6 Pixel je Bild)
    const tx = Math.max(0, Math.min(JW - JVW, s.p[me][0] + 8 - JVW / 2));
    if (R.jCam == null) R.jCam = tx;
    R.jCam += Math.max(-6, Math.min(6, tx - R.jCam));
    const cam = Math.round(R.jCam);
    ctx.save();
    ctx.beginPath(); ctx.rect(0, JOY, JVW, 256); ctx.clip();
    ctx.translate(-cam, JOY);
    ctx.drawImage(R.jWorld, 0, 0);
    // Objekte (zuletzt erzeugte zuerst, wie draw_pobs) - Fell in der Farbe des Opfers
    const o = s.o;
    for (let i = o.length - 4; i >= 0; i -= 4) {
      let img = o[i + 3];
      if (o[i] === 5) { const v = (img - 44) >> 3, rot = (img - 44) & 7; img = 44 + JNB_RABBIT[v] * 8 + rot; }
      pob(ctx, 'objects', img, o[i + 1], o[i + 2]);
    }
    // Hasen (der eigene liegt oben); ausgeschiedene nicht
    const order = s.p.map((_, i) => i).filter(i => i !== me).concat([me]);
    for (const i of order) if (s.p[i][3]) pob(ctx, 'rabbit', s.p[i][2] + JNB_RABBIT[i] * 18, s.p[i][0], s.p[i][1]);
    ctx.fillStyle = '#000';                                   // Fliegen
    for (let i = 0; i < s.f.length; i += 2) ctx.fillRect(s.f[i], s.f[i + 1], 1, 1);
    ctx.drawImage(JA.img.fg, 0, 0);                           // Vordergrund
    ctx.restore();
    // Kopfzeile: Hasenkopf + Originalziffern je Spieler, mittig der Urheberhinweis
    rect(ctx, 0, 0, W, JOY, '#606060');
    const n = s.p.length;
    for (let i = 0; i < n; i++) {
      // zu zweit: links/rechts mit zwei Ziffern; zu mehreren: 1+3 links, 2+4 rechts
      const two = n === 2, bw = two ? 54 : 36;
      const bx = two ? (i === 0 ? 3 : W - 55) : [2, W - 38, 40, W - 76][i];
      if (i === me) strokeRect(ctx, bx - 2, 0, bw, 23, '#ffffff', 1);
      ctx.globalAlpha = s.p[i][3] ? 1 : 0.35;
      const g = JA.rabbit[JNB_RABBIT[i] * 18];
      ctx.drawImage(JA.img.rabbit, g[0], g[1], g[2], g[3], bx, 1 + ((22 - g[3]) >> 1), g[2], g[3]);
      const sc = Math.min(two ? 99 : 9, s.b[i]);
      if (two) { pob(ctx, 'numbers', (sc / 10) | 0, bx + 18, 1); pob(ctx, 'numbers', sc % 10, bx + 34, 1); }
      else pob(ctx, 'numbers', sc, bx + 17, 1);
      ctx.globalAlpha = 1;
    }
    if (n === 2) {
      text(ctx, "Jump'n'Bump \u00a9 1998", 120, 10, '#f0f0f0', 8, true);
      text(ctx, 'Brainchild Design, GPL2+', 120, 20, '#d8d8d8', 8, false);
    } else {
      text(ctx, "Jump'n'Bump", 120, 8, '#f0f0f0', 7, true);
      text(ctx, '\u00a9 1998 Brainchild', 120, 15, '#d8d8d8', 7, false);
      text(ctx, 'Design, GPL2+', 120, 22, '#d8d8d8', 7, false);
    }
    if (s.st) {
      const iWon = s.st === role;
      endOverlay(ctx, iWon ? 'GEWONNEN' : 'VERLOREN', iWon ? COL.P1 : COL.P2, s.b.join(' : '));
    }
  }

  const RENDERERS = { tron, pong, duel, tanks, wnr, c4, dots, bomber, jnb };

  window.drawGame = function (gid, s, role, ctx, R) {
    rect(ctx, 0, 0, W, H, COL.BG);
    ctx.imageSmoothingEnabled = false;
    const fn = RENDERERS[gid];
    if (fn) fn(ctx, s, role, R);
  };
})();
