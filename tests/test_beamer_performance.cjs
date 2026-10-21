const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../static/beamer.js'),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('projection avoids redundant frames and hidden-tab traffic, resumes and backs off',async()=>{
 const elements=new Map(),events={},timers=new Map();let next=0,requests=0,draws=0,reject=false;
 const element=()=>({hidden:false,textContent:'',dataset:{},style:{setProperty(){}},replaceChildren(){},setAttribute(){}});
 const document={hidden:false,getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element,addEventListener(name,fn){events[name]=fn;}};
 let payload={session:'Test',mode:'match',state:'live',revision:1,game:'pong',name:'Pong',players:['A','B'],reconnecting:[],frame:{t:1,views:{'0':{}}}};
 const context={document,location:{hash:'#'+'a'.repeat(64)},window:{addEventListener(){}},AbortController,createPassiveRenderer:()=>({clear(){},draw(){draws++;}}),fetch:async()=>{requests++;if(reject)throw Error('Offline');return{ok:true,json:async()=>payload};},setTimeout(fn,delay){const id=++next;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);}};
 vm.runInNewContext(script,context);await flush();assert.equal(draws,1);
 async function tick(){assert.equal(timers.size,1);const[id,t]=timers.entries().next().value;timers.delete(id);await t.fn();await flush();}
 await tick();assert.equal(draws,1,'same paused frame must not redraw');
 payload={...payload,revision:2};await tick();assert.equal(draws,2,'switch must redraw even with same frame time');
 document.hidden=true;const before=requests;await tick();await tick();assert.equal(requests,before);
 document.hidden=false;events.visibilitychange();await flush();assert.equal(requests,before+1);assert.equal(timers.size,1);
 reject=true;await tick();assert.equal([...timers.values()][0].delay,1000);await tick();assert.equal([...timers.values()][0].delay,2000);
 reject=false;payload={...payload,frame:{t:2,views:{'0':{}}}};await tick();assert.equal([...timers.values()][0].delay,200);assert.equal(draws,3);
});
