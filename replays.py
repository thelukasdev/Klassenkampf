"""Bounded, chunked snapshot recordings. Authentication stays in WebAdmin."""
import asyncio
import hashlib
import gzip
import json
from pathlib import Path
import re
import secrets
import threading
import time

RETENTION=7*86400
MAX_STORAGE=256*1024*1024
MAX_RAW=16*1024*1024


class ReplayLibrary:
    def __init__(self,store,data_dir):
        self.store=store;self.root=(Path(data_dir)/'replays').resolve()
        self.root.mkdir(exist_ok=True);self.root.chmod(0o700);self.active={};self.tasks=set();self.lock=threading.RLock();self.last_cleanup=0
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS replays(id TEXT PRIMARY KEY,room_id TEXT NOT NULL,
                game TEXT NOT NULL,name TEXT NOT NULL,players TEXT NOT NULL,started INTEGER NOT NULL,
                ended INTEGER,duration REAL NOT NULL,frames INTEGER NOT NULL,segments TEXT NOT NULL,
                bytes INTEGER NOT NULL,truncated INTEGER NOT NULL,reason TEXT NOT NULL)''')
            db.execute('CREATE TABLE IF NOT EXISTS replay_shares(replay_id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS replays_room_started ON replays(room_id,started DESC) WHERE ended IS NOT NULL')
            db.execute('CREATE INDEX IF NOT EXISTS replays_ended ON replays(ended) WHERE ended IS NOT NULL')
            db.execute("UPDATE replays SET ended=?,truncated=1,reason='interrupted' WHERE ended IS NULL",(int(time.time()),))
        self.cleanup()

    def directory(self,rid):
        if not re.fullmatch(r'[0-9a-f]{32}',rid):raise ValueError('Replay nicht gefunden')
        path=(self.root/rid).resolve()
        if path.parent!=self.root:raise ValueError('Ungueltiger Pfad')
        return path

    def cleanup(self):
        with self.lock:
            now=int(time.time());self.last_cleanup=now
            with self.store.connect() as db:
                rows=db.execute('SELECT id,ended,bytes FROM replays WHERE ended IS NOT NULL ORDER BY started DESC,id').fetchall()
                total=0
                for row in rows:
                    total+=row['bytes']
                    if row['ended']<now-RETENTION or total>MAX_STORAGE:
                        path=self.directory(row['id'])
                        if path.exists():
                            for f in path.glob('*.json.gz'):f.unlink(missing_ok=True)
                            try:path.rmdir()
                            except OSError:pass
                        db.execute('DELETE FROM replay_shares WHERE replay_id=?',(row['id'],))
                        db.execute('DELETE FROM replays WHERE id=?',(row['id'],))

    def start(self,match):
        if not match.server.room_id or len(self.active)>=16:return None
        rid=secrets.token_hex(16);self.directory(rid).mkdir(mode=0o700)
        with self.store.connect() as db:
            db.execute('INSERT INTO replays VALUES(?,?,?,?,?,?,NULL,0,0,?,0,0,?)',
                       (rid,match.server.room_id,match.gid,match.name,json.dumps([p.nick for p in match.players]),int(time.time()),'[]','recording'))
        recorder=Recorder(self,rid,match);self.active[rid]=recorder;return recorder

    def metadata(self,room_id,rid=None):
        with self.store.connect() as db:
            if rid:
                rows=db.execute('SELECT *,EXISTS(SELECT 1 FROM replay_shares s WHERE s.replay_id=replays.id) AS shared FROM replays WHERE room_id=? AND id=? AND ended IS NOT NULL AND ended>=?',(room_id,rid,int(time.time())-RETENTION)).fetchall()
            else:rows=db.execute('SELECT *,EXISTS(SELECT 1 FROM replay_shares s WHERE s.replay_id=replays.id) AS shared FROM replays WHERE room_id=? AND ended IS NOT NULL AND ended>=? ORDER BY started DESC LIMIT 100',(room_id,int(time.time())-RETENTION)).fetchall()
        result=[]
        for row in rows:
            item=dict(row);item['players']=json.loads(item['players']);item['segments']=json.loads(item['segments']);result.append(item)
        return result[0] if rid and result else None if rid else result

    def chunk(self,room_id,rid,index):
        with self.lock:
            meta=self.metadata(room_id,rid)
            if not meta or not 0<=index<len(meta['segments']):raise ValueError('Replay nicht gefunden')
            with gzip.open(self.directory(rid)/(str(index)+'.json.gz'),'rb') as f:
                raw=f.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:raise ValueError('Replay zu gross')
            return json.loads(raw)

    def share(self,room_id,rid,revoke=False):
        with self.lock:
            if not self.metadata(room_id,rid):raise ValueError('Replay nicht gefunden')
            token=secrets.token_urlsafe(64)
            with self.store.connect() as db:
                db.execute('DELETE FROM replay_shares WHERE replay_id=?',(rid,))
                if not revoke:db.execute('INSERT INTO replay_shares VALUES(?,?)',(rid,hashlib.sha256(token.encode()).hexdigest()))
            return None if revoke else token

    def shared(self,token,index=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{86}',token):raise ValueError('Replay nicht verfügbar')
        with self.lock:
            with self.store.connect() as db:
                row=db.execute('SELECT r.room_id,r.id FROM replay_shares s JOIN replays r ON r.id=s.replay_id WHERE s.token_hash=?',
                               (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not row:raise ValueError('Replay nicht verfügbar')
            meta=self.metadata(row['room_id'],row['id'])
            if not meta:raise ValueError('Replay nicht verfügbar')
            if index is not None:return self.chunk(row['room_id'],row['id'],index)
            return {k:meta[k] for k in ('id','game','name','players','started','duration','segments','truncated','reason')}

    def track(self,task):
        self.tasks.add(task);task.add_done_callback(self.tasks.discard)

    async def drain(self):
        for rec in list(self.active.values()):rec.finish('interrupted')
        if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)


class Recorder:
    def __init__(self,library,rid,match):
        self.library=library;self.id=rid;self.match=match;self.buffer=[];self.raw=0;self.next=0
        self.queue=asyncio.Queue(maxsize=2);self.closed=False;self.truncated=False;self.reason='normal'
        self.last_t=None
        self.worker=asyncio.create_task(self.write_loop());library.track(self.worker)

    def capture(self,frame):
        if self.closed or frame['t']<self.next:return
        self.next=frame['t']+getattr(self.match.game,'replay_interval',.1)
        raw=json.dumps(frame,separators=(',',':')).encode()
        if self.raw+len(raw)>MAX_RAW:
            self.truncated=True;self.finish('limit');return
        self.raw+=len(raw);self.buffer.append(raw);self.last_t=frame['t']
        if len(self.buffer)>=getattr(self.match.game,'replay_batch',100):
            try:self.queue.put_nowait(self.buffer);self.buffer=[]
            except asyncio.QueueFull:self.truncated=True;self.buffer=[];self.finish('limit')

    def finish(self,reason):
        if self.closed:return
        if self.match.last_frame:
            frame={'t':max(self.last_t or 0,round(time.monotonic()-self.match.start_t,3)),'views':self.match.last_frame['views']}
            raw=json.dumps(frame,separators=(',',':')).encode()
            if self.raw+len(raw)<=MAX_RAW:self.buffer.append(raw);self.raw+=len(raw)
            else:self.truncated=True
        if reason in ('interrupted','storage_error','limit'):self.truncated=True
        self.closed=True;self.reason=reason
        async def flush():
            if self.buffer:await self.queue.put(self.buffer);self.buffer=[]
            await self.queue.put(None)
        task=asyncio.create_task(flush());self.library.track(task)

    def write(self,batch,index,segments,frames,total):
        path=self.library.directory(self.id)/(str(index)+'.json.gz')
        with gzip.open(path,'wb',compresslevel=3) as f:f.write(b'['+b','.join(batch)+b']')
        path.chmod(0o600)
        first=json.loads(batch[0]);last=json.loads(batch[-1]);segments.append({'index':index,'start':first['t'],'end':last['t'],'frames':len(batch)})
        frames+=len(batch);total+=path.stat().st_size
        with self.library.store.connect() as db:
            db.execute('UPDATE replays SET duration=?,frames=?,segments=?,bytes=? WHERE id=?',
                       (last['t'],frames,json.dumps(segments),total,self.id))
        return frames,total

    async def write_loop(self):
        segments=[];frames=total=0;index=0;failed=False
        try:
            while True:
                batch=await self.queue.get()
                if batch is None:break
                frames,total=await asyncio.to_thread(self.write,batch,index,segments,frames,total);index+=1
        except Exception:
            failed=True;self.truncated=True;self.closed=True;self.reason='storage_error'
        finally:
            # Drain bounded producers even if a disk write failed.
            if failed:
                while not self.queue.empty():self.queue.get_nowait()
            try:
                with self.library.store.connect() as db:
                    db.execute('UPDATE replays SET ended=?,truncated=?,reason=? WHERE id=?',
                               (int(time.time()),int(self.truncated),self.reason,self.id))
            finally:self.library.active.pop(self.id,None)
            await asyncio.to_thread(self.library.cleanup)
