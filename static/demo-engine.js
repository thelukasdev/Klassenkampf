/* Isolated Connect Four demo rules and bounded bot search. */
(function(root){
 'use strict';
 const order=[3,2,4,1,5,0,6],lines=[];
 for(let r=0;r<6;r++)for(let c=0;c<7;c++)for(const[dr,dc]of[[0,1],[1,0],[1,1],[1,-1]]){
  if(r+3*dr<6&&c+3*dc>=0&&c+3*dc<7)lines.push([0,1,2,3].map(n=>(r+n*dr)*7+c+n*dc));
 }
 function winner(b){for(const line of lines){const p=b[line[0]];if(p&&line.every(i=>b[i]===p))return p;}return 0;}
 function legal(b){return order.filter(c=>b[c]===0);}
 function drop(b,c,p){
  if(!Number.isInteger(c)||c<0||c>6||![1,2].includes(p)||b[c]||winner(b))return null;
  const next=b.slice();for(let r=5;r>=0;r--)if(!next[r*7+c]){next[r*7+c]=p;return next;}return null;
 }
 function evaluate(b){
  let score=0;for(let r=0;r<6;r++)score+=b[r*7+3]===2?6:b[r*7+3]===1?-6:0;
  for(const line of lines){let a=0,z=0;for(const i of line){if(b[i]===2)a++;else if(b[i]===1)z++;}if(a&&!z)score+=[0,1,9,90,100000][a];if(z&&!a)score-=[0,1,10,100,100000][z];}return score;
 }
 function chooseMove(board,options={}){
  if(!Array.isArray(board)||board.length!==42||!board.every(v=>v===0||v===1||v===2)||winner(board))return null;
  options=options&&typeof options==='object'?options:{};
  const b=board.slice(),powers=[1,3,9,27,81,243],codes=Array(7).fill(0),table=new Map(),MATE=1000000,STOP={};
  for(let r=0;r<6;r++)for(let c=0;c<7;c++)codes[c]+=b[r*7+c]*powers[r];
  const clock=()=>typeof performance!=='undefined'?performance.now():Date.now(),started=clock();
  const bounded=(v,f,min,max)=>Number.isFinite(v)?Math.max(min,Math.min(max,Math.floor(v))):f;
  const empties=b.filter(v=>!v).length,depth=bounded(options.depth,empties<=12?empties:9,1,14),limit=bounded(options.maxNodes,120000,1,300000),maxMs=bounded(options.maxMs,500,1,900);let nodes=0,rootMove=null;
  function put(c,p){for(let r=5;r>=0;r--)if(!b[r*7+c]){b[r*7+c]=p;codes[c]+=p*powers[r];return r;}return -1;}
  function undo(c,r,p){b[r*7+c]=0;codes[c]-=p*powers[r];}
  function won(c,r,p){for(const[dr,dc]of[[0,1],[1,0],[1,1],[1,-1]]){let count=1;for(const sign of[-1,1]){let y=r+sign*dr,x=c+sign*dc;while(y>=0&&y<6&&x>=0&&x<7&&b[y*7+x]===p){count++;y+=sign*dr;x+=sign*dc;}}if(count>=4)return true;}return false;}
  function wins(p,moves){const out=[];for(const c of moves){const r=put(c,p),win=won(c,r,p);undo(c,r,p);if(win)out.push(c);}return out;}
  function candidates(p){const moves=legal(b),winning=wins(p,moves);if(winning.length)return {moves:winning,win:true};const threats=wins(3-p,moves);if(threats.length>1)return {moves:[],loss:true};const safe=[];for(const c of threats.length?threats:moves){const r=put(c,p);if(!wins(3-p,legal(b)).length)safe.push(c);undo(c,r,p);}return {moves:safe,loss:!!moves.length&&!safe.length,forced:threats.length===1};}
  const first=candidates(2);if(first.win)return first.moves[0];
  // Even an interrupted search must never select a move that loses immediately if a safe move exists.
  let best=first.moves[0]??legal(b)[0];if(best===undefined)return null;
  function search(d,p,alpha,beta,ply,extensions){
   if(++nodes>limit||((nodes&31)===0&&clock()-started>=maxMs))throw STOP;
   const moveset=candidates(p);if(moveset.win)return MATE-ply-1;if(moveset.loss)return -MATE+ply+2;if(!moveset.moves.length)return 0;
   if(d<=0&&!(moveset.forced&&extensions>0))return (p===2?1:-1)*evaluate(b);
   const key=p+':'+codes.join(','),cached=d>0?table.get(key):null,originalAlpha=alpha,originalBeta=beta;
   if(cached&&cached.depth>=d){if(cached.flag==='exact')return cached.value;if(cached.flag==='lower')alpha=Math.max(alpha,cached.value);else beta=Math.min(beta,cached.value);if(alpha>=beta)return cached.value;}
   const moves=moveset.moves;if(cached&&moves.includes(cached.move)){moves.splice(moves.indexOf(cached.move),1);moves.unshift(cached.move);}
   let value=-Infinity,chosen=moves[0];
   for(const c of moves){const r=put(c,p);let score;try{score=-search(d-1,3-p,-beta,-alpha,ply+1,d<=0?extensions-1:extensions);}finally{undo(c,r,p);}if(score>value){value=score;chosen=c;if(ply===0)rootMove=c;}alpha=Math.max(alpha,value);if(alpha>=beta)break;}
   if(d>0&&table.size<50000)table.set(key,{depth:d,value,move:chosen,flag:value<=originalAlpha?'upper':value>=originalBeta?'lower':'exact'});
   return value;
  }
  // Only commit complete iterations: resource limits cannot bias the result toward the first searched column.
  for(let d=1;d<=Math.min(depth,empties);d++){
   rootMove=best;
   try{const score=search(d,2,-Infinity,Infinity,0,4);best=rootMove;if(Math.abs(score)>MATE-50)break;}
   catch(error){if(error!==STOP)throw error;break;}
   if(nodes>=limit||clock()-started>=maxMs)break;
  }
  return best;
 }
 const api={winner,legal,drop,chooseMove,lines};root.DemoGame=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
