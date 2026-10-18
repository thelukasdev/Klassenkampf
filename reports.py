"""Manual issue reports, private to administrators; no cookies or query strings stored."""
import asyncio
import hashlib
import json
import secrets
import time

PAGES={'/','/login','/account','/account/manage','/account/security','/admin','/watch','/status','/report'}


class Reports:
    COOKIE='__Host-kk_report'

    def __init__(self,web):
        self.web=web;self.store=web.store
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS issue_reports(
                id INTEGER PRIMARY KEY,reference TEXT UNIQUE NOT NULL,created INTEGER NOT NULL,
                page TEXT NOT NULL,description TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0)''')

    def session(self,headers):
        player=self.web.player_auth.session(headers)
        if player:return player
        admin=self.store.session(self.web.cookie(headers,self.web.COOKIE))
        return admin if admin and admin['role'] in ('owner','admin','guide') else None

    async def handle(self,reader,writer,method,route,headers):
        w=self.web
        if not self.session(headers):
            await w.respond(writer,401,{'error':'Bitte anmelden.'});return
        if route=='/auth/report/csrf' and method=='GET':
            csrf=secrets.token_urlsafe(32)
            await w.respond(writer,200,{'csrf':csrf},cookie=(self.COOKIE,csrf,900));return
        if route!='/auth/report/submit' or method!='POST':
            await w.respond(writer,404,{'error':'Nicht gefunden'});return
        from web_admin import Denied
        csrf=w.cookie(headers,self.COOKIE)
        if not csrf or headers.get('origin')!=w.origin or not secrets.compare_digest(csrf.encode(),headers.get('x-csrf-token','').encode()):
            raise Denied('Seite bitte neu laden.')
        if headers.get('transfer-encoding') or headers.get('content-type','').split(';')[0]!='application/json':raise ValueError('JSON erforderlich.')
        length=int(headers.get('content-length','0'))
        if not 0<length<=12000:raise ValueError('Anfrage zu groß.')
        obj=json.loads(await asyncio.wait_for(reader.readexactly(length),5))
        if not isinstance(obj,dict):raise ValueError('Ungültige Anfrage.')
        page=obj.get('page','/');description=obj.get('description','')
        if not isinstance(page,str) or page not in PAGES:raise ValueError('Ungültige Seite.')
        if not isinstance(description,str) or not 10<=len(description.strip())<=2000:raise ValueError('Bitte 10 bis 2000 Zeichen eingeben.')
        ip=headers.get('x-forwarded-for','local').split(',')[-1].strip()
        w.player_auth.hit('report:'+hashlib.sha256(ip.encode()).hexdigest(),5,900)
        w.player_auth.hit('report:global',100,3600)
        if not self.session(headers):
            await w.respond(writer,401,{'error':'Bitte erneut anmelden.'});return
        reference='KK-'+secrets.token_hex(6).upper()
        with self.store.connect() as db:
            db.execute('INSERT INTO issue_reports(reference,created,page,description) VALUES(?,?,?,?)',
                       (reference,int(time.time()),page,description.strip()))
        await w.respond(writer,200,{'reference':reference})

    def list(self,actor,query):
        from web_admin import Denied
        if actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen Fehlermeldungen sehen.')
        search=str(query.get('q',[''])[0]).strip().upper();state=query.get('state',['open'])[0]
        before=int(query.get('before',['0'])[0])
        if len(search)>40 or before<0 or state not in ('open','resolved','all'):raise ValueError('Ungültiger Filter.')
        sql='SELECT * FROM issue_reports WHERE instr(reference,?)>0';params=[search]
        if state!='all':sql+=' AND resolved=?';params.append(int(state=='resolved'))
        if before:sql+=' AND id<?';params.append(before)
        with self.store.connect() as db:rows=[dict(r) for r in db.execute(sql+' ORDER BY id DESC LIMIT 26',params)]
        return {'reports':rows[:25],'next':rows[24]['id'] if len(rows)>25 else None}

    def resolve(self,actor,reference,resolved):
        from web_admin import Denied
        if actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen Fehlermeldungen bearbeiten.')
        if type(resolved) is not bool:raise ValueError('Ungültiger Status.')
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM issue_reports WHERE reference=?',(reference,)).fetchone():raise ValueError('Meldung nicht gefunden.')
            db.execute('UPDATE issue_reports SET resolved=? WHERE reference=?',(int(resolved),reference))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',
                       (int(time.time()),actor['email'],'resolve-report',reference+' '+str(resolved)))
