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
