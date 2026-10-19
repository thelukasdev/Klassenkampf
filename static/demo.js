(() => {
 'use strict';
 const $=id=>document.getElementById(id),rules=window.DemoGame,buttons=[],cells=[];
 let board,turn,active,request=0,worker=null,botTimer,botWatchdog,lastAction=Date.now(),selected=3;
 for(let col=0;col<7;col++){const button=document.createElement('button');button.type='button';button.textContent='↓';button.setAttribute('aria-label','Spalte '+(col+1));button.onclick=()=>play(col);$('demoColumns').append(button);buttons.push(button);}
 for(let row=0;row<6;row++){const line=document.createElement('div');line.className='board-row';line.setAttribute('role','row');for(let col=0;col<7;col++){const cell=document.createElement('div');cell.className='cell';cell.setAttribute('role','gridcell');line.append(cell);cells.push(cell);}$('demoBoard').append(line);}
 function stopWorker(){clearTimeout(botTimer);clearTimeout(botWatchdog);if(worker)worker.terminate();worker=null;}
 function draw(){
  const won=rules.winner(board),highlight=new Set(won?rules.lines.filter(line=>line.every(i=>board[i]===won)).flat():[]);
  cells.forEach((cell,i)=>{cell.className='cell'+(board[i]===1?' human':board[i]===2?' bot':'')+(highlight.has(i)?' winner':'');cell.setAttribute('aria-label','Reihe '+(Math.floor(i/7)+1)+', Spalte '+(i%7+1)+': '+(['leer','Du','Bot'][board[i]]));});
  buttons.forEach((button,c)=>{button.disabled=!active||turn!==1||board[c]!==0;button.classList.toggle('selected',c===selected);});
 }
 function finish(message){active=false;stopWorker();$('demoStatus').textContent=message;$('demoRestart').textContent='Noch einmal spielen';draw();}
 function afterMove(){const won=rules.winner(board);if(won){finish(won===1?'Du hast gewonnen!':'Der Bot hat gewonnen.');return;}if(!rules.legal(board).length){finish('Unentschieden.');return;}draw();if(turn===2)startBot();else $('demoStatus').textContent='Du bist dran';}
 function expired(){if(active&&Date.now()-lastAction>=120000){finish('Demo nach zwei Minuten Inaktivität beendet.');return true;}return false;}
 function acceptBot(column,id){if(id!==request||!active||turn!==2||expired())return;clearTimeout(botWatchdog);const legal=rules.legal(board);if(!legal.includes(column))column=legal[0];const next=rules.drop(board,column,2);if(!next)return;board=next;turn=1;afterMove();}
 function startBot(){
  $('demoStatus').textContent='Bot überlegt …';const id=++request;
  botTimer=setTimeout(()=>{
   if(id!==request||!active)return;
   function fallback(){if(id===request&&active&&turn===2)acceptBot(rules.chooseMove(board,{depth:2,maxNodes:500,maxMs:30}),id);}
   try{
    if(!worker)worker=new Worker('/demo-worker.js');worker.onmessage=e=>acceptBot(e.data.column,e.data.id);worker.onerror=event=>{event.preventDefault();if(worker)worker.terminate();worker=null;fallback();};
    worker.postMessage({id,board});
    botWatchdog=setTimeout(()=>{if(id!==request||!active||turn!==2)return;if(worker)worker.terminate();worker=null;fallback();},2000);
   }catch(_){if(worker)worker.terminate();worker=null;fallback();}
  },350);
 }
 function play(col){if(!active||turn!==1||expired())return;const next=rules.drop(board,col,1);if(!next)return;lastAction=Date.now();selected=col;board=next;turn=2;afterMove();}
 function reset(){stopWorker();request++;board=Array(42).fill(0);turn=1;active=true;lastAction=Date.now();selected=3;$('demoStatus').textContent='Du bist dran';$('demoRestart').textContent='Neue Runde';$('demoRestart').disabled=false;draw();}
 $('demoRestart').onclick=reset;
 document.addEventListener('keydown',event=>{
  if(!active||turn!==1||expired()||event.altKey||event.ctrlKey||event.metaKey||event.target.closest('#cookie-notice'))return;
  if(/^[1-7]$/.test(event.key)){event.preventDefault();play(Number(event.key)-1);}
  else if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();selected=(selected+(event.key==='ArrowLeft'?6:1))%7;lastAction=Date.now();draw();buttons[selected].focus();}
  else if(event.key==='Enter'&&!event.target.closest('a,button')){event.preventDefault();play(selected);}
 });
 const idle=setInterval(expired,1000);
 window.addEventListener('pagehide',()=>{stopWorker();clearInterval(idle);active=false;});
 window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
 reset();
})();
