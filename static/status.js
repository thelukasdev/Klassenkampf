(() => {
  'use strict';
  const $=id=>document.getElementById(id),make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const labels={operational:'Verfügbar',standby:'Bereit',paused:'Pausiert',degraded:'Beeinträchtigt',down:'Ausfall',unknown:'Unbekannt',ended:'Beendet'};
  const up=new Set(['operational','standby','paused']);
  let data=null,busy=false,filter=new URLSearchParams(location.search).get('component')||'',request=0;
  const date=t=>new Date(t*1000).toLocaleString('de-DE',{dateStyle:'medium',timeStyle:'medium'});
  function duration(s){return s>=3600?(s/3600).toFixed(1)+' h':s>=60?Math.round(s/60)+' min':Math.round(s)+' s';}
  function totals(id){const result={};for(const row of data.daily)if(row.component===id)result[row.state]=(result[row.state]||0)+row.seconds;return result;}
  function availability(id){const t=totals(id),known=Object.entries(t).filter(([k])=>!['unknown','ended'].includes(k)).reduce((s,[,v])=>s+v,0),good=Object.entries(t).filter(([k])=>up.has(k)).reduce((s,[,v])=>s+v,0);return known?((good/known)*100).toFixed(2)+' %':'Noch keine Zeitmessung';}
  function bars(parent,id){
    const days=Number($('days').value),end=new Date().toISOString().slice(0,10),start=Date.parse(end+'T00:00:00Z')-(days-1)*86400000;
    const strip=make('div',undefined,'bars'),detail=make('p','','bar-detail');detail.hidden=true;
    for(let i=0;i<days;i++){
      const day=new Date(start+i*86400000).toISOString().slice(0,10),states={};
      data.daily.filter(r=>r.component===id&&r.day===day).forEach(r=>states[r.state]=(states[r.state]||0)+r.seconds);
      const known=Object.entries(states).filter(([s])=>!['unknown','ended'].includes(s)).reduce((n,[,v])=>n+v,0),unknown=states.unknown||0;
      const state=states.down?'down':states.degraded?'degraded':unknown&&known?'mixed':unknown||!known?'unknown':states.paused&&states.paused===known?'paused':'operational';
      const summary=day+' (UTC) · '+(Object.keys(states).length?Object.entries(states).map(([s,v])=>labels[s]+': '+duration(v)).join(' · '):'Keine Messdaten');
      const bar=make('button',undefined,'bar '+state);bar.type='button';bar.title=summary;bar.setAttribute('aria-label',summary);bar.onclick=()=>{detail.textContent=summary;detail.hidden=false;};strip.append(bar);
    }
    parent.append(strip,detail);
    const footer=make('div',undefined,'component-bottom'),t=totals(id);footer.append(make('span',days+' Tage · '+availability(id)),make('span',t.unknown?'Unbekannt: '+duration(t.unknown):'Unbekannte Zeit: 0 s'));parent.append(footer);
  }
  function component(c,isSession){
    const card=make('article',undefined,isSession?'session':'component'),top=make('div',undefined,'component-top');top.append(make('h3',c.label),make('small','● '+labels[c.state],c.state));card.append(top);
    if(isSession)card.append(make('p',c.state==='ended'?'Archiviert':`${c.online??'–'} Spieler online · ${c.matches??'–'} laufende Partien`));
    else if(c.latency_ms!==undefined)card.append(make('p',(c.id==='https'?'HTTPS-Antwortzeit: ':'Interne Antwortzeit: ')+c.latency_ms+' ms','muted'));
    bars(card,c.id);return card;
  }
  function render(){
    const platform=data.components.find(c=>c.id==='platform'),state=data.stale?'unknown':platform?.state||'unknown';
    $('overall').className='overall '+state;$('overallTitle').textContent={paused:'Wartungsarbeiten',operational:'Alle Systeme erreichbar',degraded:'Einzelne Bereiche beeinträchtigt',down:'Spielserver nicht erreichbar',unknown:'Status aktuell nicht verlässlich'}[state]||labels[state];
    $('overallText').textContent=data.stale?'Messdaten veraltet.':'';$('overallText').hidden=!data.stale;
    $('updated').textContent=data.checked?'Letzte Prüfung: '+date(data.checked)+' · alle '+data.interval+' s':'Noch keine abgeschlossene Prüfung';
    $('uptime').textContent='Gesamtsystem: '+availability('platform');
    $('monitoringSince').textContent=data.started?'Messbeginn: '+date(data.started):'Noch keine Messdaten.';
    $('services').replaceChildren(...data.components.filter(c=>c.kind==='service'&&c.id!=='platform').map(c=>component(c,false)));
    const sessions=data.components.filter(c=>c.kind==='session'&&($('showEnded').checked||c.state!=='ended'));
    $('sessions').replaceChildren(...sessions.map(c=>component(c,true)));if(!sessions.length)$('sessions').append(make('p','Aktuell keine aktiven Spielsitzungen.','empty'));
    const select=$('historyFilter');select.replaceChildren();const all=make('option','Alle Bereiche');all.value='';select.append(all);data.components.forEach(c=>{const option=make('option',c.label);option.value=c.id;select.append(option);});select.value=filter;
  }
  function renderEvents(events){
    const list=$('history');list.replaceChildren();
    events.slice(0,6).forEach(e=>{const row=make('article',undefined,'event'),when=make('time',date(e.time));when.dateTime=new Date(e.time*1000).toISOString();const info=make('div');info.append(make('h3',e.label+' · '+labels[e.state],e.state),make('p',e.detail));row.append(when,info);list.append(row);});
    if(!list.children.length)list.append(make('p','Noch keine Einträge für diesen Bereich.','empty'));
  }
  async function refresh(){
    if(busy)return;busy=true;const generation=++request;$('refresh').disabled=true;
    try{
      const q=new URLSearchParams({days:$('days').value});if(filter)q.set('component',filter);
      const response=await fetch('/api/status?'+q,{cache:'no-store'});if(!response.ok)throw Error();const next=await response.json();if(generation!==request)return;
      data=next;render();renderEvents(next.events);
    }catch{
      if(data){data.stale=true;data.components.forEach(c=>{if(c.state!=='ended')c.state='unknown';});render();}
      else{$('overallTitle').textContent='Statusdienst momentan nicht erreichbar';$('overallText').textContent='Keine aktuellen Messdaten.';$('overallText').hidden=false;}
    }finally{busy=false;$('refresh').disabled=false;}
  }
  $('refresh').onclick=()=>refresh();$('days').onchange=()=>refresh();$('showEnded').onchange=()=>{if(data)render();};
  $('historyFilter').onchange=()=>{filter=$('historyFilter').value;refresh();};
  setInterval(()=>{if(!document.hidden&&!busy)refresh();},15000);
  refresh();
})();
