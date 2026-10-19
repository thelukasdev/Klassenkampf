/* Klassenkampf Client: WebSocket, Screens, Lobby, Eingabe, Render-Loop. */
(function () {
  const $ = (id) => document.getElementById(id);
  const screens = ['login', 'nick', 'lobby', 'game'];
  function show(name) { screens.forEach(s => $(s).classList.toggle('active', s === name)); cur = name; }
  const canvas = $('c'), ctx = canvas.getContext('2d');

  let ws, cur = 'login', retryTimer, reconnectAllowed=true, lastReceived=Date.now(), transportLost=false, recovering=false, pauseState=null;
  let me = { code: null, nick: null, credits: 0 };
  let gamesInfo = [];
  let selectedGame = null;
  let lobbyState = null;
  let clientMode = 'choose';   // 'choose' | 'random' (vom Server)

  // Spielzustand
  let match = null;               // {gid, role, opp}
  let snap = null;
  const R = {};                   // persistenter Render-Zustand
  const HINTS = {
    tron: 'Steuerkreuz / Wischen: lenken\nNicht anecken!',
    pong: 'Schläger bewegen: Links / Rechts\noder Finger über das Feld ziehen',
    duel: 'Links/Rechts drehen, Hoch Schub, Runter Schild\nSchuss: Leertaste oder Schuss-Taste',
    tanks: 'Links/Rechts Winkel, Hoch/Runter Kraft\nWaffe wechseln: Taste C, Feuer: Leertaste',
    wnr: 'Richtung merken\nund antippen oder Steuerkreuz drücken',
    c4: 'Spalte antippen\noder Links/Rechts bewegen, dann Einwerfen',
    dots: 'Strich bewegen: Steuerkreuz\nRichtung drehen: Taste C, Zeichnen: Leertaste',
    bomber: 'Bewegen: Steuerkreuz\nBombe legen: A-Taste oder Leertaste',
    jnb: 'Links/Rechts laufen, Hoch oder Leertaste springen\nVon oben draufspringen = Punkt (bis 5)',
  };

  // ---------------- WebSocket ----------------
  function connectionNotice(text) { if($('connectionNotice').textContent!==text)$('connectionNotice').textContent=text;$('connectionNotice').hidden=!text; }
  function lost(socket) {
    if(socket!==ws||!reconnectAllowed)return;
    socket.onclose=null;socket.close();transportLost=true;recovering=true;connectionNotice('Verbindung unterbrochen · Wiederverbinden …');
    clearTimeout(retryTimer);retryTimer=setTimeout(connect,1000);
  }
  function connect() {
    clearTimeout(retryTimer);$('loginBtn').disabled=true;
    const socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/');ws=socket;lastReceived=Date.now();
    socket.onopen=()=>{if(ws!==socket)return;$('loginBtn').disabled=false;};
    socket.onmessage=event=>{if(ws!==socket)return;lastReceived=Date.now();handle(JSON.parse(event.data));};
    socket.onclose=()=>lost(socket);socket.onerror=()=>{};
  }
  function sendMsg(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }
  setInterval(()=>{if(ws&&ws.readyState===1){if(Date.now()-lastReceived>35000)lost(ws);else sendMsg({t:'ping'});}},10000);
  setInterval(()=>{
    if(transportLost)return;
    if(pauseState?.paused){
      const waiting=pauseState.waiting||[];
      connectionNotice(waiting.length?'Warte auf '+waiting.map(p=>p.nick+' · '+Math.max(0,Math.ceil((p.until-performance.now())/1000))+' s').join(' / '):'Partie pausiert');
    }else if(reconnectAllowed)connectionNotice('');
  },200);

  function handle(m) {
    switch (m.t) {
      case 'pong': break;
      case 'welcome': transportLost=false;connectionNotice('');gamesInfo = m.games; clientMode = m.mode || 'choose'; buildChips(); tryAutoLogin(); break;
      case 'login_ok':
        me.code = m.code;
        lsSet('cw_code', m.code);
        tabCode(m.code);
        const profile = savedProfile(m.code);
        $('nickInput').value = profile.nick || lsGet('cw_nick') || '';
        $('sessionLabel').textContent = m.session_name || '';
        if (m.mode) { clientMode = m.mode; buildChips(); }
        $('nickErr').textContent = '';
        if (!m.auto) { show('nick'); setTimeout(() => $('nickInput').focus(), 50); }
        break;
      case 'login_err':pauseState=null;connectionNotice('');me.code=null;me.nick=null;me.tok=null;$('loginErr').textContent = m.msg; lsDel('cw_code'); tabCode(null); show('login'); break;
      case 'nick_err':pauseState=null;connectionNotice('');me.nick=null;me.tok=null;$('nickErr').textContent = m.msg; lsDel('cw_tok'); show('nick'); break;
      case 'nick_ok':
        if(recovering){recovering=false;match=null;snap=null;pauseState=null;$('overlay').classList.remove('active');show('lobby');}
        me.nick = m.nick; me.tok=m.tok; lsSet('cw_nick', m.nick); lsSet('cw_tok', m.tok);
        lsSet('cw_profile_' + me.code, JSON.stringify({nick:m.nick,tok:m.tok}));
        break;
      case 'session_ended':
        reconnectAllowed=true;transportLost=false;pauseState=null;connectionNotice('');
        lsDel('cw_code'); tabCode(null); me.code = null; me.nick = null;me.tok=null;
        $('loginErr').textContent = m.msg; show('login');
        break;
      case 'lobby': lobbyState = m; buildChips(); if (m.mode) clientMode = m.mode; me.nick = m.you.nick; me.credits = m.you.credits; renderLobby(); if (cur !== 'game') show('lobby'); break;
      case 'challenged': toast(m.nick + ' fordert dich heraus' + (m.gname ? ': ' + m.gname : '')); break;
      case 'match_start': startMatch(m); break;
      case 'state': snap = m.s; if (snap.grid) R.tgrid = b64bits(snap.grid); pumpTouchDrivers(); break;
      case 'session_moved':lsSet('cw_profile_'+m.code,JSON.stringify({nick:me.nick,tok:lsGet('cw_tok')}));tabCode(m.code);location.reload();break;
      case 'match_pause':pauseState={paused:m.paused,waiting:(m.waiting||[]).map(p=>({...p,until:performance.now()+p.seconds*1000}))};keyMask=touchMask=canvasMask=inputMask=0;break;
      case 'match_cancelled':pauseState=null;connectionNotice('');match=null;snap=null;$('overlay').classList.remove('active');show('lobby');toast(m.msg);sendMsg({t:'lobby'});break;
      case 'match_end': endMatch(m); break;
      case 'info': toast(m.msg); break;
      case 'err': toast('⚠ ' + m.msg); break;
      case 'kicked':reconnectAllowed=false;clearTimeout(retryTimer);pauseState=null;transportLost=false;connectionNotice('');$('loginErr').textContent=m.msg+' · Bitte Seite neu laden.';show('login');toast(m.msg);break;
    }
  }

  // ---------------- Login / Nick ----------------
  // localStorage kann (privates Fenster, gesperrt) fehlen -> nie abstuerzen
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { } }
  function lsDel(k) { try { localStorage.removeItem(k); } catch (e) { } }
  function savedProfile(code) { try { return JSON.parse(lsGet('cw_profile_' + code) || '{}'); } catch { return {}; } }
  function tabCode(value) { try { if(value===null)sessionStorage.removeItem('cw_code');else if(value!==undefined)sessionStorage.setItem('cw_code',value);return sessionStorage.getItem('cw_code'); } catch { return null; } }
  // Nach Neuladen: mit gespeichertem Code + Name + Schluessel direkt zurueck
  function tryAutoLogin() {
    const urlCode=new URLSearchParams(location.search).get('code');
    if(urlCode){$('codeInput').value=urlCode;tabCode(urlCode);history.replaceState(null,'','/');sendMsg({t:'login',code:urlCode});return;}
    const c = me.code||tabCode(), profile = savedProfile(c);
    const n = me.nick||profile.nick||lsGet('cw_nick'), k = me.tok||profile.tok||lsGet('cw_tok');
    if (c && n && k) sendMsg({ t: 'login', code: c, nick: n, tok: k });
  }
  $('loginBtn').onclick = () => {
    const code = $('codeInput').value.trim();
    if (code) sendMsg({ t: 'login', code });
  };
  $('codeInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('loginBtn').click(); });
  $('nickBtn').onclick = () => {
    const n = $('nickInput').value.trim();
    const profile = savedProfile(me.code);
    if (n) sendMsg({ t: 'nick', nick: n, tok: profile.nick === n ? profile.tok : lsGet('cw_nick')===n?lsGet('cw_tok'):null });
  };
  $('nickInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('nickBtn').click(); });
  $('switchSession').onclick = () => {
    if (cur === 'game' && !confirm('Sitzung wechseln und die laufende Partie verlassen?')) return;
    if(cur==='game')sendMsg({t:'leave'});
    clearTimeout(retryTimer);reconnectAllowed=true;pauseState=null;transportLost=false;connectionNotice('');ws.onclose = null; ws.close();
    tabCode(null); lsDel('cw_code');
    me = {code:null,nick:null,credits:0}; match = null; snap = null;
    $('codeInput').value = ''; $('loginErr').textContent = '';
    show('login'); connect();
  };

  // ---------------- Lobby ----------------
  function buildChips() {
    const box = $('gameChips'); box.innerHTML = '';
    if(selectedGame&&lobbyState?.enabled_games&&!lobbyState.enabled_games.includes(selectedGame))selectedGame=null;
    gamesInfo.filter(g=>!lobbyState?.enabled_games||lobbyState.enabled_games.includes(g.id)).forEach(g => {
      const el = document.createElement('div'); el.className = 'chip'; el.dataset.gid = g.id;
      el.textContent = g.name + (g.max > 2 ? ' (2-' + g.max + ')' : '');
      el.onclick = () => { selectedGame = g.id; buildChips(); renderLobby(); };
      if (g.id === selectedGame) el.classList.add('sel');
      box.appendChild(el);
    });
  }
  function renderRanking() {
    const box = $('ranking'); if (!box) return;
    const ps = (lobbyState.players || []).slice().sort((a, b) =>
      b.credits - a.credits || (b.wl[0] - b.wl[1]) - (a.wl[0] - a.wl[1]) || (a.nick || '').localeCompare(b.nick || ''));
    let html = '<div class="rank-row head"><span class="rk">#</span><span class="nm">Spieler</span>'
      + '<span class="cr">Credits</span><span class="sn">S/N</span></div>';
    ps.forEach((p, i) => {
      const cls = p.credits > 0 ? 'pos' : p.credits < 0 ? 'neg' : 'zero';
      const dot = p.busy ? 'busy' : (p.online ? 'online' : '');
      html += `<div class="rank-row${p.you ? ' me' : ''}">`
        + `<span class="rk${i === 0 ? ' top' : ''}">${i + 1}</span>`
        + `<span class="nm"><span class="dot ${dot}"></span>${esc(p.nick || '—')}${p.you ? ' <span class="tag">(du)</span>' : ''}</span>`
        + `<span class="cr ${cls}">${p.credits >= 0 ? '+' : ''}${p.credits}</span>`
        + `<span class="sn">${p.wl[0]}/${p.wl[1]}</span></div>`;
    });
    box.innerHTML = html;
  }

  function renderLobby() {
    if (!lobbyState) return;
    $('meNick').textContent = me.nick || '–';
    $('meCred').textContent = (me.credits >= 0 ? '+' : '') + me.credits;
    const random = clientMode === 'random';
    $('gameSelect').classList.toggle('hidden', random);
    $('modeNote').classList.toggle('hidden', !random);
    $('challengeHead').textContent = lobbyState.paused?'Sitzung pausiert':random ? 'Gegner herausfordern' : '2 · Gegner herausfordern';
    buildChips();
    renderRanking();
    const watches=$('watchList');watches.replaceChildren();
    if(lobbyState.watch?.length){const title=document.createElement('h3');title.textContent='Zuschauen';watches.append(title);lobbyState.watch.forEach(m=>{const a=document.createElement('a');a.textContent=m.name+' · '+m.players.join(' / ')+' ↗';a.href=m.url;a.target='_blank';a.rel='noopener';a.className='watch-link';watches.append(a);});}

    // eingehende Herausforderungen
    const inc = $('incoming'); inc.innerHTML = '';
    lobbyState.incoming.forEach(c => {
      const d = document.createElement('div'); d.className = 'challenge-box';
      const others = c.others && c.others.length ? ` (mit ${c.others.map(esc).join(', ')})` : '';
      d.innerHTML = `<div class="txt"><b>${esc(c.nick)}</b> fordert dich heraus${c.gname ? ' · ' + esc(c.gname) : ''}${others}`
        + (c.acc ? '<br><span class="tag">angenommen - warte auf die anderen</span>' : '') + '</div>';
      if (!c.acc) d.appendChild(mkBtn('Annehmen', 'primary mini', () => sendMsg({ t: 'accept', from: c.from })));
      d.appendChild(mkBtn(c.acc ? 'Zurückziehen' : 'Ablehnen', 'mini', () => sendMsg({ t: 'decline', from: c.from })));
      inc.appendChild(d);
    });
    // ausgehende (bei Mehrspieler-Spielen bis zu 3 Gegner)
    const out = $('outgoing'); out.innerHTML = '';
    const o = lobbyState.outgoing;
    const targeted = new Set(o ? o.targets.map(t => t.pid) : []);
    if (o) {
      const d = document.createElement('div'); d.className = 'challenge-box';
      const list = o.targets.map(t => `<b>${esc(t.nick)}</b> ${t.acc ? '(dabei)' : '(wartet)'}`).join(', ');
      const more = o.max > o.targets.length ? `<br><span class="tag">weitere Gegner möglich: ${o.max - o.targets.length}</span>` : '';
      d.innerHTML = `<div class="txt">${o.gname ? esc(o.gname) + ': ' : ''}${list}${more}</div>`;
      const accN = o.targets.filter(t => t.acc).length;
      if (accN && accN < o.targets.length)
        d.appendChild(mkBtn('Starten (' + (accN + 1) + ' Spieler)', 'primary mini', () => sendMsg({ t: 'start_now' })));
      d.appendChild(mkBtn('Abbrechen', 'mini', () => sendMsg({ t: 'challenge_cancel' })));
      out.appendChild(d);
    }

    // Spielerliste
    const pl = $('players'); pl.innerHTML = '';
    lobbyState.players.forEach(p => {
      const row = document.createElement('div');
      row.className = 'prow' + (p.online ? ' on' : '') + (p.you ? ' me' : '');
      const st = p.busy ? 'busy' : (p.online ? 'online' : '');
      row.innerHTML = `<span class="dot ${st}"></span>
        <span class="pn">${esc(p.nick || '—')}</span>
        <span class="pcred">${p.credits >= 0 ? '+' : ''}${p.credits}</span>`;
      if (!p.you) {
        if (targeted.has(p.pid)) {
          const t = document.createElement('span'); t.className = 'tag'; t.textContent = 'gefordert'; row.appendChild(t);
        } else if (p.online && !p.busy && !lobbyState.paused) {
          row.appendChild(mkBtn('Fordern', 'mini', () => {
            if (clientMode !== 'random' && !selectedGame) { toast('Erst ein Spiel wählen'); return; }
            const msg = { t: 'challenge', target: p.pid };
            if (clientMode !== 'random') msg.game = selectedGame;
            sendMsg(msg);
          }));
        } else {
          const t = document.createElement('span'); t.className = 'tag';
          t.textContent = p.busy ? 'im Spiel' : lobbyState.paused&&p.online?'pausiert':'offline'; row.appendChild(t);
        }
      } else { const t = document.createElement('span'); t.className = 'tag'; t.textContent = 'du'; row.appendChild(t); }
      pl.appendChild(row);
    });
  }

  // ---------------- Match ----------------
  function startMatch(m) {
    pauseState=null;connectionNotice('');
    match = { gid: m.game, role: m.role, opp: m.opp };
    snap = null;
    for (const k in R) delete R[k];
    $('overlay').classList.remove('active');
    // alle Teilnehmer in ihren Spielerfarben, der eigene Name mit "(du)"
    const names = m.names || [m.opp];
    $('gVs').innerHTML = names.map((n, i) => `<b class="p${i + 1}">${esc(n)}${i + 1 === m.role ? ' (du)' : ''}</b>`)
      .join('<span class="vsx">vs</span>');
    $('gHint').textContent = HINTS[m.game] || '';
    keyMask = touchMask = canvasMask = inputMask = 0;
    applyPad(m.game);
    show('game');
  }
  function endMatch(m) {
    pauseState=null;connectionNotice('');
    const big = $('resBig');
    big.className = 'big ' + m.result;
    big.textContent = m.result === 'win' ? 'GEWONNEN' : m.result === 'loss' ? 'VERLOREN' : 'UNENTSCHIEDEN';
    const reasons = { opp_disconnected:'Gegner nicht rechtzeitig zurückgekehrt',you_disconnected:'Wiederverbindungsfrist abgelaufen',normal: '', opp_left: 'Gegner hat aufgegeben', you_left: 'Aufgegeben = verloren' };
    $('resReason').textContent = (m.delta!==undefined ? (m.delta>0?'+':'')+m.delta+' Credits' : 'Credits aktualisiert') +
      (reasons[m.reason] ? ' · ' + reasons[m.reason] : '');
    me.credits = m.credits;
    $('resCred').textContent = (m.credits >= 0 ? '+' : '') + m.credits;
    $('overlay').classList.add('active');
  }
  $('backBtn').onclick = () => { match = null; snap = null; $('overlay').classList.remove('active'); show('lobby'); sendMsg({ t: 'lobby' }); };
  $('leaveBtn').onclick = () => {
    if (match && !$('overlay').classList.contains('active')) {
      if (confirm('Aufgeben zählt als Niederlage. Wirklich aufgeben?')) sendMsg({ t: 'leave' });
    } else { match = null; snap = null; $('overlay').classList.remove('active'); show('lobby'); sendMsg({ t: 'lobby' }); }
  };

  // ---------------- Eingabe ----------------
  const L = 1, RG = 2, U = 4, DN = 8, A = 16, B = 32;
  let inputMask = 0, keyMask = 0, touchMask = 0, canvasMask = 0;
  function updateInput() {
    const m = keyMask | touchMask | canvasMask;
    if (m !== inputMask) { inputMask = m; if (match) sendMsg({ t: 'in', u: m }); }
  }
  // kurzer Tipp-Impuls (fuer direktes Antippen in rundenbasierten Spielen)
  function tap(bit) { touchMask |= bit; updateInput(); setTimeout(() => { touchMask &= ~bit; updateInput(); }, 60); }

  const KEYMAP = {
    ArrowLeft: L, KeyA: L, ArrowRight: RG, KeyD: RG, ArrowUp: U, KeyW: U, ArrowDown: DN, KeyS: DN,
    KeyJ: A, KeyZ: A, KeyC: A, Comma: A, KeyK: B, KeyL: B, KeyX: B, Space: B,
  };
  // base64 -> Uint8Array (bit-gepacktes Terrain-Gitter)
  function b64bits(str) { const bin = atob(str); const a = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i); return a; }
  const WSHORT = { 'Basic Shell': 'Basic', 'Inferno Blast': 'Inf', 'Shock Charge': 'Shock', 'Golden Dome': 'Dome' };
  window.addEventListener('keydown', e => {
    if (cur !== 'game') return;
    const b = KEYMAP[e.code]; if (b) { e.preventDefault(); keyMask |= b; updateInput(); }
  });
  window.addEventListener('keyup', e => {
    const b = KEYMAP[e.code]; if (b) { keyMask &= ~b; updateInput(); }
  });

  // Touch-Overlay-Tasten
  document.querySelectorAll('.tbtn[data-bit]').forEach(el => {
    const bit = +el.dataset.bit;
    const down = (e) => { e.preventDefault(); touchMask |= bit; el.classList.add('down'); updateInput(); };
    const up = (e) => { e.preventDefault(); touchMask &= ~bit; el.classList.remove('down'); updateInput(); };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointerleave', up);
    el.addEventListener('pointercancel', up);
  });

  // Touch-Gerät erkennen -> Overlay einblenden
  function markTouch() { document.body.classList.add('touch'); }
  if (window.matchMedia && window.matchMedia('(pointer:coarse)').matches) markTouch();
  window.addEventListener('touchstart', markTouch, { once: true, passive: true });

  // Welche Overlay-Tasten je Spiel sichtbar sind (+ Symbol für A/B)
  const PAD = {
    tron: { dirs: 'udlr' },
    pong: { dirs: 'lr' },
    duel: { dirs: 'udlr', a: 'Schuss' },
    tanks: { dirs: 'udlr', a: 'Waffe', b: 'Feuer' },
    wnr: { dirs: 'udlr' },
    c4: { dirs: 'lr', a: 'Werfen' },
    dots: { dirs: 'udlr', a: 'Dreh', b: 'Linie' },
    bomber: { dirs: 'udlr', a: 'Bombe' },
    jnb: { dirs: 'lr', a: 'Sprung' },
  };
  function applyPad(gid) {
    const cfg = PAD[gid] || { dirs: 'udlr', a: 'A', b: 'B' };
    const set = (sel, on, label) => { const el = document.querySelector(sel); if (!el) return; el.classList.toggle('hidden', !on); if (on && label) el.textContent = label; };
    set('.d-up', cfg.dirs.includes('u')); set('.d-down', cfg.dirs.includes('d'));
    set('.d-left', cfg.dirs.includes('l')); set('.d-right', cfg.dirs.includes('r'));
    set('#btnA', !!cfg.a, cfg.a); set('#btnB', !!cfg.b, cfg.b);
    // Tanks: A-Taste ist der Waffenwechsel -> kleinerer Text, zeigt aktuelle Waffe
    const bA = document.querySelector('#btnA');
    if (bA) bA.classList.toggle('wsmall', gid === 'tanks');
  }

  // Direkte Bedienung auf dem Spielbild (Pong ziehen, W'n'R/Vier-gewinnt tippen)
  let canvasDown = false;
  function logical(e) {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width * 240, (e.clientY - r.top) / r.height * 280];
  }
  function pongFollow(lx) {
    if (!snap) return;
    const px = (match.role === 1 ? snap.p1x : snap.p2x) + snap.pw / 2;
    canvasMask = lx < px - 3 ? L : lx > px + 3 ? RG : 0;
    updateInput();
  }
  function canvasPointer(e, moving) {
    if (!match || !snap) return;
    const [lx, ly] = logical(e);
    if (match.gid === 'pong') { pongFollow(lx); return; }
    if (moving) return;
    if (match.gid === 'wnr') {
      const inR = (x, y, w, h) => lx >= x && lx <= x + w && ly >= y && ly <= y + h;
      if (inR(83, 29, 74, 66)) tap(U);
      else if (inR(83, 185, 74, 66)) tap(DN);
      else if (inR(5, 107, 74, 66)) tap(L);
      else if (inR(161, 107, 74, 66)) tap(RG);
    } else if (match.gid === 'c4') {
      R.c4target = Math.max(0, Math.min(6, Math.floor((lx - 13) / 30)));
    }
  }
  canvas.addEventListener('pointerdown', e => { e.preventDefault(); canvasDown = true; canvasPointer(e, false); });
  canvas.addEventListener('pointermove', e => { if (canvasDown) canvasPointer(e, true); });
  const canvasRelease = () => { canvasDown = false; if (canvasMask) { canvasMask = 0; updateInput(); } };
  canvas.addEventListener('pointerup', canvasRelease);
  canvas.addEventListener('pointerleave', canvasRelease);
  canvas.addEventListener('pointercancel', canvasRelease);

  // garantierte Einzelflanke (fuer den automatischen Cursor-Treiber)
  function driverTap(bit) { sendMsg({ t: 'in', u: bit }); sendMsg({ t: 'in', u: 0 }); inputMask = 0; }
  // Vier-gewinnt: Cursor Schritt für Schritt zur angetippten Spalte, dann werfen
  function pumpTouchDrivers() {
    if (!match || !snap) return;
    // Tanks: Waffen-Button mit aktueller Waffe + Munition beschriften
    if (match.gid === 'tanks' && snap.wn) {
      const me = match.role - 1;
      const name = WSHORT[snap.wn[me]] || snap.wn[me];
      const ammo = snap.ammo[me];
      const bA = $('btnA'); if (bA) bA.textContent = ammo >= 0 ? name + ' ' + ammo : name;
    }
    if (match.gid === 'c4' && R.c4target != null && snap.st === 0) {
      if (snap.pl !== match.role) return;                 // nicht am Zug -> warten
      if (snap.board[R.c4target][0] !== 0) { R.c4target = null; return; } // Spalte voll
      if (snap.cur === R.c4target) { driverTap(A); R.c4target = null; }
      else driverTap(snap.cur < R.c4target ? RG : L);
    }
  }

  // ---------------- Render-Loop ----------------
  // Nativ in 240x280 zeichnen; das Canvas-Element wird per CSS (pixelated)
  // hochskaliert -> knackige, harte Pixel statt weicher Kantenglaettung.
  ctx.imageSmoothingEnabled = false;
  function fit() {
    const wrap = canvas.parentElement;
    const s = Math.max(1, Math.min(wrap.clientWidth / 240, wrap.clientHeight / 280));
    const w = Math.floor(240 * s), h = Math.floor(280 * s);
    if (canvas.style.width !== w + 'px') {
      canvas.style.width = w + 'px';
      canvas.style.height = h + 'px';
    }
  }
  function loop() {
    if (cur === 'game' && match && snap) {
      fit();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      try { window.drawGame(match.gid, snap, match.role, ctx, R); } catch (e) { /* ignore frame */ }
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  // ---------------- Helpers ----------------
  function mkBtn(txt, cls, fn) { const b = document.createElement('button'); b.className = 'btn ' + cls; b.textContent = txt; b.onclick = fn; return b; }
  function esc(s) { return (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  let toastTimer;
  function toast(msg) { const t = $('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2600); }

  connect();
})();
