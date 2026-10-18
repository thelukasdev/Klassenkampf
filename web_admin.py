"""Password administration with server-side sessions and SQLite storage."""
import asyncio
import base64
import hashlib
from http.cookies import SimpleCookie
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import urllib.request
from contextlib import contextmanager


class Denied(Exception):
    pass


class AdminStore:
    def __init__(self, path, owner=''):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS admins(email TEXT PRIMARY KEY, sub TEXT UNIQUE, role TEXT NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, email TEXT NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth(state TEXT PRIMARY KEY, browser TEXT NOT NULL, nonce TEXT NOT NULL, verifier TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, time INTEGER NOT NULL, email TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS session_access(email TEXT NOT NULL, room_id TEXT NOT NULL, PRIMARY KEY(email,room_id));
                CREATE TABLE IF NOT EXISTS game_state(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
            ''')
            # Bootstrap only an empty access list. Environment changes never add a new owner silently.
            if owner and not db.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
                db.execute('INSERT INTO admins VALUES(?,NULL,?,?)', (self.email(owner), 'owner', int(time.time())))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def email(value):
        value = str(value).strip().lower()
        if value.startswith('player:') or len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Bitte eine gueltige E-Mail-Adresse eingeben.')
        return value

    def load_game(self):
        with self.connect() as db:
            row = db.execute('SELECT data FROM game_state WHERE id=1').fetchone()
        return json.loads(row['data']) if row else None

    def save_game(self, data):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO game_state VALUES(1,?)', (json.dumps(data),))

    def new_session(self, email):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (int(time.time()),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                       (self.digest(token), email, csrf, int(time.time()) + 28800))
        return token

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def session(self, token):
        with self.connect() as db:
            row = db.execute('SELECT s.email,s.csrf,a.role FROM sessions s JOIN admins a ON s.email=a.email WHERE s.token=? AND s.expires>?',
                             (self.digest(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def log(self, email, action, detail=''):
        with self.connect() as db:
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',
                       (int(time.time()), email, action, str(detail)[:300]))

    def admins(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT email,role,created,EXISTS(SELECT 1 FROM admin_passwords p WHERE p.email=admins.email) AS activated FROM admins WHERE role!='host' ORDER BY role DESC,email")]

    def access(self, actor, action, email):
        email = self.email(email)
        with self.connect() as db:
            current = db.execute('SELECT role FROM admins WHERE email=?', (actor,)).fetchone()
            if not current or current['role'] != 'owner':
                raise Denied('Nur der Inhaber darf Verwaltungszugriffe aendern.')
            if action == 'add-admin':
                db.execute('INSERT OR IGNORE INTO admins VALUES(?,NULL,?,?)', (email, 'admin', int(time.time())))
            elif action == 'remove-admin':
                target = db.execute('SELECT role FROM admins WHERE email=?', (email,)).fetchone()
                if target and target['role'] == 'owner':
                    raise Denied('Der Inhaber kann nicht entfernt werden.')
                db.execute('DELETE FROM admins WHERE email=?', (email,))
                db.execute('DELETE FROM session_access WHERE email=?',(email,))
                db.execute('DELETE FROM sessions WHERE email=?', (email,))
            else:
                raise ValueError('Unbekannte Aktion')
        self.log(actor, action, email)

    def allowed_rooms(self, session):
        if session['role'] in ('owner','admin'):return None
        with self.connect() as db:return {r[0] for r in db.execute('SELECT room_id FROM session_access WHERE email=?',(session['email'],))}

    def check_room(self,session,room_id):
        allowed=self.allowed_rooms(session)
        if not room_id:raise ValueError('Bitte eine Spielsitzung auswaehlen.')
        if allowed is not None and room_id not in allowed:
            raise Denied('Kein Zugriff auf diese Spielsitzung.')

    def set_role(self,actor,email,role):
        if actor['role']!='owner':raise Denied('Nur der Inhaber darf Rollen aendern.')
        if role not in ('admin','guide'):raise ValueError('Ungueltige Rolle')
        email=self.email(email)
        with self.connect() as db:
            target=db.execute('SELECT role FROM admins WHERE email=?',(email,)).fetchone()
            if not target or target['role'] in ('owner','host'):raise Denied('Inhaberrolle bleibt erhalten.')
            db.execute('UPDATE admins SET role=? WHERE email=?',(role,email))
        self.log(actor['email'],'role',email+' '+role)



class WebAdmin:
    COOKIE = '__Host-kk_admin'
    FLOW_COOKIE = '__Host-kk_oauth'

    def __init__(self, server, data_dir):
        self.server = server
        self.store = AdminStore(Path(data_dir) / 'admin.sqlite3', os.environ.get('KLASSENKAMPF_OWNER_EMAIL', ''))
        self.origin = (server.public_origin or '').rstrip('/')
        from password_auth import PasswordAuth
        self.password_auth = PasswordAuth(self)
        from player_auth import PlayerAuth
        self.player_auth=PlayerAuth(self)
        os.chmod(self.store.path,0o600)

    @staticmethod
    def cookie(headers, name):
        try:
            cookie = SimpleCookie()
            cookie.load(headers.get('cookie', ''))
            return cookie[name].value if name in cookie else ''
        except Exception:
            return ''

    async def respond(self, writer, status, obj=None, *, location=None, cookie=None):
        body = json.dumps(obj or {}, ensure_ascii=False).encode()
        reasons = {200:'OK', 303:'See Other', 400:'Bad Request', 401:'Unauthorized',
                   403:'Forbidden', 404:'Not Found', 405:'Method Not Allowed', 503:'Service Unavailable'}
        header = (f'HTTP/1.1 {status} {reasons[status]}\r\nContent-Type: application/json; charset=utf-8\r\n'
                  f'Content-Length: {len(body)}\r\nCache-Control: no-store\r\n'
                  'Referrer-Policy: no-referrer\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n')
        if location:
            header += 'Location: ' + location + '\r\n'
        if cookie:
            name, value, age = cookie
            header += f'Set-Cookie: {name}={value}; Path=/; Max-Age={age}; HttpOnly; Secure; SameSite=Lax\r\n'
        writer.write(header.encode() + b'\r\n' + body)
        await writer.drain()

    def player_accounts(self,query):
        search=str(query.get('q',[''])[0]).strip().lower();after=str(query.get('after',[''])[0])
        if len(search)>254 or len(after)>254:raise ValueError('Suche zu lang.')
        with self.store.connect() as db:
            rows=[dict(r) for r in db.execute("""SELECT p.email,p.created,
                (SELECT count(*) FROM sessions s WHERE s.email='player:'||p.email AND s.expires>?) AS logins
                FROM player_accounts p WHERE instr(p.email,?)>0 AND p.email>? ORDER BY p.email LIMIT 26""",
                (int(time.time()),search,after))]
        return {'accounts':rows[:25],'next':rows[24]['email'] if len(rows)>25 else None}

    async def manage_player(self,actor,action,value):
        if actor['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen Spielerkonten verwalten.')
        email=self.store.email(value);identity='player:'+email;hub=self.server.session_hub;rooms=[]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM player_accounts WHERE email=?',(email,)).fetchone():raise ValueError('Spielerkonto nicht gefunden.')
            if action=='delete-player-account':
                if hub:
                    rooms=[r[0] for r in db.execute("""SELECT DISTINCT r.id FROM game_rooms r
                        LEFT JOIN session_access a ON a.room_id=r.id LEFT JOIN host_rooms h ON h.room_id=r.id
                        WHERE r.active=1 AND (a.email=? OR h.email=?)""",(identity,identity))]
                    # Persist closure before waiting for connections/workers to stop.
                    for rid in rooms:db.execute('UPDATE game_rooms SET active=0,ended=? WHERE id=?',(int(time.time()),rid))
                    db.execute('DELETE FROM host_rooms WHERE email=?',(identity,))
                db.execute('DELETE FROM player_accounts WHERE email=?',(email,))
                db.execute("DELETE FROM admins WHERE email=? AND role='host'",(identity,))
                db.execute('DELETE FROM session_access WHERE email=?',(identity,))
            db.execute('DELETE FROM sessions WHERE email=?',(identity,))
            db.execute('DELETE FROM player_codes WHERE email=?',(email,))
            db.execute('DELETE FROM player_resets WHERE email=?',(email,))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',(int(time.time()),actor['email'],action,email))
        for rid in rooms:
            room=hub.rooms.get(rid)
            if room and room.room_active:await hub.end(rid)
        return 'Spielerkonto gelöscht.' if action=='delete-player-account' else 'Spielerkonto abgemeldet.'

    async def handle(self, reader, writer, method, path, headers):
        route = urlsplit(path).path
        player_scope=route.startswith('/api/player/')
        if player_scope:route=route.replace('/api/player/','/api/admin/',1)
        try:
            if route.startswith('/auth/player/'):
                await self.player_auth.handle(reader,writer,method,route,headers);return
            if route.startswith('/auth/google/'):
                await self.respond(writer,404,{'error':'Google-Anmeldung ist deaktiviert.'})
                return
            if route.startswith('/auth/password/'):
                await self.password_auth.handle(reader,writer,method,route,headers)
                return
            token = self.cookie(headers,self.player_auth.COOKIE if player_scope else self.COOKIE)
            session = self.player_auth.session(headers) if player_scope else self.store.session(token)
            if session and not player_scope and session['role']=='host':session=None
            if route == '/api/admin/me' and method == 'GET':
                await self.respond(writer, 200, {'user': session, 'login_ready': self.player_auth.ready if player_scope else self.password_auth.ready})
                return
            if not session:
                await self.respond(writer, 401, {'error':'Bitte mit E-Mail-Adresse und Passwort anmelden.'})
                return
            if player_scope and session['role']=='host':
                if method=='GET' and route=='/api/admin/overview':
                    await self.server.session_hub.hosts.sweep()
                    await self.respond(writer,200,self.server.session_hub.hosts.overview(session['email']));return
                if not (method=='POST' and route=='/api/admin/action'):
                    raise Denied('Für Spielerkonten nicht verfügbar.')
            if route=='/api/admin/accounts' and method=='GET':
                if session['role'] not in ('owner','admin'):raise Denied('Nur Administratoren dürfen Spielerkonten verwalten.')
                await self.respond(writer,200,self.player_accounts(parse_qs(urlsplit(path).query)));return
            if route in ('/api/admin/replay','/api/admin/replay-chunk') and method=='GET':
                query=parse_qs(urlsplit(path).query);room_id=query.get('session',[''])[0];rid=query.get('id',[''])[0]
                self.store.check_room(session,room_id)
                meta=self.server.replays.metadata(room_id,rid)
                if not meta:raise ValueError('Replay nicht gefunden')
                if route.endswith('-chunk'):
                    index=int(query.get('chunk',['0'])[0]);result=await asyncio.to_thread(self.server.replays.chunk,room_id,rid,index)
                else:result=meta
                await self.respond(writer,200,{'result':result});return
            if route == '/api/admin/join'  and method == 'GET':
                room_id=parse_qs(urlsplit(path).query).get('session',[''])[0]
                self.store.check_room(session,room_id)
                room=self.server.session_hub.get(room_id)
                if not room.room_active:raise ValueError('Sitzung beendet')
                import io
                import qrcode
                import qrcode.image.svg
                url=self.origin+'/?'+urlencode({'code':room.login_code})
                stream=io.BytesIO();qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage,box_size=6).save(stream)
                await self.respond(writer,200,{'url':url,'qr':'data:image/svg+xml;base64,'+base64.b64encode(stream.getvalue()).decode()})
                return
            if route == '/api/admin/overview' and method == 'GET':
                with self.store.connect() as db:
                    audit = [dict(row) for row in db.execute('SELECT time,email,action,detail FROM audit ORDER BY id DESC LIMIT 25')]
                if self.server.session_hub:
                    selected=parse_qs(urlsplit(path).query).get('session',[''])[0]
                    allowed=self.store.allowed_rooms(session)
                    if selected:self.store.check_room(session,selected)
                    overview=self.server.session_hub.overview(selected,allowed)
                    if allowed is not None:audit=[a for a in audit if a['detail'].split(' ',1)[0] in allowed]
                    from control import server_status
                    overview['server']=server_status(self.server) if allowed is None else {'games':__import__('games').GAME_INFO}
                    with self.store.connect() as db:
                        overview['assignments']=[dict(r) for r in db.execute('SELECT email,room_id FROM session_access')] if session['role']=='owner' else []
                else:
                    overview={'status':await self.server.admin_action({'action':'status'}),
                              'code':self.server.login_code,'saves':self.server.admin_list_saves()}
                await self.respond(writer, 200, {**overview,
                                               'admins':self.store.admins() if session['role']=='owner' else [], 'audit':audit})
                return
            if route not in ('/api/admin/action', '/auth/logout') or method != 'POST':
                await self.respond(writer, 404, {'error':'Nicht gefunden'})
                return
            if headers.get('origin') != self.origin or not secrets.compare_digest(
                    headers.get('x-csrf-token', ''), session['csrf']):
                raise Denied('Ungueltige Sicherheitspruefung. Seite neu laden.')
            if route == '/auth/logout':
                with self.store.connect() as db:
                    db.execute('DELETE FROM sessions WHERE token=?', (self.store.digest(token),))
                await self.respond(writer, 200, {'ok':True}, cookie=(self.COOKIE,'',0))
                return
            if headers.get('transfer-encoding') or headers.get('content-type','').split(';')[0] != 'application/json':
                raise ValueError('JSON-Anfrage erforderlich.')
            length = int(headers.get('content-length','0'))
            if not 0 < length <= 4096:
                raise ValueError('Anfrage zu gross.')
            obj = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
            if not isinstance(obj, dict):
                raise ValueError('Ungueltige Anfrage')
            action, value = obj.get('action'), str(obj.get('value',''))
            if session['role']=='host' and action not in ('create-session','end-session'):raise Denied('Für Spielerkonten nicht verfügbar.')
            if action in ('delete-player-account','revoke-player-logins'):
                result=await self.manage_player(session,action,value)
            elif action=='role':
                self.store.set_role(session,value,obj.get('role'))
                result='Rolle gespeichert.'
            elif action=='assign-session':
                if session['role']!='owner':raise Denied('Nur der Inhaber darf Sitzungen zuweisen.')
                email=self.store.email(value);room_id=str(obj.get('session',''))
                self.server.session_hub.get(room_id)
                with self.store.connect() as db:
                    target=db.execute('SELECT role FROM admins WHERE email=?',(email,)).fetchone()
                    if not target or target['role']!='guide':raise ValueError('Spielleiter erforderlich')
                    if obj.get('remove'):db.execute('DELETE FROM session_access WHERE email=? AND room_id=?',(email,room_id))
                    else:db.execute('INSERT OR IGNORE INTO session_access VALUES(?,?)',(email,room_id))
                self.store.log(session['email'],action,room_id+' '+email)
                result='Zuweisung gespeichert.'
            elif action in ('add-admin','remove-admin','reset-admin-password'):
                if session['role']!='owner':
                    raise Denied('Nur der Inhaber darf Verwaltungszugriffe aendern.')
                email=self.store.email(value)
                if action in ('add-admin','reset-admin-password'):
                    async with self.password_auth.slots:
                        encoded=await asyncio.to_thread(self.password_auth.encode,obj.get('password',''))
                    if action=='add-admin':
                        with self.store.connect() as db:
                            if db.execute('SELECT 1 FROM admins WHERE email=?',(email,)).fetchone():
                                raise ValueError('Dieses Konto existiert bereits.')
                        self.store.access(session['email'],action,email)
                        if obj.get('role')=='guide':self.store.set_role(session,email,'guide')
                    self.password_auth.set_encoded(email,encoded)
                    self.store.log(session['email'],action,email)
                else:
                    self.store.access(session['email'],action,email)
                    self.password_auth.mfa.reset(email)
                    with self.store.connect() as db:
                        db.execute('DELETE FROM admin_passwords WHERE email=?',(email,))
                result='Zugriff aktualisiert'
            elif action in ('kick','ban','unban','reset-credits','mode','save','load','create-session','end-session',
                            'rules','pause-match','end-match','remove-player','move-player','spectators'):
                if self.server.session_hub:
                    if action=='create-session':
                        if session['role']=='host':
                            await self.server.session_hub.hosts.sweep()
                            if not self.player_auth.session(headers):raise Denied('Bitte erneut anmelden.')
                            with self.store.connect() as db:
                                count=db.execute('SELECT count(*) FROM session_access a JOIN game_rooms r ON a.room_id=r.id WHERE a.email=? AND r.active=1',(session['email'],)).fetchone()[0]
                            if count>=1:raise ValueError('Du kannst nur eine Sitzung gleichzeitig starten.')
                            self.player_auth.hit('create:'+session['email'],5,86400)
                            obj={**obj,'mode':'choose'}
                        elif session['role'] not in ('owner','admin'):raise Denied('Nur Administratoren duerfen Sitzungen erstellen.')
                    else:self.store.check_room(session,str(obj.get('session','')))
                    if action=='move-player':self.store.check_room(session,str(obj.get('target','')))
                result = await self.server.admin_action(obj)
                if action=='create-session' and session['role']=='host':
                    with self.store.connect() as db:db.execute('INSERT INTO session_access VALUES(?,?)',(session['email'],result['id']))
                    self.server.session_hub.hosts.attach(result['id'],session['email'])
                self.store.log(session['email'], action, str(result['id'] if action=='create-session' else obj.get('session',''))+' '+value)
            else:
                raise ValueError('Unbekannte Aktion')
            await self.respond(writer, 200, {'result':result})
        except Denied as exc:
            if route == '/auth/google/callback':
                await self.respond(writer, 303, location='/admin?error=access', cookie=(self.FLOW_COOKIE,'',0))
            else:
                await self.respond(writer, 403, {'error':str(exc)})
        except ValueError as exc:
            message=str(exc) if route.startswith('/auth/player/') or player_scope else 'Die Anfrage konnte nicht verarbeitet werden.'
            await self.respond(writer,400,{'error':message or 'Ungültige Anfrage.'})
        except (TypeError, KeyError, TimeoutError, asyncio.IncompleteReadError):
            await self.respond(writer, 400, {'error':'Die Anfrage konnte nicht verarbeitet werden.'})
        except Exception:
            # Do not log codes, tokens or OAuth request URLs.
            logging.error('Web administration request failed (%s)', route)
            await self.respond(writer, 503, {'error':'Anmeldung oder Verwaltung momentan nicht erreichbar.'})
