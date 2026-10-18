"""Independent public monitor and durable incident timeline (stdlib only)."""
from contextlib import contextmanager
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit
import urllib.request

INTERVAL=15
STATES={'operational','standby','paused','degraded','down','unknown','ended'}
UP={'operational','standby','paused'}
DETAILS={'operational':'Erreichbar','standby':'Bereit, keine laufende Partie',
         'paused':'Durch Spielleitung pausiert','degraded':'Beeinträchtigt',
         'down':'Nicht erreichbar','unknown':'Keine verlässlichen Messdaten',
         'ended':'Sitzung beendet'}


class StatusStore:
    def __init__(self,path):
        self.path=str(path)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS components(id TEXT PRIMARY KEY,label TEXT NOT NULL,kind TEXT NOT NULL,
                    state TEXT NOT NULL,since INTEGER NOT NULL,checked INTEGER NOT NULL,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,time INTEGER NOT NULL,
                    component TEXT NOT NULL,state TEXT NOT NULL,detail TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_component ON events(component,id);
                CREATE TABLE IF NOT EXISTS daily(component TEXT NOT NULL,day TEXT NOT NULL,state TEXT NOT NULL,
                    seconds INTEGER NOT NULL,PRIMARY KEY(component,day,state));
            ''')
        os.chmod(self.path,0o600)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    @staticmethod
    def accrue(db,component,start,end,state):
        if state=='ended':return
        while start<end:
            day=time.strftime('%Y-%m-%d',time.gmtime(start))
            boundary=(start//86400+1)*86400
            until=min(end,boundary)
            db.execute('INSERT INTO daily VALUES(?,?,?,?) ON CONFLICT(component,day,state) DO UPDATE SET seconds=seconds+excluded.seconds',
                       (component,day,state,until-start))
            start=until

    def observe(self,components,now=None):
        now=int(time.time()) if now is None else int(now)
        # Every value comes from an explicit public allowlist, never from game state.
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO meta VALUES('started',?)",(str(now),))
            for item in components:
                cid=item['id'];state=item['state']
                if state not in STATES:raise ValueError('Invalid state')
                old=db.execute('SELECT * FROM components WHERE id=?',(cid,)).fetchone()
                since=now
                if old:
                    if now<old['checked']:raise ValueError('Clock moved backwards')
                    gap=now-old['checked']
                    if gap>INTERVAL*3 and old['state']!='ended':
                        cutoff=old['checked']+INTERVAL
                        self.accrue(db,cid,old['checked'],cutoff,old['state'])
                        self.accrue(db,cid,cutoff,now,'unknown')
                        db.execute('INSERT INTO events(time,component,state,detail) VALUES(?,?,?,?)',
                                   (cutoff,cid,'unknown','Überwachung unterbrochen; tatsächlicher Zustand unbekannt'))
                    else:
                        self.accrue(db,cid,old['checked'],now,old['state'])
                        if state==old['state']:since=old['since']
                    changed=state!=old['state'] or (gap>INTERVAL*3 and old['state']!='ended')
                else:changed=True
                if changed:
                    db.execute('INSERT INTO events(time,component,state,detail) VALUES(?,?,?,?)',
                               (now,cid,state,DETAILS[state] if old else 'Überwachung gestartet · '+DETAILS[state]))
                safe={k:item[k] for k in ('online','matches','latency_ms') if k in item}
                db.execute('INSERT INTO components VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,state=excluded.state,since=excluded.since,checked=excluded.checked,data=excluded.data',
                           (cid,item['label'],item['kind'],state,since,now,json.dumps(safe)))
            db.execute("INSERT OR REPLACE INTO meta VALUES('checked',?)",(str(now),))

    def previous_sessions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,label,kind,state FROM components WHERE kind='session'")]

    def read(self,days=90,before=None,component=None,now=None):
        now=int(time.time()) if now is None else int(now)
        with self.connect() as db:
            meta={r['key']:int(r['value']) for r in db.execute('SELECT * FROM meta')}
            checked=meta.get('checked',0);stale=not checked or now-checked>INTERVAL*3
            rows=[dict(r) for r in db.execute("SELECT * FROM components ORDER BY CASE kind WHEN 'service' THEN 0 ELSE 1 END,id")]
            recorded_states={r['id']:r['state'] for r in rows}
            for row in rows:
                row.update(json.loads(row.pop('data')))
                if stale and row['state']!='ended':row['state']='unknown'
            params=[];where=[]
            if before is not None:
                when,eid=before
                where.append('(e.time<? OR (e.time=? AND e.id<?))');params.extend((when,when,eid))
            if component:where.append('e.component=?');params.append(component)
            sql='SELECT e.*,c.label FROM events e JOIN components c ON c.id=e.component'
            if where:sql+=' WHERE '+' AND '.join(where)
            events=[dict(r) for r in db.execute(sql+' ORDER BY e.time DESC,e.id DESC LIMIT 51',params)]
            more=len(events)>50;events=events[:50]
            since=time.strftime('%Y-%m-%d',time.gmtime(now-(days-1)*86400))
            daily=[dict(r) for r in db.execute('SELECT * FROM daily WHERE day>=? ORDER BY day,component,state',(since,))]
            # Include the current interval without writing from a public GET request.
            for row in rows:
                if recorded_states[row['id']]=='ended':continue
                cutoff=min(now,row['checked']+INTERVAL) if stale else now
                intervals=[(row['checked'],cutoff,recorded_states[row['id']])]
                if stale:intervals.append((cutoff,now,'unknown'))
                for start,end,state in intervals:
                    start=max(start,(now//86400-days+1)*86400)
                    while start<end:
                        until=min(end,(start//86400+1)*86400)
                        daily.append({'component':row['id'],'day':time.strftime('%Y-%m-%d',time.gmtime(start)),
                                      'state':state,'seconds':until-start})
                        start=until
        return {'started':meta.get('started'),'checked':checked,'now':now,'interval':INTERVAL,'stale':stale,
                'components':rows,'daily':daily,'events':events,'next':str(events[-1]['time'])+':'+str(events[-1]['id']) if more else None}


def websocket_probe(target,origin):
    url=urlsplit(target)
    key=base64.b64encode(os.urandom(16)).decode()
    accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    with socket.create_connection((url.hostname,url.port or 80),timeout=3) as sock:
        sock.sendall(('GET / HTTP/1.1\r\nHost: '+url.netloc+'\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Origin: '+origin+'\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '+key+'\r\n\r\n').encode())
        data=b''
        while b'\r\n\r\n' not in data and len(data)<16384:
            chunk=sock.recv(4096)
            if not chunk:break
            data+=chunk
        headers=data.split(b'\r\n\r\n',1)[0].decode('latin1')
        return headers.startswith('HTTP/1.1 101 ') and ('sec-websocket-accept: '+accept).lower() in headers.lower()


def probe(store,target,token,origin,check_public=False):
    start=time.monotonic();payload=None
    try:
        with urllib.request.urlopen(target+'/healthz',timeout=3) as response:
            if response.status!=200 or response.read(32)!=b'ok':raise ValueError('Invalid health response')
        http='operational'
    except Exception:http='down'
    latency=round((time.monotonic()-start)*1000)
    try:
        if http!='operational':raise ValueError('HTTP unavailable')
        req=urllib.request.Request(target+'/internal/status.json',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=3) as response:payload=json.loads(response.read(512*1024))
        if payload.get('version')!=1:raise ValueError('Unknown feed')
    except Exception:payload=None
    try:ws='operational' if websocket_probe(target,origin) else 'down'
    except Exception:ws='down'
    edge=[]
    if check_public:
        start=time.monotonic()
        try:
            with urllib.request.urlopen(origin+'/healthz',timeout=3) as response:
                reachable=response.status==200 and response.read(32)==b'ok'
            edge_state='operational' if reachable else 'down'
        except Exception:edge_state='down'
        edge=[{'id':'https','label':'Öffentlicher HTTPS-Zugang','kind':'service',
               'state':edge_state,'latency_ms':round((time.monotonic()-start)*1000)}]
    database=payload['database'] if payload else 'unknown'
    sessions=payload.get('sessions',[]) if payload and database=='operational' else [
        {**r,'state':'ended' if r['state']=='ended' else 'down' if http=='down' else 'unknown'} for r in store.previous_sessions()]
    logins=[]
    for cid,label,path,needs_mail in (
        ('player-login','Spieleranmeldung','/auth/player/csrf',True),
        ('admin-login','Verwaltungsanmeldung','/auth/password/csrf',False),
    ):
        start=time.monotonic()
        try:
            if http!='operational':raise ValueError('HTTP unavailable')
            with urllib.request.urlopen(target+path,timeout=3) as response:
                if response.status!=200:raise ValueError('Invalid login response')
                result=json.loads(response.read(16384))
            if not isinstance(result.get('csrf'),str) or len(result['csrf'])<24:raise ValueError('Invalid login response')
            state='operational' if database=='operational' and (not needs_mail or result.get('ready') is True) else 'degraded'
        except Exception:state='down'
        logins.append({'id':cid,'label':label,'kind':'service','state':state,
                       'latency_ms':round((time.monotonic()-start)*1000)})
    platform='down' if http=='down' else 'degraded' if ws!='operational' or database!='operational' or any(s['state']=='degraded' for s in sessions) or any(e['state']=='down' for e in edge) or any(c['state']!='operational' for c in logins) else 'operational'
    return [{'id':'platform','label':'Gesamtsystem','kind':'service','state':platform},
            {'id':'http','label':'Spielserver · HTTP','kind':'service','state':http,'latency_ms':latency},
            {'id':'websocket','label':'Spielverbindungen · WebSocket','kind':'service','state':ws},
            {'id':'database','label':'Spielstandspeicher','kind':'service','state':database},
            {'id':'monitor','label':'Statusüberwachung','kind':'service','state':'operational'},*edge,*logins,*sessions]


def make_handler(store,static_dir):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_HEAD(self):self.do_GET()
        def do_GET(self):
            route=urlsplit(self.path)
            try:
                if route.path=='/api/status':
                    query=parse_qs(route.query)
                    days=int(query.get('days',['90'])[0]);before=query.get('before',[None])[0];component=query.get('component',[None])[0]
                    if not 1<=days<=90:raise ValueError()
                    if before is not None:
                        if not re.fullmatch(r'[0-9]{1,12}:[0-9]{1,18}',before):raise ValueError()
                        before=tuple(map(int,before.split(':')))
                    if component and not re.fullmatch(r'[a-z0-9-]{1,40}',component):raise ValueError()
                    body=json.dumps(store.read(days,before,component),ensure_ascii=False).encode();ctype='application/json; charset=utf-8'
                elif route.path=='/status/healthz':
                    with store.connect() as db:db.execute('SELECT 1').fetchone()
                    body=b'ok';ctype='text/plain'
                else:
                    files={'/status':'status.html','/status/':'status.html','/status/status.css':'status.css',
                           '/status/cookie-notice.js':'cookie-notice.js','/status/cookie-notice.css':'cookie-notice.css',
                           '/status/status.js':'status.js','/status/lp-logo.png':'lp-logo.png'}
                    if route.path not in files:self.reply(404,b'Not found','text/plain');return
                    name=files[route.path];body=(static_dir/name).read_bytes()
                    ctype={'html':'text/html; charset=utf-8','css':'text/css; charset=utf-8','js':'application/javascript; charset=utf-8','png':'image/png'}[name.rsplit('.',1)[1]]
                self.reply(200,body,ctype)
            except (ValueError,TypeError):self.reply(400,b'Invalid query','text/plain')
            except Exception:self.reply(503,b'Status temporarily unavailable','text/plain')
        def reply(self,status,body,ctype):
            self.send_response(status);self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            if self.command!='HEAD':self.wfile.write(body)
    return Handler


def main():
    store=StatusStore(Path(os.environ.get('STATUS_DATA_DIR','/data'))/'status.sqlite3')
    target=os.environ.get('STATUS_TARGET','http://app:8080').rstrip('/')
    token=os.environ.get('KLASSENKAMPF_STATUS_TOKEN','')
    origin=os.environ.get('STATUS_PUBLIC_ORIGIN','')
    stop=threading.Event()
    def poll():
        while not stop.is_set():
            start=time.monotonic()
            try:store.observe(probe(store,target,token,origin,check_public=True))
            except Exception:print('Status sample could not be persisted',flush=True)
            stop.wait(max(.1,INTERVAL-(time.monotonic()-start)))
    worker=threading.Thread(target=poll,daemon=True);worker.start()
    server=ThreadingHTTPServer(('0.0.0.0',8081),make_handler(store,Path(__file__).with_name('static')))
    server.daemon_threads=True;server.timeout=.5
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    print('Public status monitor listening on :8081',flush=True)
    while not stop.is_set():server.handle_request()
    server.server_close();worker.join(timeout=8)


if __name__=='__main__':main()
