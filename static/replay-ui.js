(() => {
  const $=id=>document.getElementById(id),dialog=$('replayDialog');
  if(!dialog)return;
  const renderer=window.createPassiveRenderer($('replayCanvas'));
  let current=null,playing=false,time=0,clock=performance.now(),generation=0,sequence=0,loading=false;
  const cache=new Map();
  const stamp=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
  async function get(path){if(location.pathname.startsWith('/account'))path=path.replace('/api/admin/','/api/player/');const response=await fetch(path,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error(response.status===403?'Kein Zugriff auf diese Sitzung.':'Replay nicht verfügbar.');return (await response.json()).result;}
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
    $('replayNotice').textContent='Replay wird geladen …';$('replayTitle').textContent='Replay';$('replayPlay').textContent='Abspielen';
    if(!dialog.open)dialog.showModal();
    try{
      const meta=await get('/api/admin/replay?session='+encodeURIComponent(session)+'&id='+encodeURIComponent(id));
      if(gen!==generation||!dialog.open)return;
      current={session,meta};$('replayTitle').textContent=meta.name;$('replayNames').textContent=meta.players.join(' / ');
      $('replaySeek').max=Math.max(.1,meta.duration);$('replaySeek').value=0;$('replayView').replaceChildren();
      meta.players.forEach((name,i)=>{const option=document.createElement('option');option.value=i+1;option.textContent='Ansicht: '+name;$('replayView').append(option);});
      $('replayNotice').textContent=meta.truncated?'Teilaufnahme · '+({limit:'Aufnahmelimit',interrupted:'Serverneustart',storage_error:'Speicherfehler'}[meta.reason]||'Aufzeichnung unterbrochen'):meta.reason==='admin'?'Ohne Wertung beendet.':meta.reason==='worker_error'?'Technisch beendet.':'';
      await draw();
    }catch(error){$('replayNotice').textContent=error.message;}
  };
  $('replayPlay').onclick=()=>{if(!current)return;if(time>=current.meta.duration)time=0;playing=!playing;clock=performance.now();$('replayPlay').textContent=playing?'Pause':'Abspielen';};
  $('replaySeek').oninput=()=>{time=Number($('replaySeek').value);clock=performance.now();draw();};
  $('replayView').onchange=()=>{renderer.clear();draw();};
  $('replayClose').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{generation++;playing=false;current=null;cache.clear();renderer.clear();});
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
  function tick(now){
    if(playing&&current&&dialog.open){time=Math.min(current.meta.duration,time+(now-clock)/1000*Number($('replaySpeed').value));draw();if(time>=current.meta.duration){playing=false;$('replayPlay').textContent='Abspielen';}}
    clock=now;requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
