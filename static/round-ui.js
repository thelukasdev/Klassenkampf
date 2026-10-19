(() => {
 'use strict';
 const $=id=>document.getElementById(id);let current=null,until=0;
 const command=data=>window.dispatchEvent(new CustomEvent('round-command',{detail:data}));
 function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;}
 function button(text,run){const el=node('button',text);el.type='button';el.className='btn mini';el.onclick=run;return el;}
 window.clearRoundFlow=()=>{current=null;for(const id of ['roundPanel','roundResultPanel','waitingRoom'])$(id).hidden=true;$('backBtn').textContent='Zurück zur Lobby';};
 window.renderRoundFlow=flow=>{
  const previous=current?.offer;current=flow||null;
  const waiting=$('waitingRoom');waiting.replaceChildren();waiting.hidden=!flow?.waiting;
  if(flow?.waiting){waiting.append(node('h3','Warteraum'),node('p',flow.ready+' / '+flow.online+' bereit · Warte auf die Spielleitung'));waiting.append(button(flow.you_ready?'Bereitschaft zurücknehmen':'Ich bin bereit',()=>command({t:'ready',ready:!current.you_ready})));}
  const offer=flow?.offer;until=performance.now()+(offer?.seconds||0)*1000;
  for(const id of ['roundPanel','roundResultPanel']){
   const panel=$(id);panel.replaceChildren();panel.hidden=!offer;if(!offer)continue;
   panel.append(node('h3',offer.kind==='vote'?'Nächstes Minispiel':'Revanche'),node('p',offer.players.join(' · ')),node('p',offer.accepted+' / '+offer.total+(offer.kind==='vote'?' Stimmen':' Zusagen')));
   const options=node('div');options.className='round-options';
   for(const choice of offer.choices){const chosen=offer.selected===choice.id;const text=offer.kind==='vote'?choice.name+' · '+choice.votes:chosen?'Revanche zugesagt':'Revanche spielen';const el=button(text,()=>command({t:'round_vote',id:offer.id,game:choice.id}));el.classList.toggle('chosen',chosen);el.setAttribute('aria-pressed',String(chosen));el.disabled=chosen;options.append(el);}
   panel.append(options);const timer=node('p');timer.className='round-time';panel.append(timer);
   if(offer.kind==='vote')panel.append(node('small','Alle vier stimmen ab. Bei Gleichstand wird gelost.'));
   panel.append(button('Gruppe verlassen',()=>{command({t:'round_leave'});window.clearRoundFlow();window.dispatchEvent(new Event('round-exit'));}));
  }
  $('backBtn').textContent=offer?'Gruppe verlassen & Lobby':'Zurück zur Lobby';
  if(previous&&!offer)window.dispatchEvent(new CustomEvent('round-notice',{detail:'Die gemeinsame Runde wurde geschlossen.'}));
 };
 setInterval(()=>{if(!current?.offer)return;const seconds=Math.max(0,Math.ceil((until-performance.now())/1000));document.querySelectorAll('.round-time').forEach(el=>{const text=seconds+' Sekunden';if(el.textContent!==text)el.textContent=text;});if(!seconds)window.clearRoundFlow();},250);
})();
