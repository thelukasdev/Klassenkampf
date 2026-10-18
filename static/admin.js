(() => {
  'use strict';
  const playerPanel=location.pathname.startsWith('/account');
  const $ = id => document.getElementById(id);
  let user = null, snapshot = null, busy = false, toastTimer, selectedSession = '', accessMode = 'add-admin', loginCsrf = '';
  const titles = {
    sessions: ['Spielsitzungen', 'Spielsitzungen', 'Starte parallele Sitzungen mit eigenem Code und eigener Rangliste.'],
    overview: ['Übersicht', 'Übersicht', 'Alles, was du für die nächste Runde brauchst.'],
    players: ['Spieler', 'Spieler', 'Spieler begleiten, Credits einsehen und fair moderieren.'],
    accounts:['Spielerkonten','Spielerkonten',''],
    games:['Spielsteuerung','Spielsteuerung','Freigaben, Regeln und Partien.'],
    results:['Ergebnisse','Ergebnisse','Ranglisten und abgeschlossene Partien.'],
    system:['Serverstatus','Serverstatus','Verbindung und Auslastung.'],
    saves: ['Sicherungen', 'Sicherungen', 'Bewahre eure Fortschritte auf und lade sie bei Bedarf wieder.'],
    access: ['Zugriffsverwaltung', 'Zugriffsverwaltung', 'Bestimme, wer die Arena mit dir verwalten darf.'],
    activity: ['Aktivitäten', 'Aktivitäten', 'Sieh nach, wer zuletzt etwas verwaltet hat.']
  };
  const labels = {'player-permissions':'Spielerrechte geändert','delete-player-account':'Spielerkonto gelöscht','revoke-player-logins':'Spielerkonto abgemeldet','player-password-reset':'Spielerpasswort zurückgesetzt','auto-end-session':'Leere Sitzung beendet','player-login':'Spielerkonto angemeldet',login:'Anmeldung',kick:'Spieler getrennt',ban:'Spieler gesperrt',unban:'Spieler entsperrt',
    'reset-credits':'Credits zurückgesetzt',mode:'Spielmodus geändert',save:'Spielstand gesichert',load:'Spielstand geladen',
    'add-admin':'Zugriff freigegeben','remove-admin':'Zugriff entfernt','reset-admin-password':'Passwort geändert',
    rules:'Regeln geändert','pause-match':'Partie pausiert / fortgesetzt','spectators':'Zuschauerfreigabe geändert','end-match':'Partie ohne Wertung beendet','move-player':'Spieler zugeordnet','remove-player':'Spieler entfernt',role:'Rolle geändert','assign-session':'Sitzungszugriff geändert',
    'create-session':'Spielsitzung gestartet','end-session':'Spielsitzung beendet'};
  function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
  function toast(text, error=false) { clearTimeout(toastTimer); $('toast').textContent=text; $('toast').className='toast'+(error?' error':''); $('toast').hidden=false; toastTimer=setTimeout(()=>$('toast').hidden=true,5500); }
  async function api(path, data) {
    if(playerPanel)path=path.replace('/api/admin/','/api/player/').replace('/auth/logout','/auth/player/logout');
    const options={credentials:'same-origin',headers:{}};
    if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':user?.csrf||''};options.body=JSON.stringify(data);}
    const response=await fetch(path,options);
    const body=await response.json();
    if(!response.ok){if(response.status===401) location.assign(playerPanel?'/login':'/admin');throw new Error(body.error||'Die Anfrage ist fehlgeschlagen.');}
    return body;
  }
  function confirmAction(title,text) {
    return new Promise(resolve=>{const dialog=$('confirmDialog');$('confirmTitle').textContent=title;$('confirmText').textContent=text;dialog.returnValue='';dialog.addEventListener('close',()=>resolve(dialog.returnValue==='ok'),{once:true});dialog.showModal();});
  }
  async function action(name,value,confirmation,sessionId,extra={}) {
    if(busy)return;
    if(confirmation&&$('confirmDialog').open)return;
    if(confirmation&&!await confirmAction(confirmation[0],confirmation[1]))return;
    busy=true;
    document.querySelectorAll('button[type=submit]').forEach(b=>b.disabled=true);
    try{const result=await api('/api/admin/action',{action:name,value,session:sessionId||selectedSession,...extra});if(name==='create-session'){selectedSession=result.result.id;toast('Spielsitzung gestartet. Code: '+result.result.code);}else toast(typeof result.result==='string'?result.result:'Änderung gespeichert.');await refresh();if(activeTab==='accounts')await loadAccounts();return true;}
    catch(error){toast(error.message,true);return false;}
    finally{busy=false;document.querySelectorAll('button[type=submit]').forEach(b=>b.disabled=false);document.querySelector('#saveForm button[type=submit]').disabled=!snapshot?.session_active;}
  }
  function empty(parent,title,text){const box=el('div',undefined,'empty');box.append(el('strong',title),el('p',text));parent.append(box);}
  function button(label,name,value,confirmation){const b=el('button',label);b.type='button';b.dataset.action=name;b.addEventListener('click',()=>action(name,value,confirmation));return b;}
  function playersTable(parent,players,controls){
    parent.replaceChildren();
    if(!players.length){empty(parent,'Hier ist noch Platz für die erste Runde.','Sobald sich Spieler anmelden, erscheinen ihre Profile hier.');return;}
    const wrap=el('div',undefined,'table-wrap'),table=el('table'),head=el('thead'),tr=el('tr');
    ['Spieler','Status','Credits','Siege / Niederlagen',...(controls?['Aktionen']:[])].forEach(t=>tr.append(el('th',t)));head.append(tr);table.append(head);const body=el('tbody');
    players.forEach(p=>{const row=el('tr'),name=el('td'),cell=el('div',undefined,'player-cell');cell.append(el('span',p.nick.slice(0,1).toUpperCase(),'mini-avatar'),el('span',p.nick,'player-name'));name.append(cell);row.append(name);const status=el('td');status.append(el('span',p.banned?'Gesperrt':p.busy?'Im Spiel':p.online?'Online':'Offline','status '+(p.banned?'banned':p.online?'online':'')));row.append(status,el('td',String(p.credits)),el('td',`${p.wl[0]} / ${p.wl[1]}`));
      if(controls){const td=el('td'),actions=el('div',undefined,'actions');if(p.online)actions.append(button('Trennen','kick',p.key,['Spieler trennen?',`${p.nick} wird vom Server getrennt. Eine laufende Partie wird beendet.`]));actions.append(button(p.banned?'Entsperren':'Sperren',p.banned?'unban':'ban',p.key,[p.banned?'Spieler entsperren?':'Spieler sperren?',`${p.nick}: Zugangsstatus ändern?`]));actions.append(button('Credits zurücksetzen','reset-credits',p.key,['Credits zurücksetzen?',`Credits und Siege/Niederlagen von ${p.nick} werden auf null gesetzt.`]));const remove=button('Entfernen','remove-player',p.key,['Profil entfernen?',p.nick+': Profil und Credits löschen? Historische Ergebnisse bleiben erhalten.']);remove.disabled=p.busy;actions.append(remove);
        const targets=(snapshot.sessions||[]).filter(s=>s.active&&s.id!==selectedSession);
        if(targets.length){const move=el('select',undefined,'row-select');move.setAttribute('aria-label',p.nick+' zuordnen');const first=el('option','Sitzung zuordnen …');first.value='';move.append(first);targets.forEach(s=>{const o=el('option',s.name);o.value=s.id;move.append(o);});move.disabled=p.busy;move.onchange=()=>{if(move.value)action('move-player',p.key,['Spieler zuordnen?',p.nick+' mit Credits in diese Sitzung verschieben?'],null,{target:move.value});};actions.append(move);}td.append(actions);row.append(td);}body.append(row);});table.append(body);wrap.append(table);parent.append(wrap);
  }
  function render(){
    const {status,saves,admins,audit,code}=snapshot;
    renderSessions();renderControls();
    $('statOnline').textContent=status.players.filter(p=>p.online).length;$('statMatches').textContent=status.matches;$('statPlayers').textContent=status.players.length;$('statSaves').textContent=saves.length;$('playerCode').textContent=code||'Kein aktiver Code';$('copyCode').disabled=!code;
    document.querySelectorAll('[name=mode]').forEach(input=>{input.checked=input.value===status.mode;input.disabled=!snapshot.session_active;});
    $('saveName').disabled=!snapshot.session_active;
    document.querySelector('#saveForm button[type=submit]').disabled=!snapshot.session_active;
    playersTable($('recentPlayers'),[...status.players].sort((a,b)=>Number(b.online)-Number(a.online)).slice(0,5),false);
    filterPlayers();applyPlayerPermissions();$('updated').textContent='Aktualisiert um '+new Date().toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
    const saveList=$('savesList');saveList.replaceChildren();if(!saves.length)empty(saveList,'Noch keine Sicherung.','Speichere euren ersten Spielstand über das Formular.');saves.forEach(name=>{const row=el('div',undefined,'list-row');row.append(el('strong',name));const b=button('Laden','load',name,['Spielstand laden?',`„${name}“ ersetzt den aktuellen Stand dieser Sitzung. Ihre verbundenen Spieler werden getrennt.`]);b.className='button secondary';b.disabled=!snapshot.session_active;row.append(b);saveList.append(row);});
    const access=$('adminsList');access.replaceChildren();admins.forEach(a=>{const row=el('div',undefined,'list-row'),info=el('div');info.append(el('strong',a.email),el('small',`${a.role==='owner'?'Inhaber':a.role==='guide'?'Spielleiter':'Administrator'} · ${a.activated?'Passwort eingerichtet':'Passwort ausstehend'}`));row.append(info);{const reset=el('button','Passwort ändern','button secondary');reset.type='button';reset.onclick=()=>{$('adminEmail').value=a.email;accessMode='reset-admin-password';document.querySelector('#accessForm button[type=submit]').textContent='Passwort speichern';$('adminPassword').focus();};row.append(reset);}if(a.role!=='owner'){
      const role=el('select',undefined,'row-select');role.setAttribute('aria-label','Rolle für '+a.email);['admin','guide'].forEach(r=>{const o=el('option',r==='guide'?'Spielleiter':'Administrator');o.value=r;role.append(o);});role.value=a.role;role.onchange=()=>action('role',a.email,null,null,{role:role.value});row.append(role);
      if(a.role==='guide'){const assigned=el('div',undefined,'assignment-list');(snapshot.sessions||[]).forEach(s=>{const label=el('label'),check=el('input');check.type='checkbox';check.checked=(snapshot.assignments||[]).some(x=>x.email===a.email&&x.room_id===s.id);check.onchange=()=>action('assign-session',a.email,null,s.id,{remove:!check.checked});label.append(check,document.createTextNode(s.name));assigned.append(label);});info.append(assigned);}
      const b=button('Entfernen','remove-admin',a.email,['Zugriff entfernen?',`${a.email} verliert sofort den Verwaltungszugriff. Bestehende Sitzungen werden beendet.`]);b.className='button danger';row.append(b);}access.append(row);});
    const activity=$('activityList');activity.replaceChildren();if(!audit.length)empty(activity,'Hier bleibt alles nachvollziehbar.','Verwaltungsaktionen werden nach ihrer Ausführung angezeigt.');audit.forEach(a=>{const row=el('div',undefined,'list-row'),info=el('div');info.append(el('strong',labels[a.action]||a.action),el('small',(a.email.startsWith('player:')?a.email.slice(7):a.email)+(a.detail?' · '+a.detail:'')));row.append(info,el('small',new Date(a.time*1000).toLocaleString('de-DE',{dateStyle:'short',timeStyle:'short'})));activity.append(row);});
  }
  async function copyText(value){try{await navigator.clipboard.writeText(value);toast('Code kopiert.');}catch{toast('Code bitte manuell kopieren.',true);}}
  async function showJoin(id,name){try{const data=await api('/api/admin/join?session='+encodeURIComponent(id));$('qrTitle').textContent=name;$('joinQr').src=data.qr;$('joinUrl').href=data.url;$('qrDialog').showModal();}catch(e){toast(e.message,true);}}
  function renderControls(){
    const sessions=snapshot.sessions||[],server=snapshot.server||{},rules=snapshot.rules||{};
    $('globalStats').replaceChildren(...[`${sessions.filter(s=>s.active).length} aktive Sitzungen`,`${sessions.reduce((a,s)=>a+s.online,0)} Spieler online`,`${sessions.reduce((a,s)=>a+s.matches,0)} laufende Partien`].map(t=>el('span',t)));
    if(!document.querySelector('#rulesForm:focus-within')){
      const enabled=$('enabledGames');enabled.replaceChildren();(server.games||[]).forEach(g=>{const label=el('label'),check=el('input');check.type='checkbox';check.value=g.id;check.name='gameEnabled';check.checked=(rules.enabled||[]).includes(g.id);label.append(check,document.createTextNode(g.name));enabled.append(label);});
      $('ruleSpeed').value=rules.speed||1;$('ruleWin').value=rules.credits_win??1;$('ruleLoss').value=rules.credits_loss??-1;$('ruleDraw').value=rules.credits_draw??0;
    }
    $('rulesForm').querySelectorAll('input,select,button').forEach(x=>x.disabled=!snapshot.session_active);
    $('pauseSession').disabled=!snapshot.session_active;$('pauseSession').textContent=rules.paused?'Sitzung fortsetzen':'Sitzung pausieren';
    const matches=$('matchesList');matches.replaceChildren();if(!snapshot.matches_detail?.length)empty(matches,'Keine laufenden Partien.','');
    (snapshot.matches_detail||[]).forEach(m=>{const row=el('div',undefined,'list-row'),info=el('div');info.append(el('strong',m.name+' · '+m.players.join(' / ')),el('small',`${m.paused?'Pausiert':'Läuft'} · ${m.duration} s · ${m.recording?'Aufnahme':m.replay_partial?'Teilaufnahme':'Keine Aufnahme'}`));const actions=el('div',undefined,'actions');actions.append(button(m.paused?'Fortsetzen':'Pausieren','pause-match',m.id),button('Ohne Wertung beenden','end-match',m.id,['Partie beenden?','Die Partie wird ohne zusätzliche Wertung geschlossen.']));const share=button(m.watch_url?'Freigabe beenden':'Zuschauer freigeben','spectators',m.id);share.disabled=m.spectators_allowed===false;share.title=share.disabled?'Verdeckte Spielansichten bleiben privat.':'';actions.append(share);if(m.watch_url){const link=el('a','Zuschauen ↗','button secondary');link.href=m.watch_url;link.target='_blank';link.rel='noopener';actions.append(link);const copy=el('button','Link kopieren');copy.onclick=()=>copyText(location.origin+m.watch_url);actions.append(copy);}row.append(info,actions);matches.append(row);});
    playersTable($('rankingTable'),[...snapshot.status.players].sort((a,b)=>b.credits-a.credits||b.wl[0]-a.wl[0]),false);
    const history=$('historyList');history.replaceChildren();if(!snapshot.history?.length)empty(history,'Noch keine abgeschlossenen Partien.','Neue Ergebnisse erscheinen hier.');
    [...(snapshot.history||[])].reverse().slice(0,100).forEach(m=>{const row=el('div',undefined,'list-row'),info=el('div');const winners=Object.entries(m.outcomes).filter(([,v])=>v==='win').map(([k])=>k);info.append(el('strong',m.name+' · '+m.players.join(' / ')),el('small',m.reason==='admin'?'Ohne Wertung beendet':m.reason==='worker_error'?'Technisch abgebrochen':winners.length?'Sieg: '+winners.join(', '):'Unentschieden'));row.append(info,el('small',new Date(m.time*1000).toLocaleString('de-DE')+' · '+m.duration+' s'));history.append(row);});
    const replayList=$('replaysList');replayList.replaceChildren();if(!snapshot.replays?.length)empty(replayList,'Noch keine Replays.','');(snapshot.replays||[]).forEach(r=>{const row=el('div',undefined,'list-row'),info=el('div');info.append(el('strong',r.name+' · '+r.players.join(' / ')),el('small',new Date(r.started*1000).toLocaleString('de-DE')+' · '+Math.round(r.duration)+' s'+(r.truncated?' · Teilaufnahme':'')));const play=el('button','Replay öffnen','button secondary');play.disabled=!r.frames;play.onclick=()=>window.openReplay(selectedSession,r.id);row.append(info,play);replayList.append(row);});
    const system=$('systemStatus');system.replaceChildren();const grid=el('div',undefined,'system-grid');
    const metrics=[['Laufzeit',Math.floor((server.uptime||0)/60)+' min'],['Verbindungen',server.connections??'–'],['RAM',server.memory?.used_mb!==undefined?`${server.memory.used_mb} / ${server.memory.limit_mb||'∞'} MB`:'Nicht verfügbar'],['Freier Speicher',server.disk_free_mb!==undefined?server.disk_free_mb+' MB':'–'],['Host-Auslastung (1 min)',server.load?.[0]?.toFixed(2)||'–'],['Prozessfehler seit Start',server.worker_errors??0]];
    metrics.forEach(([label,value])=>{const box=el('div');box.append(el('small',label),el('strong',String(value)));grid.append(box);});system.append(grid,el('p',server.architecture||''));
    const workers=$('workersList');workers.replaceChildren();if(!server.workers?.length)empty(workers,'Keine Spielprozesse aktiv.','Prozesse starten bei der ersten Partie und enden nach der letzten.');(server.workers||[]).forEach(w=>{const row=el('div',undefined,'list-row');row.append(el('strong',w.session),el('small',`PID ${w.pid} · ${w.matches} Partien`));workers.append(row);});
  }
  function csvDownload(name,rows){
    const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';
    const blob=new Blob(['\ufeff'+rows.map(r=>r.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=name+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  $('exportRanking').onclick=()=>csvDownload('rangliste',[['Spieler','Credits','Siege','Niederlagen'],...[...snapshot.status.players].sort((a,b)=>b.credits-a.credits).map(p=>[p.nick,p.credits,...p.wl])]);
  $('exportHistory').onclick=()=>csvDownload('partien',[['Zeit','Spiel','Spieler','Ergebnisse','Grund','Dauer (s)'],...(snapshot.history||[]).map(m=>[new Date(m.time*1000).toISOString(),m.name,m.players.join(' / '),Object.entries(m.outcomes).map(([k,v])=>k+': '+v).join(' / '),m.reason,m.duration])]);
  $('rulesForm').onsubmit=async event=>{event.preventDefault();document.activeElement.blur();await action('rules','',null,null,{rules:{enabled:[...document.querySelectorAll('[name=gameEnabled]:checked')].map(x=>x.value),speed:Number($('ruleSpeed').value),credits_win:Number($('ruleWin').value),credits_loss:Number($('ruleLoss').value),credits_draw:Number($('ruleDraw').value)}});};
  $('pauseSession').onclick=()=>action('rules','',null,null,{rules:{paused:!snapshot.rules.paused}});
  $('showQr').onclick=()=>{if(selectedSession)showJoin(selectedSession,snapshot.session_name);};
  function filterPlayers(){if(!snapshot)return;const search=$('playerSearch').value.toLocaleLowerCase('de');playersTable($('playersTable'),snapshot.status.players.filter(p=>p.nick.toLocaleLowerCase('de').includes(search)),snapshot.session_active&&(!playerPanel||snapshot.permissions?.moderate_players));}
  function renderSessions(){
    selectedSession=snapshot.selected_session||'';
    const select=$('sessionSelect');select.replaceChildren();
    if(!snapshot.sessions?.length){select.append(el('option','Noch keine Spielsitzung'));select.disabled=true;}else{select.disabled=false;snapshot.sessions.forEach(s=>{const option=el('option',s.name+(s.active?' · aktiv':' · beendet'));option.value=s.id;select.append(option);});select.value=selectedSession;}
    $('sessionState').textContent=snapshot.session_name?(snapshot.session_active?'Aktiv · '+snapshot.session_name:'Beendet · '+snapshot.session_name):'Neue Sitzung unter Spielsitzungen starten';
    const list=$('sessionsList');list.replaceChildren();
    if(!snapshot.sessions?.length)empty(list,'Die nächste Runde wartet.','Starte deine erste Spielsitzung mit dem Formular.');
    (snapshot.sessions||[]).forEach(s=>{const row=el('div',undefined,'session-card');const info=el('div');info.append(el('strong',s.name),el('small',`${s.active?'Aktiv':'Beendet'} · ${s.online} online · ${s.players} Spieler`));if(s.code)info.append(el('code',s.code));if(s.public_status_id){const statusLink=el('a','Status: #'+s.public_status_id.slice(8,14).toUpperCase()+' ↗','session-status-link');statusLink.href='/status?component='+encodeURIComponent(s.public_status_id);statusLink.target='_blank';statusLink.rel='noopener';info.append(statusLink);}row.append(info);const buttons=el('div',undefined,'actions');if(s.code){const copy=el('button','Code kopieren');copy.onclick=()=>copyText(s.code);const qr=el('button','QR-Code');qr.onclick=()=>showJoin(s.id,s.name);buttons.append(copy,qr);}const open=el('button','Auswählen');open.addEventListener('click',async()=>{selectedSession=s.id;await refresh();tab('overview');});buttons.append(open);if(s.active){const end=el('button','Beenden');end.dataset.action='ban';end.addEventListener('click',()=>action('end-session','',['Spielsitzung beenden?',`„${s.name}“ wird beendet. Alle Teilnehmer dieser Sitzung werden getrennt. Ihr Code wird ungültig; die Ergebnisse bleiben erhalten.`],s.id));buttons.append(end);}row.append(buttons);list.append(row);});
  }
  async function refresh(){try{snapshot=await api('/api/admin/overview'+(playerPanel?'?manage=1'+(selectedSession?'&session='+encodeURIComponent(selectedSession):''):(selectedSession?'?session='+encodeURIComponent(selectedSession):'')));render();document.querySelector('.service-badge').textContent='● Server verbunden';}catch(error){if(playerPanel){location.replace('/account');return;}toast(error.message,true);document.querySelector('.service-badge').textContent='Verbindung unterbrochen';}}
  const rightLabels={keep_empty:'Leere Sitzungen offen halten',moderate_players:'Spieler moderieren (inkl. Credits)',manage_games:'Spielregeln und Partien steuern',view_results:'Ergebnisse ansehen und exportieren',view_replays:'Replays ansehen',manage_saves:'Sicherungen erstellen und laden'};
  let rightsTarget=null;
  function editPlayerRights(account){rightsTarget=account;$('playerRightsError').hidden=true;$('playerAdminAccess').hidden=user.role!=='owner';$('playerAdminAccessNote').hidden=user.role!=='owner';$('playerRightsEmail').textContent=account.email;$('rightMaxSessions').value=account.permissions.max_sessions;const box=$('playerRightOptions');box.replaceChildren();for(const [key,label] of Object.entries(rightLabels)){const row=el('label'),check=el('input');check.type='checkbox';check.name='playerRight';check.value=key;check.checked=account.permissions[key];row.append(check,document.createTextNode(label));box.append(row);}$('playerRightsDialog').showModal();}
  $('playerAdminAccess').onclick=()=>{if(!rightsTarget||user.role!=='owner')return;const account=(snapshot.admins||[]).find(a=>a.email===rightsTarget.email);$('playerRightsDialog').close();tab('access');$('adminEmail').value=rightsTarget.email;$('adminPassword').value='';if(account){accessMode='reset-admin-password';document.querySelector('#accessForm button[type=submit]').textContent='Passwort speichern';$('adminRole').value=account.role==='guide'?'guide':'admin';toast('Verwaltungszugang besteht bereits. Rolle und Zugriff hier bearbeiten.');}else{accessMode='add-admin';$('adminRole').value='admin';document.querySelector('#accessForm button[type=submit]').textContent='Person freischalten';}$('adminPassword').focus();};
  $('playerRightsCancel').onclick=()=>$('playerRightsDialog').close();
  $('playerRightsForm').onsubmit=async e=>{e.preventDefault();if(!rightsTarget)return;const permissions={max_sessions:Number($('rightMaxSessions').value)};document.querySelectorAll('[name=playerRight]').forEach(c=>permissions[c.value]=c.checked);if(await action('player-permissions',rightsTarget.email,null,null,{permissions}))$('playerRightsDialog').close();else{$('playerRightsError').textContent='Rechte konnten nicht gespeichert werden. Bitte erneut versuchen.';$('playerRightsError').hidden=false;}};
  function playerTabAllowed(name){const p=snapshot?.permissions||user?.permissions||{};return ['sessions','overview'].includes(name)||name==='players'&&p.moderate_players||name==='games'&&p.manage_games||name==='results'&&(p.view_results||p.view_replays)||name==='saves'&&p.manage_saves;}
  function applyPlayerPermissions(){if(!playerPanel)return;const p=snapshot.permissions||{};for(const node of document.querySelectorAll('[data-tab]'))node.hidden=!playerTabAllowed(node.dataset.tab);$('recentPlayers').closest('article').hidden=!p.moderate_players&&!p.view_results;document.querySelector('[name=mode]').closest('article').hidden=!p.manage_games;$('rankingTable').closest('article').hidden=!p.view_results;$('historyList').closest('article').hidden=!p.view_results;$('replaysList').closest('article').hidden=!p.view_replays;$('statSaves').closest('article').hidden=!p.manage_saves;document.querySelectorAll('[data-goto=players]').forEach(n=>n.hidden=!p.moderate_players);$('sessionForm').hidden=snapshot.sessions.filter(s=>s.active).length>=p.max_sessions;if(activeTab&&!playerTabAllowed(activeTab))tab('sessions');}
  let activeTab='overview' ,accountAfter='',accountNext=null,accountPages=[],accountRequest=0,accountTimer;
  async function loadAccounts(){
    const generation=++accountRequest;$('accountsError').hidden=true;
    try{const q=new URLSearchParams({q:$('accountSearch').value,after:accountAfter});const result=await api('/api/admin/accounts?'+q);if(generation!==accountRequest)return;accountNext=result.next;const list=$('accountsList');list.replaceChildren();if(!result.accounts.length)list.append(el('p','Keine Spielerkonten gefunden.'));for(const a of result.accounts){const row=el('div',undefined,'list-row'),info=el('div');info.append(el('strong',a.email),el('small','Erstellt: '+new Date(a.created*1000).toLocaleDateString('de-DE')+' · '+a.logins+' aktive Anmeldungen'));const controls=el('div',undefined,'actions');const rights=el('button','Rechte bearbeiten','button secondary');rights.type='button';rights.onclick=()=>editPlayerRights(a);controls.append(rights);controls.append(button('Abmelden','revoke-player-logins',a.email,['Spielerkonto abmelden?',a.email+': Alle Anmeldungen und offenen Bestätigungscodes widerrufen?']),button('Konto löschen','delete-player-account',a.email,['Spielerkonto löschen?',a.email+': Konto dauerhaft löschen und eigene Spielsitzungen beenden? Historische Spielergebnisse bleiben erhalten.']));controls.lastChild.className='button danger';row.append(info,controls);list.append(row);}$('accountsPrevious').disabled=!accountPages.length;$('accountsNext').disabled=!accountNext;}catch(error){if(generation===accountRequest){$('accountsError').textContent=error.message;$('accountsError').hidden=false;}}
  }
  $('accountsRefresh').onclick=()=>loadAccounts();$('accountSearch').oninput=()=>{clearTimeout(accountTimer);accountRequest++;accountAfter='';accountPages=[];accountTimer=setTimeout(loadAccounts,250);};$('accountsNext').onclick=()=>{if(accountNext){accountPages.push(accountAfter);accountAfter=accountNext;loadAccounts();}};$('accountsPrevious').onclick=()=>{if(accountPages.length){accountAfter=accountPages.pop();loadAccounts();}};
  function tab(name){if(playerPanel&&!playerTabAllowed(name))return;if(name==='accounts'&&!['owner','admin'].includes(user?.role))return;if(!titles[name]||(name==='access'&&user?.role!=='owner'))return;document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==name);document.querySelectorAll('[data-tab]').forEach(p=>p.classList.toggle('active',p.dataset.tab===name));activeTab=name;document.querySelector('.session-toolbar').hidden=name==='accounts';if(name==='accounts')loadAccounts();$('breadcrumb').textContent=titles[name][0];$('pageTitle').textContent=titles[name][1];$('pageSubtitle').textContent=titles[name][2];}
  document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
  document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.goto)));
  $('refresh').addEventListener('click',async()=>{await refresh();if(activeTab==='accounts')await loadAccounts();});$('playerSearch').addEventListener('input',filterPlayers);
  $('sessionSelect').addEventListener('change',()=>{selectedSession=$('sessionSelect').value;refresh();});
  $('sessionForm').addEventListener('submit',async event=>{event.preventDefault();await action('create-session',$('sessionName').value.trim());});
  document.querySelectorAll('[name=mode]').forEach(b=>b.addEventListener('change',()=>action('mode',b.value)));
  $('saveForm').addEventListener('submit',async event=>{event.preventDefault();const value=$('saveName').value.trim();await action('save',value,snapshot.saves.includes(value)?['Sicherung überschreiben?',`„${value}“ wird durch den aktuellen Stand ersetzt.`]:null);});
  $('accessForm').addEventListener('submit',async event=>{event.preventDefault();const saved=await action(accessMode,$('adminEmail').value.trim(),null,null,{password:$('adminPassword').value,role:$('adminRole').value});if(!saved)return;$('adminPassword').value='';accessMode='add-admin';document.querySelector('#accessForm button[type=submit]').textContent='Person freischalten';});
  $('copyCode').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(snapshot.code);toast('Spieler-Code kopiert.');}catch{toast('Kopieren nicht möglich. Markiere den Code manuell.',true);}});
  $('logout').addEventListener('click',async()=>{try{await api('/auth/logout',{});location.replace(playerPanel?'/login':'/admin');}catch(error){toast(error.message,true);}});
  $('adminEmail').addEventListener('input',()=>{accessMode='add-admin';document.querySelector('#accessForm button[type=submit]').textContent='Person freischalten';});
  $('passwordLoginForm').addEventListener('submit',async event=>{
    event.preventDefault();$('loginSubmit').disabled=true;$('loginError').hidden=true;
    try{
      const response=await fetch('/auth/password/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':loginCsrf},body:JSON.stringify({email:$('loginEmail').value,password:$('loginPassword').value})});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Anmeldung fehlgeschlagen.');$('loginPassword').value='';showMfa(result);
    }catch(error){$('loginError').textContent=error.message;$('loginError').hidden=false;$('loginSubmit').disabled=false;}
  });
  function showMfa(result){
    $('passwordLoginForm').hidden=true;$('mfaPanel').hidden=false;document.querySelector('.login-card').classList.add('mfa-mode');
    const setup=result.stage==='setup';$('mfaSetup').hidden=!setup;$('useRecovery').hidden=setup;
    $('mfaTitle').textContent=setup?'Authenticator einrichten':'Code aus deiner App';
    if(setup){$('mfaQr').src=result.qr;$('mfaSecret').textContent=result.secret;}
    $('mfaCode').focus();
  }
  $('mfaRestart').onclick=()=>location.replace('/admin');
  $('useRecovery').onclick=()=>{$('mfaCode').inputMode='text';$('mfaCode').placeholder='Wiederherstellungscode';$('mfaCode').value='';$('mfaCode').focus();};
  $('mfaForm').addEventListener('submit',async event=>{
    event.preventDefault();$('mfaSubmit').disabled=true;$('loginError').hidden=true;
    try{
      const response=await fetch('/auth/password/mfa',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':loginCsrf},body:JSON.stringify({code:$('mfaCode').value})});
      const result=await response.json();if(!response.ok)throw Error(result.error||'Code konnte nicht bestätigt werden.');
      $('mfaCode').value='';$('mfaQr').removeAttribute('src');$('mfaSecret').textContent='';
      if(result.recovery_codes?.length){$('mfaPanel').hidden=true;$('recoveryPanel').hidden=false;$('recoveryCodes').replaceChildren(...result.recovery_codes.map(code=>el('code',code)));}else location.replace('/admin');
    }catch(error){$('loginError').textContent=error.message;$('loginError').hidden=false;}finally{$('mfaSubmit').disabled=false;}
  });
  $('recoverySaved').onchange=()=>{$('recoveryContinue').disabled=!$('recoverySaved').checked;};
  $('recoveryContinue').onclick=()=>location.replace('/admin');
  async function init(){
    try{const me=await api('/api/admin/me');user=me.user;
      if(!user){if(playerPanel){location.replace('/login');return;}$('loginView').hidden=false;if(!me.login_ready){$('setupNote').hidden=false;$('loginSubmit').disabled=true;}else{const challenge=await api('/auth/password/csrf');loginCsrf=challenge.csrf;}return;}
      $('dashboardView').hidden=false;if(playerPanel){document.title='Meine Sitzungen · Klassenkampf';document.querySelector('.brand').href='/account';document.querySelector('.workspace-label').textContent='MEINE SITZUNGEN';document.querySelector('.topbar>span').firstChild.textContent='SPIELERKONTO ';}$('profileName').textContent=user.display_email||user.email;$('profileRole').textContent=user.role==='owner'?'Inhaber':user.role==='host'?'Sitzungsleiter':user.role==='guide'?'Spielleiter':'Administrator';$('sessionForm').hidden=user.role==='guide';document.querySelector('[data-tab=system]').hidden=['guide','host'].includes(user.role);$('avatar').textContent=(user.display_email||user.email).slice(0,1).toUpperCase();$('accountsNav').hidden=!['owner','admin'].includes(user.role);$('accessNav').hidden=user.role!=='owner';await refresh();if(playerPanel)tab('sessions');setInterval(()=>{if(!busy&&!document.hidden)refresh();},15000);
    }catch(error){$('loginView').hidden=false;$('loginError').textContent='Verwaltung momentan nicht erreichbar. Bitte lade die Seite erneut.';$('loginError').hidden=false;$('loginSubmit').disabled=true;}
  }
  init();
})();
