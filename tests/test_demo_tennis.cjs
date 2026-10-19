const test=require('node:test'),assert=require('node:assert/strict');
const Tennis=require('../static/demo-tennis-engine.js');
const make=()=>new Tennis(()=>.5);
test('countdown freezes ball then simulation advances',()=>{const g=make(),start=g.by;for(let i=0;i<72;i++)g.tick();assert.equal(g.by,start);assert.equal(g.cd,0);g.tick();assert.notEqual(g.by,start);});
test('human movement, pointer targeting and paddle boundaries',()=>{const g=make();g.p2x=4;g.tick(1);assert.equal(g.p2x,4);g.p2x=192;g.tick(2);assert.equal(g.p2x,192);g.p2x=98;g.tick(0,200);assert.equal(g.p2x,102);g.tick(1,null);assert.equal(g.p2x,98);});
test('side walls reflect ball without scoring',()=>{const g=make();g.cd=0;g.bx=5;g.bvx=-4;g.bvy=1;g.tick();assert.ok(g.bvx>0);assert.ok(g.bx>=5);assert.equal(g.s1+g.s2,0);});
test('both paddles return ball and speed stays bounded',()=>{for(const bottom of [true,false]){const g=make();g.cd=0;g.bx=120;g.by=bottom?259:43;g.bvx=0;g.bvy=bottom?8:-8;g.tick();assert.equal(Math.sign(g.bvy),bottom?-1:1);assert.ok(Math.hypot(g.bvx,g.bvy)<=9.000001);assert.equal(g.s1+g.s2,0);}});
test('correct scoring, five-point finish and frozen result',()=>{for(const player of [1,2]){const g=make();for(let i=0;i<5;i++){g.cd=0;g.bx=6;g.by=player===2?29:277;g.bvx=0;g.bvy=player===2?-4:4;g.tick();assert.equal(player===1?g.s1:g.s2,i+1);if(i<4)assert.equal(g.cd,72);}assert.equal(g.result,player);assert.equal(g.snapshot().st,player);const before=g.snapshot();g.tick(2,220);assert.deepEqual(g.snapshot(),before);}});
test('bot reaction is delayed and movement has a speed limit',()=>{const g=make();g.bx=220;g.bvy=-4;const before=g.p1x;g.tick();assert.equal(g.p1x,before);g.botClock=7;g.tick();assert.ok(g.p1x>before);assert.ok(g.p1x-before<=2.5);assert.ok(g.p1x>=4&&g.p1x<=192);});
