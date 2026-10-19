/* Tennis42 browser demo. Fixed 25 ms simulation ticks, human at the bottom. */
(function(root){
 'use strict';
 class TennisDemo {
  constructor(random=Math.random){this.random=random;this.s1=0;this.s2=0;this.result=0;this.p1x=this.p2x=98;this.botTarget=120;this.botClock=0;this.serve(random()<.5?-1:1);}
  serve(direction){this.cd=72;this.p1x=this.p2x=98;this.bx=120;this.by=153;const angle=(this.random()*60-30)*Math.PI/180;this.bvx=Math.sin(angle)*4;this.bvy=direction*Math.cos(angle)*4;}
  bounce(px){this.bvx=((this.bx-px-22)/22)*2.4;const speed=Math.hypot(this.bvx,this.bvy),next=Math.min(speed*1.05,9);if(speed){this.bvx*=next/speed;this.bvy*=next/speed;}}
  score(player){if(player===1)this.s1++;else this.s2++;if((player===1?this.s1:this.s2)>=5)this.result=player;else this.serve(player===2?-1:1);}
  tick(mask=0,target=null){
   if(this.result)return;
   if(Number.isFinite(target))this.p2x+=Math.max(-4,Math.min(4,target-22-this.p2x));
   else this.p2x+=(mask&1?-4:0)+(mask&2?4:0);
   this.p2x=Math.max(4,Math.min(192,this.p2x));
   if(++this.botClock>=8){this.botClock=0;this.botTarget=this.bvy<0?this.bx+(this.random()-.5)*28:120;}
   this.p1x=Math.max(4,Math.min(192,this.p1x+Math.max(-2.5,Math.min(2.5,this.botTarget-22-this.p1x))));
   if(this.cd){this.cd--;return;}
   for(let i=0;i<4;i++){
    this.bx+=this.bvx/4;this.by+=this.bvy/4;
    if(this.bx<5){this.bx=5;this.bvx=-this.bvx;}else if(this.bx>235){this.bx=235;this.bvx=-this.bvx;}
    if(this.bvy<0&&this.by-4>=34&&this.by-4<=44&&this.bx>=this.p1x&&this.bx<=this.p1x+44){this.by=49;this.bvy=-this.bvy;this.bounce(this.p1x);}
    else if(this.bvy>0&&this.by+4>=262&&this.by+4<=272&&this.bx>=this.p2x&&this.bx<=this.p2x+44){this.by=257;this.bvy=-this.bvy;this.bounce(this.p2x);}
    if(this.by<30){this.score(2);break;}if(this.by>276){this.score(1);break;}
   }
  }
  snapshot(){return{g:'pong',p1x:this.p1x,p2x:this.p2x,bx:this.bx,by:this.by,s1:this.s1,s2:this.s2,st:this.result|| (this.cd?4:0),cd:this.cd?Math.ceil(this.cd/24):0,pw:44,ph:6,br:4,p1y:38,p2y:262,win:5};}
 }
 root.TennisDemo=TennisDemo;if(typeof module!=='undefined'&&module.exports)module.exports=TennisDemo;
})(globalThis);
