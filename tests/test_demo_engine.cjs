const test=require('node:test'),assert=require('node:assert/strict');
const game=require('../static/demo-engine.js');
const empty=()=>Array(42).fill(0);
test('gravity, full columns, bounds and immutable moves',()=>{
 let b=empty();const first=game.drop(b,3,1);assert.equal(first[38],1);assert.equal(b[38],0);b=first;
 for(let i=1;i<6;i++)b=game.drop(b,3,i%2+1);
 assert.equal(game.drop(b,3,1),null);assert.equal(game.drop(b,-1,1),null);assert.equal(game.drop(b,7,1),null);assert.equal(game.drop(b,2,3),null);
});
test('four in every direction and no false three',()=>{
 for(const positions of [[35,36,37,38],[3,10,17,24],[0,8,16,24],[6,12,18,24]]){
  const b=empty();for(const i of positions.slice(0,3))b[i]=1;assert.equal(game.winner(b),0);b[positions[3]]=1;assert.equal(game.winner(b),1);assert.equal(game.drop(b,0,2),null);
 }
});
test('bot takes immediate win before defending',()=>{
 const b=empty();for(const c of [0,1,2])b[35+c]=2;for(const c of [4,5,6])b[28+c]=1;assert.equal(game.chooseMove(b),3);
});
test('bot blocks human immediate win',()=>{
 const b=empty();for(const c of [1,2,3])b[35+c]=1;b[35]=2;assert.equal(game.chooseMove(b),4);
});
test('bot uses legal columns under tiny resource budget',()=>{
 let b=empty();for(let i=0;i<6;i++)b=game.drop(b,3,i%2+1);const original=b.slice();const move=game.chooseMove(b,{maxNodes:1,maxMs:1});assert.ok(game.legal(b).includes(move));assert.notEqual(move,3);assert.deepEqual(b,original);
});
test('full drawn board and won board have no bot move',()=>{
 const b=[];for(let r=0;r<6;r++)for(let c=0;c<7;c++)b.push((Math.floor(c/2)+r)%2+1);
 assert.equal(game.winner(b),0);assert.deepEqual(game.legal(b),[]);assert.equal(game.chooseMove(b),null);
 const won=empty();for(let c=0;c<4;c++)won[35+c]=2;assert.equal(game.chooseMove(won),null);
});
test('invalid worker input is rejected',()=>{for(const b of [null,{},[],Array(42).fill(7)])assert.equal(game.chooseMove(b),null);});
test('complete simulated rounds always alternate legal moves',()=>{
 for(let n=0;n<8;n++){let b=empty(),turn=1,moves=0;while(!game.winner(b)&&game.legal(b).length){const legal=game.legal(b),col=turn===2?game.chooseMove(b,{maxNodes:500,maxMs:20}):legal[(moves+n)%legal.length];assert.ok(legal.includes(col));b=game.drop(b,col,turn);assert.ok(b);turn=3-turn;assert.ok(++moves<=42);}}
});
const winningMoves=(b,p)=>game.legal(b).filter(c=>game.winner(game.drop(b,c,p))===p);

test('bot avoids supporting an opponent win even if search budget is exhausted',()=>{
 const b=[0,0,0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0,1,2,0,2,0,0,2,1,1,2,1,1,2,1,2,2,1,1,2,1,2,2,2,1],original=b.slice();
 assert.deepEqual(winningMoves(b,1),[]);assert.ok(winningMoves(game.drop(b,3,2),1).length);
 const move=game.chooseMove(b,{maxNodes:1,maxMs:1});assert.equal(winningMoves(game.drop(b,move,2),1).length,0);assert.deepEqual(b,original);
});

test('bot creates a fork that no single opponent move can block',()=>{
 const b=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1,2,0,1,1,0,0,2,2,0];
 const move=game.chooseMove(b,{maxNodes:50000,maxMs:900}),next=game.drop(b,move,2);assert.equal(move,3);assert.ok(winningMoves(next,2).length>=2);assert.equal(winningMoves(next,1).length,0);
 for(const c of game.legal(next))assert.ok(winningMoves(game.drop(next,c,1),2).length);
});

function exactOutcome(b,p,memo=new Map()){
 const win=game.winner(b);if(win)return win===p?1:-1;const moves=game.legal(b);if(!moves.length)return 0;
 const key=b.join('')+p;if(memo.has(key))return memo.get(key);let result=-1;
 for(const c of moves){result=Math.max(result,-exactOutcome(game.drop(b,c,p),3-p,memo));if(result===1)break;}
 memo.set(key,result);return result;
}
test('deeper search finds a proven endgame win missed by the previous shallow choice',()=>{
 const board=[0,0,2,0,1,0,0,1,1,1,2,1,0,0,2,1,2,2,1,0,0,2,2,1,1,2,0,0,1,2,1,2,1,1,2,2,2,1,2,1,1,2];
 assert.equal(Math.abs(exactOutcome(game.drop(board,5,2),1)),0);
 for(const b of [board,Array.from({length:42},(_,i)=>board[Math.floor(i/7)*7+6-i%7])]){
  const original=b.slice(),move=game.chooseMove(b,{maxNodes:300000,maxMs:900});assert.equal(-exactOutcome(game.drop(b,move,2),1),1);assert.deepEqual(b,original);
 }
});
test('non-finite resource options remain bounded and null options are accepted',()=>{
 const b=empty();b[38]=1;const t=performance.now();assert.ok(game.legal(b).includes(game.chooseMove(b,{depth:Infinity,maxNodes:1,maxMs:NaN})));assert.ok(performance.now()-t<1000);assert.ok(game.legal(b).includes(game.chooseMove(b,null)));
});
