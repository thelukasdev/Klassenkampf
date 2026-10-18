/* Shared passive renderer. Never opens a player WebSocket or sends inputs. */
(() => {
  window.createPassiveRenderer=canvas=>{
    const ctx=canvas.getContext('2d');let last='',R={};
    return {clear(){ctx.clearRect(0,0,240,280);R={};last='';},draw(game,frame,role=1){
      if(!frame)return;const snap=frame.views['0']||frame.views[String(role)];if(!snap)return;
      const key=game+':'+role+':'+frame.t;
      if(key===last)return;last=key;R={};
      if(snap.grid){const bin=atob(snap.grid);R.tgrid=Uint8Array.from(bin,c=>c.charCodeAt(0));}
      window.drawGame(game,snap,role,ctx,R);
    }};
  };
  const canvas=document.getElementById('viewerCanvas');if(!canvas)return;
  const renderer=window.createPassiveRenderer(canvas),token=location.hash.slice(1);let stopped=false;
  async function refresh(){
    try{
      if(!token){stopped=true;throw Error('Kein Zuschauerlink.');}
      const response=await fetch('/api/watch',{headers:{'X-Spectator-Token':token},cache:'no-store'});
      if(!response.ok){if(response.status===404){stopped=true;throw Error('Freigabe beendet oder nicht verfügbar.');}throw Error('Verbindung unterbrochen.');}
      const data=await response.json();document.getElementById('viewerTitle').textContent=data.name;
      document.getElementById('viewerNames').textContent=data.players.join(' / ');
      document.getElementById('viewerState').textContent=data.paused?'Pausiert':'Live';renderer.draw(data.game,data.frame);
    }catch(error){renderer.clear();document.getElementById('viewerState').textContent=error.message==='Failed to fetch'?'Verbindung unterbrochen.':error.message;}
    if(!stopped)setTimeout(refresh,200);
  }
  refresh();
})();
