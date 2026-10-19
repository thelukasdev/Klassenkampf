"""Player accounts: verified registration, password login and email password recovery."""
import asyncio
from email.message import EmailMessage
from email.utils import parseaddr
import hashlib
import json
import os
import secrets
import smtplib
import ssl
import time
from password_auth import PasswordAuth
from web_admin import Denied


class PlayerAuth:
    COOKIE='__Host-kk_player'
    CSRF='__Host-kk_player_login'
    PENDING='__Host-kk_player_pending'
    RESET='__Host-kk_player_reset'

    def __init__(self,web):
        self.web=web;self.store=web.store;self.slots=asyncio.Semaphore(2);self.mail_slots=asyncio.Semaphore(2)
        from player_permissions import PlayerPermissions
        self.permissions=PlayerPermissions(self.store)
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS player_accounts(email TEXT PRIMARY KEY,hash TEXT NOT NULL,created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS player_codes(token TEXT PRIMARY KEY,email TEXT NOT NULL,hash TEXT NOT NULL,
                    password TEXT,expires INTEGER NOT NULL,attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS player_resets(token TEXT PRIMARY KEY,email TEXT NOT NULL,hash TEXT NOT NULL,
                    expires INTEGER NOT NULL,attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS player_limits(key TEXT PRIMARY KEY,started INTEGER NOT NULL,count INTEGER NOT NULL);
            ''')

    @property
    def ready(self):return all(os.environ.get(k) for k in ('SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM'))

    def session(self,headers):
        row=self.store.session(self.web.cookie(headers,self.COOKIE))
        if row and row['role']=='host' and row['email'].startswith('player:'):
            row['display_email']=row['email'][7:];row['permissions']=self.permissions.get(row['email']);return row
        return None

    def hit(self,key,limit,window):
        now=int(time.time())
        with self.store.connect() as db:
            db.execute('DELETE FROM player_limits WHERE started<?',(now-86400,))
            row=db.execute('SELECT * FROM player_limits WHERE key=?',(key,)).fetchone()
            if not row or row['started']<=now-window:db.execute('INSERT OR REPLACE INTO player_limits VALUES(?,?,1)',(key,now))
            elif row['count']>=limit:raise ValueError('Zu viele Versuche. Bitte später erneut versuchen.')
            else:db.execute('UPDATE player_limits SET count=count+1 WHERE key=?',(key,))

    def send(self,email,code):
        self.deliver(email,code,False)

    def send_reset(self,email,code):
        self.deliver(email,code,True)

    def deliver(self,email,code,reset):
        msg=EmailMessage();msg['From']=os.environ['SMTP_FROM'];msg['To']=email;msg['Subject']='Klassenkampf: Passwort zurücksetzen' if reset else 'Klassenkampf: E-Mail bestätigen'
        msg.set_content(('Code zum Zurücksetzen deines Passworts: ' if reset else 'Dein Bestätigungscode: ')+code+'\n\nDer Code ist 5 Minuten gültig und kann einmal verwendet werden.\nWenn du diese Anfrage nicht gestartet hast, ignoriere diese E-Mail.\n\nKlassenkampf\n'+self.web.origin)
        port=int(os.environ.get('SMTP_PORT','465'));host=os.environ['SMTP_HOST']
        if port==465:
            connection=smtplib.SMTP_SSL(host,port,timeout=12,context=ssl.create_default_context())
        else:
            connection=smtplib.SMTP(host,port,timeout=12);connection.ehlo();connection.starttls(context=ssl.create_default_context());connection.ehlo()
        with connection as smtp:
            smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);smtp.send_message(msg)

    async def challenge(self,email,password=None):
        self.hit('mail:'+email,3,600);self.hit('mail:global',30,3600)
        token=secrets.token_urlsafe(32);code=str(secrets.randbelow(1000000)).zfill(6)
        with self.store.connect() as db:
            db.execute('DELETE FROM player_codes WHERE expires<?',(int(time.time()),))
            db.execute('INSERT INTO player_codes VALUES(?,?,?,?,?,0)',
                       (self.store.digest(token),email,self.store.digest(token+':'+code),password,int(time.time())+300))
        try:
            async with self.mail_slots:await asyncio.to_thread(self.send,email,code)
        except Exception:
            with self.store.connect() as db:db.execute('DELETE FROM player_codes WHERE token=?',(self.store.digest(token),))
            raise ValueError('E-Mail-Versand momentan nicht verfügbar. Bitte später erneut versuchen.') from None
        return token

    def verify(self,token,code):
        now=int(time.time())
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM player_codes WHERE token=?',(self.store.digest(token),)).fetchone()
            if not row or row['expires']<=now or row['attempts']>=5:raise ValueError('Code ungültig oder abgelaufen.')
            if not row['password']:raise ValueError('Code ungültig oder abgelaufen.')
            valid=secrets.compare_digest(self.store.digest(token+':'+str(code)),row['hash'])
            db.execute('UPDATE player_codes SET attempts=attempts+1 WHERE token=?',(self.store.digest(token),))
        if not valid:raise ValueError('Code ungültig oder abgelaufen.')
        with self.store.connect() as db:
            # Consume once, including competing pending registrations for this email.
            db.execute('DELETE FROM player_codes WHERE email=?',(row['email'],))
            if row['password']:
                if db.execute('SELECT 1 FROM player_accounts WHERE email=?',(row['email'],)).fetchone():raise ValueError('Konto existiert bereits. Bitte anmelden.')
                db.execute('INSERT INTO player_accounts VALUES(?,?,?)',(row['email'],row['password'],now))
                db.execute('INSERT INTO admins VALUES(?,NULL,?,?)',('player:'+row['email'],'host',now))
            account=db.execute('SELECT 1 FROM player_accounts WHERE email=?',(row['email'],)).fetchone()
            if not account:raise ValueError('Konto nicht verfügbar.')
        actor='player:'+row['email'];self.store.log(actor,'player-login')
        return self.store.new_session(actor)

    async def request_reset(self,email):
        self.hit('mail:'+email,3,600);self.hit('mail:global',30,3600)
        token=secrets.token_urlsafe(32);code=str(secrets.randbelow(1000000)).zfill(6);now=int(time.time())
        with self.store.connect() as db:
            db.execute('DELETE FROM player_resets WHERE expires<=?',(now,))
            account=db.execute('SELECT 1 FROM player_accounts WHERE email=?',(email,)).fetchone()
            if account:db.execute('INSERT INTO player_resets VALUES(?,?,?,?,0)',(self.store.digest(token),email,self.store.digest(token+':'+code),now+300))
        if account:
            try:
                async with self.mail_slots:await asyncio.to_thread(self.send_reset,email,code)
            except Exception:
                with self.store.connect() as db:db.execute('DELETE FROM player_resets WHERE token=?',(self.store.digest(token),))
                # Same public response for missing accounts and delivery failures.
        return token

    async def reset_password(self,token,code,password):
        key=self.store.digest(token);now=int(time.time())
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM player_resets WHERE token=?',(key,)).fetchone()
            if not row or row['expires']<=now or row['attempts']>=5:raise ValueError('Code ungültig oder abgelaufen.')
            valid=secrets.compare_digest(self.store.digest(token+':'+str(code)),row['hash'])
            db.execute('UPDATE player_resets SET attempts=attempts+1 WHERE token=?',(key,))
        if not valid:raise ValueError('Code ungültig oder abgelaufen.')
        if self.slots.locked():raise ValueError('Bitte später erneut versuchen.')
        async with self.slots:encoded=await asyncio.to_thread(PasswordAuth.encode,password)
        with self.store.connect() as db:
            # Recheck after hashing: concurrent resets must not reuse a consumed code.
            current=db.execute('SELECT * FROM player_resets WHERE token=?',(key,)).fetchone()
            if not current or current['expires']<=int(time.time()):raise ValueError('Code ungültig oder abgelaufen.')
            db.execute('UPDATE player_accounts SET hash=? WHERE email=?',(encoded,row['email']))
            db.execute('DELETE FROM player_resets WHERE email=?',(row['email'],))
            db.execute('DELETE FROM player_codes WHERE email=?',(row['email'],))
            db.execute('DELETE FROM sessions WHERE email=?',('player:'+row['email'],))
        self.store.log('player:'+row['email'],'player-password-reset')

    async def change_password(self,headers,obj):
        session=self.session(headers);w=self.web
        if not session:raise Denied('Bitte erneut anmelden.')
        if headers.get('origin')!=w.origin or not secrets.compare_digest(headers.get('x-csrf-token','').encode(),session['csrf'].encode()):raise Denied('Ungültige Sicherheitsprüfung.')
        old=obj.get('current_password','');new=obj.get('password','')
        if not isinstance(old,str) or not 1<=len(old)<=256 or not isinstance(new,str) or not 12<=len(new)<=256:raise ValueError('Passwort muss 12 bis 256 Zeichen lang sein.')
        if old==new:raise ValueError('Bitte ein anderes neues Passwort wählen.')
        self.hit('change-password:'+session['email'],5,900)
        email=session['display_email'];key=self.store.digest(w.cookie(headers,self.COOKIE))
        with self.store.connect() as db:account=db.execute('SELECT hash FROM player_accounts WHERE email=?',(email,)).fetchone()
        if not account:raise Denied('Bitte erneut anmelden.')
        if self.slots.locked():raise ValueError('Bitte später erneut versuchen.')
        async with self.slots:
            valid=await asyncio.to_thread(PasswordAuth.verify,old,account['hash'])
            if not valid:raise ValueError('Aktuelles Passwort ist falsch.')
            encoded=await asyncio.to_thread(PasswordAuth.encode,new)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT hash FROM player_accounts WHERE email=?',(email,)).fetchone()
            active=db.execute('SELECT 1 FROM sessions WHERE token=? AND email=? AND expires>?',(key,session['email'],int(time.time()))).fetchone()
            if not active or not current or current['hash']!=account['hash']:raise Denied('Bitte erneut anmelden.')
            db.execute('UPDATE player_accounts SET hash=? WHERE email=?',(encoded,email))
            db.execute('DELETE FROM sessions WHERE email=?',(session['email'],))
            db.execute('DELETE FROM player_codes WHERE email=?',(email,))
            db.execute('DELETE FROM player_resets WHERE email=?',(email,))
        self.store.log(session['email'],'player-password-change')

    async def delete_account(self,headers,obj):
        session=self.session(headers)
        if not session:raise Denied('Bitte erneut anmelden.')
        password=obj.get('current_password','')
        if obj.get('confirmation')!='LÖSCHEN' or not isinstance(password,str) or not 1<=len(password)<=256:raise ValueError('Bitte Passwort und Löschbestätigung eingeben.')
        self.hit('delete-account:'+session['email'],5,900)
        email=session['display_email']
        with self.store.connect() as db:account=db.execute('SELECT hash FROM player_accounts WHERE email=?',(email,)).fetchone()
        if not account:raise Denied('Bitte erneut anmelden.')
        if self.slots.locked():raise ValueError('Bitte später erneut versuchen.')
        async with self.slots:valid=await asyncio.to_thread(PasswordAuth.verify,password,account['hash'])
        if not valid:raise ValueError('Aktuelles Passwort ist falsch.')
        await self.web.manage_player(session,'delete-player-account',email,self_delete=(account['hash'],self.store.digest(self.web.cookie(headers,self.COOKIE))))

    async def handle(self,reader,writer,method,route,headers):
        w=self.web
        if route=='/auth/player/csrf' and method=='GET':
            token=secrets.token_urlsafe(32);await w.respond(writer,200,{'csrf':token,'ready':True,'mail_ready':self.ready},cookie=(self.CSRF,token,600));return
        if route in ('/auth/player/change-password','/auth/player/delete-account') and method=='POST':
            session=self.session(headers)
            if not session or headers.get('origin')!=w.origin or not secrets.compare_digest(headers.get('x-csrf-token','').encode(),session['csrf'].encode()):raise Denied('Bitte erneut anmelden.')
            if headers.get('transfer-encoding') or headers.get('content-type','').split(';')[0]!='application/json':raise ValueError('JSON erforderlich.')
            length=int(headers.get('content-length','0'))
            if not 0<length<=4096:raise ValueError('Anfrage zu groß.')
            obj=json.loads(await asyncio.wait_for(reader.readexactly(length),5))
            if not isinstance(obj,dict):raise ValueError('Ungültige Anfrage.')
            if route.endswith('/delete-account'):await self.delete_account(headers,obj)
            else:await self.change_password(headers,obj)
            await w.respond(writer,200,{'ok':True},cookie=(self.COOKIE,'',0));return
        if route=='/auth/player/logout' and method=='POST':
            session=self.session(headers)
            if not session or headers.get('origin')!=w.origin or not secrets.compare_digest(headers.get('x-csrf-token','').encode(),session['csrf'].encode()):raise Denied('Ungültige Sicherheitsprüfung.')
            with self.store.connect() as db:db.execute('DELETE FROM sessions WHERE token=?',(self.store.digest(w.cookie(headers,self.COOKIE)),))
            await w.respond(writer,200,{'ok':True},cookie=(self.COOKIE,'',0));return
        if route not in ('/auth/player/register','/auth/player/login','/auth/player/verify','/auth/player/reset-request','/auth/player/reset-confirm') or method!='POST':
            await w.respond(writer,404,{'error':'Nicht gefunden'});return
        csrf=w.cookie(headers,self.CSRF)
        if not csrf or headers.get('origin')!=w.origin or not secrets.compare_digest(csrf.encode(),headers.get('x-csrf-token','').encode()):raise Denied('Seite bitte neu laden.')
        if route in ('/auth/player/register','/auth/player/reset-request') and not self.ready:
            await w.respond(writer,503,{'error':'E-Mail-Anmeldung momentan nicht verfügbar.'});return
        if headers.get('transfer-encoding') or headers.get('content-type','').split(';')[0]!='application/json':raise ValueError('JSON erforderlich')
        length=int(headers.get('content-length','0'))
        if not 0<length<=4096:raise ValueError('Anfrage zu groß')
        ip=headers.get('x-forwarded-for','local').split(',')[-1].strip()
        self.hit('requests:'+hashlib.sha256(ip.encode()).hexdigest(),30,900)
        obj=json.loads(await asyncio.wait_for(reader.readexactly(length),5))
        if not isinstance(obj,dict):raise ValueError('Ungültige Anfrage')
        if route.endswith('/reset-confirm'):
            password=obj.get('password','')
            if not isinstance(password,str) or not 12<=len(password)<=256:raise ValueError('Passwort muss 12 bis 256 Zeichen lang sein.')
            await self.reset_password(w.cookie(headers,self.RESET),obj.get('code',''),password)
            await w.respond(writer,200,{'ok':True},cookie=(self.COOKIE,'',0));return
        if route.endswith('/verify'):

            token=self.verify(w.cookie(headers,self.PENDING),obj.get('code',''))
            await w.respond(writer,200,{'ok':True},cookie=(self.COOKIE,token,28800));return
        email=self.store.email(obj.get('email',''))
        if parseaddr(email)[1]!=email:raise ValueError('Bitte eine gültige E-Mail-Adresse eingeben.')
        self.hit('auth:'+email,10,900)
        if route.endswith('/reset-request'):
            self.hit('send-ip:'+hashlib.sha256(ip.encode()).hexdigest(),5,900)
            token=await self.request_reset(email)
            await w.respond(writer,200,{'stage':'reset'},cookie=(self.RESET,token,300));return
        password=obj.get('password','')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Ungültige Anmeldedaten.')
        with self.store.connect() as db:account=db.execute('SELECT hash FROM player_accounts WHERE email=?',(email,)).fetchone()
        if route.endswith('/register'):
            if account:raise ValueError('Registrierung nicht möglich. Bitte anmelden.')
            if self.slots.locked():raise ValueError('Bitte später erneut versuchen.')
            async with self.slots:encoded=await asyncio.to_thread(PasswordAuth.encode,password)
        else:
            if self.slots.locked():raise ValueError('Bitte später erneut versuchen.')
            async with self.slots:valid=await asyncio.to_thread(PasswordAuth.verify,password,account['hash'] if account else w.password_auth.dummy)
            with self.store.connect() as db:current=db.execute('SELECT hash FROM player_accounts WHERE email=?',(email,)).fetchone()
            if not account or not valid or not current or current['hash']!=account['hash']:
                await w.respond(writer,401,{'error':'E-Mail-Adresse oder Passwort ungültig.'});return
            actor='player:'+email;self.store.log(actor,'player-login')
            token=self.store.new_session(actor)
            await w.respond(writer,200,{'stage':'authenticated'},cookie=(self.COOKIE,token,28800));return
        self.hit('send-ip:'+hashlib.sha256(ip.encode()).hexdigest(),5,900)
        token=await self.challenge(email,encoded)
        await w.respond(writer,200,{'stage':'email'},cookie=(self.PENDING,token,300))
