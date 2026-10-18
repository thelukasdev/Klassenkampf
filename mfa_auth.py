"""Mandatory RFC 6238 second factor after password verification."""
import base64
import hashlib
import hmac
import io
import re
import secrets
import time
from urllib.parse import quote,urlencode


def totp(secret,step,digits=6):
    digest=hmac.new(base64.b32decode(secret),int(step).to_bytes(8,'big'),hashlib.sha1).digest()
    offset=digest[-1]&15
    number=int.from_bytes(digest[offset:offset+4],'big')&0x7fffffff
    return str(number % (10**digits)).zfill(digits)


class MFAAuth:
    COOKIE='__Host-kk_mfa'

    def __init__(self,web):
        self.web=web;self.store=web.store
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mfa_factors(email TEXT PRIMARY KEY,secret TEXT NOT NULL,last_step INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS mfa_pending(token TEXT PRIMARY KEY,email TEXT NOT NULL,secret TEXT,version TEXT NOT NULL,expires INTEGER NOT NULL,attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS mfa_recovery(email TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(email,hash));
                CREATE TABLE IF NOT EXISTS mfa_limits(email TEXT PRIMARY KEY,window_start INTEGER NOT NULL,failures INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_settings(key TEXT PRIMARY KEY,value TEXT);
            ''')
            if not db.execute("SELECT 1 FROM auth_settings WHERE key='mfa_required'").fetchone():
                db.execute('DELETE FROM sessions')
                db.execute("INSERT INTO auth_settings VALUES('mfa_required','1')")

    def begin(self,email,password_hash):
        token=secrets.token_urlsafe(32)
        with self.store.connect() as db:
            enrolled=db.execute('SELECT 1 FROM mfa_factors WHERE email=?',(email,)).fetchone()
            secret=None if enrolled else base64.b32encode(secrets.token_bytes(20)).decode()
            db.execute('DELETE FROM mfa_pending WHERE email=? OR expires<?',(email,int(time.time())))
            db.execute('INSERT INTO mfa_pending VALUES(?,?,?,?,?,0)',
                       (self.store.digest(token),email,secret,self.store.digest(password_hash),int(time.time())+300))
        response={'stage':'verify' if enrolled else 'setup'}
        if secret:
            import qrcode
            from qrcode.image.svg import SvgPathImage
            uri='otpauth://totp/'+quote('Klassenkampf:'+email,safe='')+'?'+urlencode(
                {'secret':secret,'issuer':'Klassenkampf','algorithm':'SHA1','digits':6,'period':30})
            image=qrcode.make(uri,image_factory=SvgPathImage)
            output=io.BytesIO();image.save(output)
            response.update(qr='data:image/svg+xml;base64,'+base64.b64encode(output.getvalue()).decode(),secret=secret)
        return token,response

    def verify(self,token,code):
        now=int(time.time())
        code=str(code).strip().replace(' ','').replace('-','').upper()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pending=db.execute('SELECT * FROM mfa_pending WHERE token=?',(self.store.digest(token),)).fetchone()
            if not pending or pending['expires']<=now or pending['attempts']>=5:
                return None
            account=db.execute('SELECT p.hash FROM admin_passwords p JOIN admins a ON a.email=p.email WHERE p.email=?',(pending['email'],)).fetchone()
            if not account or not secrets.compare_digest(self.store.digest(account['hash']),pending['version']):
                return None
            limit=db.execute('SELECT * FROM mfa_limits WHERE email=?',(pending['email'],)).fetchone()
            if limit and limit['window_start']>now-900 and limit['failures']>=5:return None
            if not limit or limit['window_start']<=now-900:
                db.execute('INSERT OR REPLACE INTO mfa_limits VALUES(?,?,0)',(pending['email'],now))
            db.execute('UPDATE mfa_limits SET failures=failures+1 WHERE email=?',(pending['email'],))
            db.execute('UPDATE mfa_pending SET attempts=attempts+1 WHERE token=?',(pending['token'],))
            factor=db.execute('SELECT * FROM mfa_factors WHERE email=?',(pending['email'],)).fetchone()
            secret=factor['secret'] if factor else pending['secret']
            # Do not reuse a setup challenge after another flow enrolled the account.
            if (factor is None)!=(pending['secret'] is not None):return None
            step=None
            if re.fullmatch(r'\d{6}',code):
                for candidate in (now//30-1,now//30,now//30+1):
                    if (not factor or candidate>factor['last_step']) and secrets.compare_digest(totp(secret,candidate),code):
                        step=candidate;break
            recovered=False
            if step is None and factor and re.fullmatch(r'[0-9A-F]{20}',code):
                recovered=db.execute('DELETE FROM mfa_recovery WHERE email=? AND hash=?',
                                     (pending['email'],self.store.digest(code))).rowcount==1
            if step is None and not recovered:return None
            recovery=[]
            if factor:
                if step is not None:
                    db.execute('UPDATE mfa_factors SET last_step=? WHERE email=?',(step,pending['email']))
            else:
                db.execute('INSERT INTO mfa_factors VALUES(?,?,?)',(pending['email'],secret,step))
                for _ in range(10):
                    value=secrets.token_hex(10).upper()
                    recovery.append('-'.join(value[i:i+4] for i in range(0,20,4)))
                    db.execute('INSERT INTO mfa_recovery VALUES(?,?)',(pending['email'],self.store.digest(value)))
            db.execute('DELETE FROM mfa_pending WHERE email=?',(pending['email'],))
            db.execute('DELETE FROM mfa_limits WHERE email=?',(pending['email'],))
        return {'email':pending['email'],'recovery_codes':recovery,'recovered':recovered}

    def reset(self,email):
        with self.store.connect() as db:
            for table in ('mfa_factors','mfa_pending','mfa_recovery','mfa_limits','sessions'):
                db.execute('DELETE FROM '+table+' WHERE email=?',(email,))
