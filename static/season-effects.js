(() => {
  'use strict';
  const scene=document.querySelector('.season-christmas');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let direction='';
  document.addEventListener('pointermove',event=>{
    if(event.pointerType!=='mouse'||document.hidden||reduced.matches||!scene||getComputedStyle(scene).display==='none')return;
    const next=event.clientX<innerWidth*.35?'wind-left':event.clientX>innerWidth*.65?'wind-right':'';
    if(next===direction)return;
    scene.classList.remove('wind-left','wind-right');if(next)scene.classList.add(next);direction=next;
  },{passive:true});
  const pause=()=>document.documentElement.classList.toggle('season-paused',document.hidden);
  document.addEventListener('visibilitychange',pause);pause();
})();
