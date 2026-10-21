"""Account-owned support tickets with administrator replies and email notifications."""
import asyncio
import hashlib
import json
import re
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit,parse_qs
import secrets
import time

PAGES={'/','/login','/account','/account/manage','/account/security','/admin','/watch','/status','/report'}


class Reports:
    COOKIE='__Host-kk_report'

    def __init__(self,web):
        self.web=web;self.store=web.store;self.sending=set()
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS issue_reports(
                id INTEGER PRIMARY KEY,reference TEXT UNIQUE NOT NULL,created INTEGER NOT NULL,
                page TEXT NOT NULL,description TEXT NOT NULL,resolved INTEGER NOT NULL DEFAULT 0,resolved_at INTEGER)''')

            if 'resolved_at' not in {r['name'] for r in db.execute('PRAGMA table_info(issue_reports)')}:
                db.execute('ALTER TABLE issue_reports ADD COLUMN resolved_at INTEGER')
            columns={r['name'] for r in db.execute('PRAGMA table_info(issue_reports)')}
            for column,kind in [('owner','TEXT'),('last_activity','INTEGER')]:
                if column not in columns:db.execute('ALTER TABLE issue_reports ADD COLUMN '+column+' '+kind)
            db.execute('''CREATE TABLE IF NOT EXISTS report_messages(
                id INTEGER PRIMARY KEY,report_id INTEGER NOT NULL,author TEXT NOT NULL,kind TEXT NOT NULL,
                body TEXT NOT NULL,created INTEGER NOT NULL,request_id TEXT NOT NULL,mail_status TEXT NOT NULL,mail_attempt INTEGER,
                UNIQUE(report_id,author,request_id))''')
            db.execute('CREATE INDEX IF NOT EXISTS issue_reports_owner ON issue_reports(owner,id)')
            db.execute('CREATE INDEX IF NOT EXISTS report_messages_ticket ON report_messages(report_id,id)')
            db.execute('CREATE INDEX IF NOT EXISTS issue_reports_activity ON issue_reports(COALESCE(last_activity,created) DESC,id DESC)')
            db.execute('CREATE INDEX IF NOT EXISTS issue_reports_state_activity ON issue_reports(resolved,COALESCE(last_activity,created) DESC,id DESC)')
            # Existing completed reports start their 30-day window at migration.
            db.execute('UPDATE issue_reports SET resolved_at=? WHERE resolved=1 AND resolved_at IS NULL',(int(time.time()),))

    def session(self,headers):
        player=self.web.player_auth.session(headers)
        if player:return player
        admin=self.store.session(self.web.cookie(headers,self.web.COOKIE))
        return admin if admin and admin['role'] in ('owner','admin','guide') else None

    async def handle(self,reader,writer,method,route,headers):
        w=self.web;query=parse_qs(urlsplit(route).query);route=urlsplit(route).path
        actor=self.session(headers)
        if not actor:
            await w.respond(writer,401,{'error':'Bitte anmelden.'});return
        if route=='/auth/report/csrf' and method=='GET':
            csrf=secrets.token_urlsafe(32)
            await w.respond(writer,200,{'csrf':csrf},cookie=(self.COOKIE,csrf,900));return
        if route=='/auth/report/mine' and method=='GET':
            await w.respond(writer,200,self.mine(actor,query));return
        if route.startswith('/auth/report/ticket/') and method=='GET':
            await w.respond(writer,200,self.detail(actor,route.rsplit('/',1)[-1],query));return
        if route not in ('/auth/report/submit','/auth/report/reply') or method!='POST':
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
        actor=self.session(headers)
        if not actor:
            await w.respond(writer,401,{'error':'Bitte erneut anmelden.'});return
        if route=='/auth/report/reply':
            result=await self.reply(actor,obj.get('reference'),obj.get('message'),obj.get('request_id'),admin=False)
            await w.respond(writer,200,result);return
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
            db.execute('INSERT INTO issue_reports(reference,created,page,description,owner,last_activity) VALUES(?,?,?,?,?,?)',
                       (reference,int(time.time()),page,description.strip(),actor['email'],int(time.time())))
        await w.respond(writer,200,{'reference':reference,'url':'/tickets/'+reference})

    def list(self,actor,query):
        from web_admin import Denied
        if actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen Fehlermeldungen sehen.')
        search=str(query.get('q',[''])[0]).strip().upper();state=query.get('state',['open'])[0]
        before=str(query.get('before',[''])[0])
        if len(search)>40 or state not in ('open','resolved','all') or (before and not re.fullmatch(r'[0-9]{1,12}:[0-9]{1,18}',before)):raise ValueError('Ungültiger Filter.')
        sql='SELECT id,reference,created,page,description,resolved,COALESCE(last_activity,created) AS activity FROM issue_reports WHERE instr(reference,?)>0';params=[search]
        if state!='all':sql+=' AND resolved=?';params.append(int(state=='resolved'))
        if before:
            stamp,rid=map(int,before.split(':'));sql+=' AND (COALESCE(last_activity,created)<? OR (COALESCE(last_activity,created)=? AND id<?))';params.extend([stamp,stamp,rid])
        with self.store.connect() as db:rows=[dict(r) for r in db.execute(sql+' ORDER BY activity DESC,id DESC LIMIT 26',params)]
        next_cursor=str(rows[24]['activity'])+':'+str(rows[24]['id']) if len(rows)>25 else None
        for row in rows:row.pop('activity')
        return {'reports':rows[:25],'next':next_cursor}

    def resolve(self,actor,reference,resolved):
        from web_admin import Denied
        if actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen Fehlermeldungen bearbeiten.')
        if type(resolved) is not bool:raise ValueError('Ungültiger Status.')
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM issue_reports WHERE reference=?',(reference,)).fetchone():raise ValueError('Meldung nicht gefunden.')
            db.execute('UPDATE issue_reports SET resolved=?,resolved_at=CASE WHEN ?=0 THEN NULL WHEN resolved=0 THEN ? ELSE resolved_at END WHERE reference=?',(int(resolved),int(resolved),int(time.time()),reference))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',
                       (int(time.time()),actor['email'],'resolve-report',reference+' '+str(resolved)))

    def ticket(self,actor,reference):
        from web_admin import Denied
        if not isinstance(reference,str) or not re.fullmatch(r'KK-[A-F0-9]{12}',reference):raise ValueError('Ticket nicht gefunden.')
        with self.store.connect() as db:row=db.execute('SELECT * FROM issue_reports WHERE reference=?',(reference,)).fetchone()
        if not row or (actor['role'] not in ('owner','admin') and row['owner']!=actor['email']):raise Denied('Ticket nicht verfügbar.')
        return dict(row)

    def detail(self,actor,reference,query=None):
        row=self.ticket(actor,reference);before=int((query or {}).get('before',['0'])[0])
        if before<0:raise ValueError('Ungültiger Verlauf.')
        sql='SELECT id,kind,body,created,mail_status FROM report_messages WHERE report_id=?';args=[row['id']]
        if before:sql+=' AND id<?';args.append(before)
        with self.store.connect() as db:messages=[dict(r) for r in db.execute(sql+' ORDER BY id DESC LIMIT 101',args)]
        is_admin=actor['role'] in ('owner','admin')
        if not is_admin:
            for message in messages:message.pop('mail_status',None)
        return {'ticket':{'reference':row['reference'],'page':row['page'],'description':row['description'],
                'created':row['created'],'resolved':bool(row['resolved']),'replyable':bool(row['owner']),
                'owner':row['owner'] if is_admin else None},'messages':list(reversed(messages[:100])),
                'next':messages[99]['id'] if len(messages)>100 else None}

    def mine(self,actor,query):
        before=int(query.get('before',['0'])[0])
        if before<0:raise ValueError('Ungültiger Verlauf.')
        sql='SELECT id,reference,created,resolved FROM issue_reports WHERE owner=?';args=[actor['email']]
        if before:sql+=' AND id<?';args.append(before)
        with self.store.connect() as db:rows=[dict(r) for r in db.execute(sql+' ORDER BY id DESC LIMIT 26',args)]
        return {'tickets':rows[:25],'next':rows[24]['id'] if len(rows)>25 else None}

    async def reply(self,actor,reference,message,request_id,admin=True):
        from web_admin import Denied
        if admin and actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen antworten.')
        ticket=self.ticket(actor,reference)
        if not admin and ticket['owner']!=actor['email']:raise Denied('Ticket nicht verfügbar.')
        if not ticket['owner']:raise ValueError('Diese ältere Meldung ist keinem Konto zugeordnet.')
        if not isinstance(message,str) or not 1<=len(message.strip())<=2000:raise ValueError('Bitte 1 bis 2000 Zeichen eingeben.')
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{20,64}',request_id):raise ValueError('Ungültige Nachrichtenkennung.')
        now=int(time.time());identity=actor['email'];kind='admin' if admin else 'player'
        with self.store.connect() as db:
            existing=db.execute('SELECT id,body FROM report_messages WHERE report_id=? AND author=? AND request_id=?',(ticket['id'],identity,request_id)).fetchone()
        if existing:
            if existing['body']!=message.strip():raise ValueError('Nachrichtenkennung bereits verwendet.')
            return {'message_id':existing['id'],'notice':'Antwort bereits gespeichert.'}
        self.web.player_auth.hit('ticket-reply:'+identity,30,3600)
        self.web.player_auth.hit('ticket-reply:global',300,3600)
        with self.store.connect() as db:
            # Recheck ownership/account after rate-limit I/O, before persisting.
            current=db.execute('SELECT owner FROM issue_reports WHERE id=?',(ticket['id'],)).fetchone()
            if not current or current['owner']!=ticket['owner']:raise Denied('Ticket nicht verfügbar.')
            result=db.execute('INSERT INTO report_messages(report_id,author,kind,body,created,request_id,mail_status) VALUES(?,?,?,?,?,?,?)',
                (ticket['id'],identity,kind,message.strip(),now,request_id,'pending' if admin else 'not_required'))
            mid=result.lastrowid
            db.execute('UPDATE issue_reports SET last_activity=?,resolved=0,resolved_at=NULL WHERE id=?',(now,ticket['id']))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',(now,identity,'reply-report',reference))
        status=await self.notify(actor,reference,mid) if admin else 'not_required'
        return {'message_id':mid,'mail_status':status,'notice':'Antwort gespeichert und E-Mail versendet.' if status=='sent' else 'Antwort gespeichert. E-Mail konnte nicht versendet werden; bitte erneut senden.' if admin else 'Antwort gespeichert.'}

    def send_notification(self,email,reference,message):
        msg=EmailMessage();msg['From']=os.environ['SMTP_FROM'];msg['To']=email
        msg['Subject']='Klassenkampf: Antwort auf Ticket '+reference
        msg.set_content('Neue Antwort auf dein Ticket '+reference+':\n\n'+message+'\n\nTicket öffnen und antworten:\n'+self.web.origin+'/tickets/'+reference+'\n\nBitte mit deinem zugehörigen Konto anmelden. Antworten direkt auf diese E-Mail werden nicht dem Ticket zugeordnet.')
        port=int(os.environ.get('SMTP_PORT','465'));host=os.environ['SMTP_HOST']
        if port==465:connection=smtplib.SMTP_SSL(host,port,timeout=12,context=ssl.create_default_context())
        else:
            connection=smtplib.SMTP(host,port,timeout=12);connection.ehlo();connection.starttls(context=ssl.create_default_context());connection.ehlo()
        with connection as smtp:
            smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);smtp.send_message(msg)

    async def notify(self,actor,reference,message_id):
        from web_admin import Denied
        if actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen E-Mails senden.')
        ticket=self.ticket(actor,reference)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            message=db.execute("SELECT * FROM report_messages WHERE id=? AND report_id=? AND kind='admin'",(int(message_id),ticket['id'])).fetchone()
            if not message or not ticket['owner']:raise ValueError('Antwort nicht gefunden.')
            if message['id'] in self.sending:return 'sending'
            if message['mail_status']=='sent' or (message['mail_status']=='sending' and (message['mail_attempt'] or 0)>time.time()-120):return message['mail_status']
            db.execute("UPDATE report_messages SET mail_status='sending',mail_attempt=? WHERE id=?",(int(time.time()),message['id']))
        self.sending.add(message['id'])
        email=ticket['owner'].removeprefix('player:')
        try:
            self.web.player_auth.hit('ticket-mail:global',100,3600)
            async with self.web.player_auth.mail_slots:await asyncio.to_thread(self.send_notification,email,reference,message['body'])
            status='sent'
        except Exception:status='failed'
        finally:self.sending.discard(message['id'])
        with self.store.connect() as db:db.execute('UPDATE report_messages SET mail_status=? WHERE id=?',(status,message['id']))
        return status
