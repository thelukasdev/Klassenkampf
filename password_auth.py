"""Password authentication; no external identity provider or default password."""
import asyncio
from collections import deque
import hashlib
import json
import secrets
import time


class PasswordAuth:
    COOKIE='__Host-kk_login'
    ITERATIONS=600000

    def __init__(self, web):
        self.web=web
        self.store=web.store
        self.attempts=deque(maxlen=30)
        self.slots=asyncio.Semaphore(2)
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS admin_passwords(email TEXT PRIMARY KEY, hash TEXT NOT NULL)')
        self.dummy=self.encode(secrets.token_urlsafe(24))
        from mfa_auth import MFAAuth
        self.mfa=MFAAuth(web)

    @classmethod
    def encode(cls,password):
        if not isinstance(password,str) or not 12<=len(password)<=256:
            raise ValueError('Das Passwort muss 12 bis 256 Zeichen enthalten.')
        salt=secrets.token_hex(16)
        digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),cls.ITERATIONS).hex()
        return f'pbkdf2_sha256${cls.ITERATIONS}${salt}${digest}'

    @staticmethod
    def verify(password,encoded):
        try:
            algorithm,iterations,salt,expected=encoded.split('$')
            if algorithm!='pbkdf2_sha256' or not 100000<=int(iterations)<=1000000:
                return False
            actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
            return secrets.compare_digest(actual,expected)
        except (ValueError,TypeError):
            return False

    def set_encoded(self,email,encoded):
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM admins WHERE email=?',(email,)).fetchone():
                raise ValueError('Dieses Verwaltungskonto existiert nicht.')
            db.execute('INSERT OR REPLACE INTO admin_passwords VALUES(?,?)',(email,encoded))
            db.execute('DELETE FROM sessions WHERE email=?',(email,))
            db.execute('DELETE FROM mfa_pending WHERE email=?',(email,))

    @property
    def ready(self):
        with self.store.connect() as db:
            return bool(db.execute('SELECT 1 FROM admins a JOIN admin_passwords p ON a.email=p.email WHERE a.role=\'owner\'').fetchone())

    async def handle(self,reader,writer,method,path,headers):
        w=self.web
        if path=='/auth/password/csrf' and method=='GET':
            csrf=secrets.token_urlsafe(32)
            await w.respond(writer,200,{'csrf':csrf},cookie=(self.COOKIE,csrf,600))
            return
        if path not in ('/auth/password/login','/auth/password/mfa') or method!='POST':
            await w.respond(writer,404,{'error':'Nicht gefunden'})
            return
        csrf=w.cookie(headers,self.COOKIE)
        if (headers.get('origin')!=w.origin or not csrf or
                not secrets.compare_digest(csrf.encode(),headers.get('x-csrf-token','').encode())):
            await w.respond(writer,403,{'error':'Bitte die Seite neu laden.'})
            return
        now=time.monotonic()
        while self.attempts and self.attempts[0]<now-60:self.attempts.popleft()
        if len(self.attempts)>=20 or self.slots.locked():
            await w.respond(writer,503,{'error':'Zu viele Anmeldeversuche. Bitte in einer Minute erneut versuchen.'})
            return
        self.attempts.append(now)
        if headers.get('transfer-encoding') or headers.get('content-type','').split(';')[0]!='application/json':
            raise ValueError('JSON erforderlich')
        length=int(headers.get('content-length','0'))
        if not 0<length<=4096:raise ValueError('Ungueltige Anfrage')
        obj=json.loads(await asyncio.wait_for(reader.readexactly(length),5))
        if not isinstance(obj,dict):raise ValueError('Ungueltige Anfrage')
        if path=='/auth/password/mfa':
            verified=self.mfa.verify(w.cookie(headers,self.mfa.COOKIE),obj.get('code',''))
            if not verified:
                await w.respond(writer,401,{'error':'Code ungueltig oder Anmeldung abgelaufen. Nach fuenf Fehlversuchen 15 Minuten warten und neu anmelden.'})
                return
            token=self.store.new_session(verified['email'])
            self.store.log(verified['email'],'login','2FA-Wiederherstellungscode' if verified['recovered'] else '2FA')
            await w.respond(writer,200,{'ok':True,'recovery_codes':verified['recovery_codes']},cookie=(w.COOKIE,token,28800))
            return
        email=str(obj.get('email','')).strip().lower()
        password=obj.get('password','')
        if not isinstance(password,str) or len(password)>256:raise ValueError('Ungueltige Anfrage')
        with self.store.connect() as db:
            row=db.execute('SELECT p.hash FROM admin_passwords p JOIN admins a ON a.email=p.email WHERE p.email=?',(email,)).fetchone()
        async with self.slots:
            valid=await asyncio.to_thread(self.verify,password,row['hash'] if row else self.dummy)
        if not row or not valid:
            await w.respond(writer,401,{'error':'E-Mail-Adresse oder Passwort ist falsch.'})
            return
        pending,response=self.mfa.begin(email,row['hash'])
        await w.respond(writer,200,response,cookie=(self.mfa.COOKIE,pending,300))
