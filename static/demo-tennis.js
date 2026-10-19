(() => {
 'use strict';
 const $=id=>document.getElementById(id),canvas=$('tennisCanvas'),ctx=canvas.getContext('2d');
 let game,active=false,raf=null,previous=null,accumulator=0,keyMask=0,touchMask=0,target=null,lastAction=Date.now();
 function status(text){if($('tennisStatus').textContent!==text)$('tennisStatus').textContent=text;}
 function draw(){window.drawGame('pong',game.snapshot(),2,ctx,{});const score='Du '+game.s2+' : '+game.s1+' Bot';if($('tennisScore').textContent!==score)$('tennisScore').textContent=score;}
 function release(){keyMask=touchMask=0;target=null;}
 function finish(message){active=false;cancelAnimationFrame(raf);release();status(message);$('tennisRestart').textContent='Noch einmal spielen';$('tennisLeft').disabled=$('tennisRight').disabled=true;draw();}
 function expired(){if(active&&Date.now()-lastAction>=120000){finish('Demo nach zwei Minuten Inaktivität beendet.');return true;}return false;}
 function frame(now){
  if(!active||expired())return;
  if(document.hidden){previous=null;accumulator=0;raf=requestAnimationFrame(frame);return;}
  if(previous!==null)accumulator+=Math.min(100,Math.max(0,now-previous));previous=now;
  if(keyMask||touchMask)lastAction=Date.now();
  while(accumulator>=25&&!game.result){game.tick(keyMask|touchMask,target);accumulator-=25;}
  draw();if(game.result){finish(game.result===2?'Du hast gewonnen!':'Der Bot hat gewonnen.');return;}
  status(game.cd?'Los geht’s in '+Math.ceil(game.cd/24):'Du spielst unten');raf=requestAnimationFrame(frame);
 }
 function reset(){cancelAnimationFrame(raf);game=new window.TennisDemo();active=true;release();lastAction=Date.now();previous=null;accumulator=0;$('tennisLeft').disabled=$('tennisRight').disabled=false;$('tennisRestart').textContent='Neue Runde';$('tennisRestart').disabled=false;draw();status('Los geht’s in 3');raf=requestAnimationFrame(frame);}
 const keys={ArrowLeft:1,KeyA:1,ArrowRight:2,KeyD:2};
 document.addEventListener('keydown',event=>{const bit=keys[event.code];if(!bit||event.altKey||event.ctrlKey||event.metaKey||event.target.closest('#cookie-notice')||!active||expired())return;event.preventDefault();keyMask|=bit;target=null;lastAction=Date.now();});
 document.addEventListener('keyup',event=>{const bit=keys[event.code];if(bit)keyMask&=~bit;});window.addEventListener('blur',release);
 for(const[id,bit]of[['tennisLeft',1],['tennisRight',2]]){const button=$(id);button.addEventListener('pointerdown',event=>{if(!active||expired())return;event.preventDefault();button.setPointerCapture(event.pointerId);touchMask|=bit;target=null;game.p2x=Math.max(4,Math.min(192,game.p2x+(bit===1?-4:4)));lastAction=Date.now();draw();});for(const name of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(name,()=>touchMask&=~bit);button.addEventListener('click',event=>{if(event.detail===0&&active&&!expired()){game.p2x=Math.max(4,Math.min(192,game.p2x+(bit===1?-16:16)));lastAction=Date.now();draw();}});}
 function point(event){if(!active||expired())return;const box=canvas.getBoundingClientRect();target=Math.max(0,Math.min(240,(event.clientX-box.left)*240/box.width));keyMask=touchMask=0;lastAction=Date.now();}
 canvas.addEventListener('pointerdown',event=>{if(!active)return;canvas.setPointerCapture(event.pointerId);point(event);});canvas.addEventListener('pointermove',event=>{if(event.pointerType==='mouse'||canvas.hasPointerCapture(event.pointerId))point(event);});
 document.addEventListener('visibilitychange',()=>{release();previous=null;accumulator=0;if(document.hidden&&active)status('Pausiert · Tab inaktiv');else expired();});
 $('tennisRestart').onclick=reset;const idle=setInterval(expired,1000);window.addEventListener('pagehide',()=>{active=false;cancelAnimationFrame(raf);clearInterval(idle);release();});window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});reset();
})();
