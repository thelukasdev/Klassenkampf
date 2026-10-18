(() => {
  const $=id=>document.getElementById(id),dialog=$('replayDialog');
  if(!dialog)return;
  const publicReplay=location.pathname==='/replay'||location.pathname==='/replay/'||location.pathname==='/shared-replay.html',shareToken=publicReplay?location.hash.slice(1):'';
  const renderer=window.createPassiveRenderer($('replayCanvas'));
  let current=null,playing=false,time=0,clock=performance.now(),generation=0,sequence=0,loading=false;
  const cache=new Map();
  const stamp=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
  async function get(path){
    if(publicReplay){const query=new URL(path,location.origin).searchParams;path='/api/replay-share'+(query.has('chunk')?'?chunk='+query.get('chunk'):'');}
    else if(location.pathname.startsWith('/account'))path=path.replace('/api/admin/','/api/player/');
    const response=await fetch(path,{credentials:publicReplay?'omit':'same-origin',cache:'no-store',headers:publicReplay?{'X-Replay-Token':shareToken}:{}});
    if(!response.ok)throw Error(response.status===403?'Kein Zugriff auf diese Sitzung.':'Replay nicht verfügbar oder Freigabe beendet.');return (await response.json()).result;
  }
  function url(suffix=''){return '/api/admin/replay'+suffix+'?session='+encodeURIComponent(current.session)+'&id='+encodeURIComponent(current.meta.id);}
  async function chunk(index){
    if(!cache.has(index)){const promise=get(url('-chunk')+'&chunk='+index);cache.set(index,promise);promise.catch(()=>cache.delete(index));}
    const frames=await cache.get(index);
    while(cache.size>3){const first=cache.keys().next().value;if(first===index)break;cache.delete(first);}
    return frames;
  }
  async function draw(){
    if(!current||!dialog.open)return;
    const gen=generation,seq=++sequence;
    let index=0;current.meta.segments.forEach((s,i)=>{if(s.start<=time)index=i;});
    try{
      const frames=await chunk(index);if(gen!==generation||seq!==sequence||!dialog.open)return;
      let frame=frames[0];for(const f of frames){if(f.t>time)break;frame=f;}
      renderer.draw(current.meta.game,frame,Number($('replayView').value));
      $('replayTime').textContent=stamp(time)+' / '+stamp(current.meta.duration);
      $('replaySeek').value=time;
    }catch(error){playing=false;$('replayNotice').textContent=error.message;}
  }
  window.openReplay=async(session,id)=>{
    playing=false;current=null;time=0;generation++;cache.clear();renderer.clear();const gen=generation;
    if($('replaySharePanel')){$('replayShare').textContent='Freigabelink erstellen';$('replaySharePanel').hidden=true;$('replayShareUrl').value='';$('replayRevoke').hidden=true;}
    $('replayNotice').textContent='Replay wird geladen …';$('replayTitle').textContent='Replay';$('replayPlay').textContent='Abspielen';
    if(!dialog.open)dialog.showModal();
    try{
      const meta=await get('/api/admin/replay?session='+encodeURIComponent(session)+'&id='+encodeURIComponent(id));
      if(gen!==generation||!dialog.open)return;
      current={session,meta};if($('replayRevoke'))$('replayRevoke').hidden=!meta.shared;if(publicReplay)$('sharedState').hidden=true;$('replayTitle').textContent=meta.name;$('replayNames').textContent=meta.players.join(' / ');
      $('replaySeek').max=Math.max(.1,meta.duration);$('replaySeek').value=0;$('replayView').replaceChildren();
      meta.players.forEach((name,i)=>{const option=document.createElement('option');option.value=i+1;option.textContent='Ansicht: '+name;$('replayView').append(option);});
      $('replayNotice').textContent=meta.truncated?'Teilaufnahme · '+({limit:'Aufnahmelimit',interrupted:'Serverneustart',storage_error:'Speicherfehler'}[meta.reason]||'Aufzeichnung unterbrochen'):meta.reason==='admin'?'Ohne Wertung beendet.':meta.reason==='worker_error'?'Technisch beendet.':'';
      await draw();
    }catch(error){$('replayNotice').textContent=error.message;}
  };
  $('replayPlay').onclick=()=>{if(!current)return;if(time>=current.meta.duration)time=0;playing=!playing;clock=performance.now();$('replayPlay').textContent=playing?'Pause':'Abspielen';};
  $('replaySeek').oninput=()=>{time=Number($('replaySeek').value);clock=performance.now();draw();};
  $('replayView').onchange=()=>{renderer.clear();draw();};
  $('replayClose').onclick=()=>publicReplay?location.assign('/'):dialog.close();dialog.addEventListener('close',()=>{generation++;playing=false;current=null;cache.clear();renderer.clear();});
  $('replayDownload').onclick=async()=>{
    if(!current||loading)return;loading=true;$('replayDownload').disabled=true;const saved=current,gen=generation;
    try{
      const parts=['{"format":"klassenkampf-replay-v1","meta":'+JSON.stringify(saved.meta)+',"frames":['];
      for(let i=0;i<saved.meta.segments.length;i++){
        if(gen!==generation)throw Error('Download abgebrochen.');
        const frames=await chunk(i);if(i)parts.push(',');parts.push(JSON.stringify(frames).slice(1,-1));
      }
      parts.push(']}');const blob=new Blob(parts,{type:'application/json'}),link=document.createElement('a'),address=URL.createObjectURL(blob);
      link.href=address;link.download='replay-'+saved.meta.id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(address),1000);
    }catch(error){$('replayNotice').textContent=error.message;}finally{loading=false;$('replayDownload').disabled=false;}
  };
  async function shareAction(action){
    const saved=current;if(!saved||loading)return;loading=true;
    try{
      const prefix=location.pathname.startsWith('/account')?'/api/player/':'/api/admin/';
      const me=await fetch(prefix+'me',{cache:'no-store'}).then(r=>r.json());
      const response=await fetch(prefix+'action',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.user?.csrf||''},body:JSON.stringify({action,session:saved.session,value:saved.meta.id})});
      const body=await response.json();if(!response.ok)throw Error(body.error||'Freigabe fehlgeschlagen.');
      if(current!==saved)return;
      const revoked=action==='revoke-replay';$('replaySharePanel').hidden=revoked;$('replayShareUrl').value=body.result.url||'';$('replayRevoke').hidden=revoked;
      $('replayShare').textContent=revoked?'Freigabelink erstellen':'Neuen Link erstellen';
      $('replayNotice').textContent=revoked?'Freigabe beendet.':'Freigabelink erstellt. Bisherige Links sind ungültig.';
    }catch(error){$('replayNotice').textContent=error.message;}finally{loading=false;}
  }
  if($('replayShare')){
    $('replayShare').onclick=()=>shareAction('share-replay');$('replayRevoke').onclick=()=>shareAction('revoke-replay');
    $('replayCopy').onclick=async()=>{try{await navigator.clipboard.writeText($('replayShareUrl').value);$('replayNotice').textContent='Link kopiert.';}catch(_){$('replayShareUrl').select();$('replayNotice').textContent='Link markieren und kopieren.';}};
  }
  if(publicReplay){dialog.addEventListener('cancel',event=>{event.preventDefault();location.assign('/');});window.openReplay('','');}
  function tick(now){
    if(playing&&current&&dialog.open){time=Math.min(current.meta.duration,time+(now-clock)/1000*Number($('replaySpeed').value));draw();if(time>=current.meta.duration){playing=false;$('replayPlay').textContent='Abspielen';}}
    clock=now;requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
