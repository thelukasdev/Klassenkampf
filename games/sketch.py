"""Private, authoritative drawing and guessing rounds for 4–8 participants."""
import base64
import math
import random
import unicodedata
from .base import Game

WORDS=('Apfel Banane Birne Erdbeere Ananas Zitrone Karotte Tomate Kartoffel Brokkoli '
       'Hund Katze Maus Pferd Elefant Giraffe Zebra Pinguin Delfin Schmetterling '
       'Biene Schnecke Schildkröte Krokodil Frosch Eule Fisch Krabbe Spinne Marienkäfer '
       'Haus Burg Brücke Leuchtturm Zelt Iglu Kirche Windmühle Schule Krankenhaus '
       'Auto Fahrrad Flugzeug Hubschrauber Segelboot Rakete Zug Bus Traktor U-Boot '
       'Sonne Mond Stern Wolke Regenbogen Blitz Schneemann Vulkan Insel Berg '
       'Baum Blume Palme Kaktus Pilz Blatt Tannenbaum Lagerfeuer Wasserfall Strand '
       'Gitarre Trommel Klavier Trompete Mikrofon Kopfhörer Kamera Fernseher Roboter Computer '
       'Schlüssel Schere Hammer Regenschirm Brille Uhr Kerze Ballon Geschenk Krone '
       'Pizza Hamburger Eis Torte Brezel Spiegelei Käse Wassermelone Popcorn Lutscher '
       'Fußball Basketball Tennisschläger Skateboard Schlitten Schaukel Rutsche Leiter Zahnbürste Badewanne').split()
COLORS=8
MAX_SEGMENTS=1024
DRAW_MS=60000
REVEAL_MS=5000


def normalize(text):
    text=text.casefold().replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss')
    return ''.join(c for c in unicodedata.normalize('NFKD',text) if c.isalnum())


def clean_event(obj):
    if not isinstance(obj,dict):return None
    turn=obj.get('turn');seq=obj.get('seq');op=obj.get('op')
    if type(turn) is not int or not 1<=turn<=8 or type(seq) is not int or not 1<=seq<=10000000:return None
    result={'turn':turn,'seq':seq,'op':op}
    if op=='draw':
        segments=obj.get('segments')
        if not isinstance(segments,list) or not 1<=len(segments)<=8:return None
        for segment in segments:
            if not isinstance(segment,list) or len(segment)!=6 or any(type(v) is not int for v in segment):return None
            x,y,xx,yy,color,width=segment
            if not (0<=x<=255 and 0<=xx<=255 and 0<=y<=159 and 0<=yy<=159 and 0<=color<COLORS and 1<=width<=8):return None
        result['segments']=[list(segment) for segment in segments]
    elif op=='guess':
        value=obj.get('text')
        if not isinstance(value,str) or not 1<=len(value.strip())<=40 or any(ord(c)<32 for c in value):return None
        result['text']=value.strip()
    elif op!='clear':return None
    return result


class Sketch(Game):
    gid='sketch'
    name='Zeichnen & Raten'
    min_players=4
    max_players=8
    per_view=True
    tick_ms=150
    manual_start=True
    speed_fixed=True
    replay_interval=1.0
    replay_batch=10

    def __init__(self,n=4):
        if type(n) is not int or not self.min_players<=n<=self.max_players:raise ValueError('Zeichnen & Raten braucht 4 bis 8 Spieler.')
        super().__init__(n)
        self.alive=set(range(1,n+1));self.order=list(self.alive);random.shuffle(self.order)
        self.words=random.sample(WORDS,n);self.scores={p:0 for p in self.alive};self.played=set();self.index=-1
        self.turn=0;self.clock=0;self.chat=[];self.chat_id=0;self.revision=0
        self._next_turn()

    def _next_turn(self):
        self.index+=1
        while self.index<len(self.order) and self.order[self.index] not in self.alive:self.index+=1
        if self.index>=len(self.order):
            self.phase='finished';top=max(self.scores[p] for p in self.alive);leaders=[p for p in self.alive if self.scores[p]==top]
            self.finish('p'+str(leaders[0]) if len(leaders)==1 else 'draw');return
        self.drawer=self.order[self.index];self.played.add(self.drawer);self.word=self.words[self.index]
        self.turn+=1;self.phase='draw';self.until=self.clock+DRAW_MS;self.guessed=set();self.ink=bytearray();self.encoded='';self.revision+=1
        self.ack={p:0 for p in range(1,self.n+1)};self.feedback={p:'' for p in self.ack};self.last_guess={};self.windows={}
        self.chat=[]

    def _reveal(self):
        if self.phase=='draw':self.phase='reveal';self.until=self.clock+REVEAL_MS

    def _chat(self,p,text,kind):
        self.chat_id+=1;self.chat.append({'id':self.chat_id,'p':p,'text':text,'kind':kind});self.chat=self.chat[-24:]

    def handle_event(self,p,obj):
        obj=clean_event(obj)
        if not obj or p not in self.alive or self.phase!='draw' or obj['turn']!=self.turn or obj['seq']<=self.ack[p]:return
        op=obj['op']
        if op in ('draw','clear'):
            if p!=self.drawer:return
            start,count=self.windows.get(p,(self.clock,0))
            if self.clock-start>=1000:start,count=self.clock,0
            if count>=25:return
            self.windows[p]=(start,count+1)
            if op=='clear':self.ink.clear()
            else:
                if len(self.ink)//5+len(obj['segments'])>MAX_SEGMENTS:
                    self.feedback[p]='Zeichenfläche voll. Bitte leeren.';self.ack[p]=obj['seq'];return
                for x,y,xx,yy,color,width in obj['segments']:self.ink.extend((x,y,xx,yy,color*8+width-1))
            self.encoded=base64.b64encode(self.ink).decode('ascii');self.revision+=1;self.ack[p]=obj['seq'];self.feedback[p]=''
        elif op=='guess':
            if p==self.drawer or p in self.guessed:return
            self.ack[p]=obj['seq']
            if self.clock-self.last_guess.get(p,-1000)<1000:self.feedback[p]='Bitte kurz warten.';return
            self.last_guess[p]=self.clock;text=obj['text'];answer=normalize(text);target=normalize(self.word)
            if answer==target:
                self.guessed.add(p);self.scores[p]+=100+max(0,math.ceil((self.until-self.clock)/1000));self.scores[self.drawer]+=50
                self.feedback[p]='Richtig geraten!';self._chat(p,'hat richtig geraten!','correct')
                if self.guessed>=self.alive-{self.drawer}:self._reveal()
            elif target in answer:self.feedback[p]='Bitte nur den gesuchten Begriff eingeben.'
            else:self.feedback[p]='';self._chat(p,text,'guess')

    def _step(self):
        if self.result is not None:return
        self.clock+=self.tick_ms
        if self.clock>=self.until:
            if self.phase=='draw':self._reveal()
            elif self.phase=='reveal':self._next_turn()

    def remove_player(self,p):
        self.alive.discard(p)
        if len(self.alive)<self.min_players:self.phase='finished';self.finish('draw');return
        if self.phase=='draw' and (p==self.drawer or self.guessed>=self.alive-{self.drawer}):self._reveal()

    def snapshot(self,view=None):
        if view not in self.ack:raise ValueError('Private Spieleransicht erforderlich.')
        return {'g':self.gid,'phase':self.phase,'turn':self.turn,'total':sum(p in self.alive or p in self.played for p in self.order),
                'drawer':self.drawer,'seconds':max(0,math.ceil((self.until-self.clock)/1000)),
                'word':self.word if view==self.drawer or self.phase!='draw' else None,
                'hint':' '.join('_' if c.isalpha() else c for c in self.word),
                'drawing':self.encoded,'revision':self.revision,'chat':list(self.chat),
                'scores':dict(self.scores),'alive':sorted(self.alive),'guessed':sorted(self.guessed),
                'ack':self.ack[view],'feedback':self.feedback[view],'limit':len(self.ink)//5>=MAX_SEGMENTS}

    def console_stat(self):return 'Runde '+str(self.turn)+'/'+str(self.n)
