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
  const moves=legal(board);if(!moves.length)return null;
  for(const c of moves)if(winner(drop(board,c,2))===2)return c;
  for(const c of moves)if(winner(drop(board,c,1))===1)return c;
  const depth=Math.max(1,Math.min(5,options.depth||4)),limit=Math.max(1,Math.min(20000,options.maxNodes||12000));
  const clock=()=>typeof performance!=='undefined'?performance.now():Date.now(),started=clock(),maxMs=Math.max(1,Math.min(200,options.maxMs||120));let nodes=0;
  function search(b,d,player,alpha,beta){
   const w=winner(b);if(w)return w===2?1000000+d:-1000000-d;
   const next=legal(b);if(!next.length)return 0;
   if(!d||++nodes>=limit||clock()-started>maxMs)return evaluate(b);
   let value=player===2?-Infinity:Infinity;
   for(const c of next){const score=search(drop(b,c,player),d-1,3-player,alpha,beta);value=player===2?Math.max(value,score):Math.min(value,score);if(player===2)alpha=Math.max(alpha,value);else beta=Math.min(beta,value);if(beta<=alpha||nodes>=limit||clock()-started>maxMs)break;}
   return value;
  }
  let best=moves[0],value=-Infinity;
  for(const c of moves){const score=search(drop(board,c,2),depth-1,1,-Infinity,Infinity);if(score>value){value=score;best=c;}if(nodes>=limit||clock()-started>maxMs)break;}return best;
 }
 const api={winner,legal,drop,chooseMove,lines};root.DemoGame=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
