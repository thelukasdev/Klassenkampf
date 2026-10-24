(() => {
  'use strict';
  const scenes=[...document.querySelectorAll('.season-christmas,.season-scenery')];
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let direction='';
  document.addEventListener('pointermove',event=>{
    if(event.pointerType!=='mouse'||document.hidden||reduced.matches||!scenes.some(scene=>getComputedStyle(scene).display!=='none'))return;
    const next=event.clientX<innerWidth*.35?'wind-left':event.clientX>innerWidth*.65?'wind-right':'';
    if(next===direction)return;
    for(const scene of scenes){scene.classList.remove('wind-left','wind-right');if(next)scene.classList.add(next);}direction=next;
  },{passive:true});
  const pause=()=>document.documentElement.classList.toggle('season-paused',document.hidden);
  document.addEventListener('visibilitychange',pause);pause();
})();
