"""Independent game arenas sharing one HTTP listener, not player state."""
import hashlib
import asyncio
import json
import secrets
import time


class GameSessions:
    def __init__(self, server):
        self.server = server
        self.store = server.web_admin.store
        self.rooms = {}
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS game_rooms(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
                    active INTEGER NOT NULL, created INTEGER NOT NULL, ended INTEGER,
                    state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS game_settings(key TEXT PRIMARY KEY, value TEXT);
            ''')
            if not db.execute("SELECT 1 FROM game_settings WHERE key='rooms_migrated'").fetchone():
                old = server._state_dict()
                now = int(time.time())
                code=server.login_code.upper().replace('-','').replace(' ','')
                db.execute('INSERT INTO game_rooms VALUES(?,?,?,?,?,?,?)',
                           (secrets.token_hex(12),'Bisherige Spielsitzung',code,1,now,None,json.dumps(old)))
                db.execute("INSERT INTO game_settings VALUES('rooms_migrated','1')")
            ids = [row['id'] for row in db.execute('SELECT id FROM game_rooms WHERE active=1')]
        for room_id in ids:
            self.get(room_id)
        from host_sessions import HostSessions
        self.hosts=HostSessions(self)

    def state(self, room_id):
        with self.store.connect() as db:
            row = db.execute('SELECT state FROM game_rooms WHERE id=?',(room_id,)).fetchone()
        if not row:
            raise ValueError('Spielsitzung nicht gefunden.')
        return json.loads(row['state'])

    def persist(self, room):
        with self.store.connect() as db:
            db.execute('UPDATE game_rooms SET state=? WHERE id=?',
                       (json.dumps(room._state_dict()),room.room_id))

    def get(self, room_id):
        if room_id in self.rooms:
            return self.rooms[room_id]
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM game_rooms WHERE id=?',(room_id,)).fetchone()
        if not row:
            raise ValueError('Spielsitzung nicht gefunden.')
        room = type(self.server)(self.server.host, self.server.port, False, headless=True,
                      login_code=row['code'], public_origin=self.server.public_origin,
                      room_id=room_id, hub=self)
        room.room_name = row['name']
        room.room_active = bool(row['active'])
        room.joined_connections = set()
        if room.room_active:
            self.rooms[room_id] = room
        return room

    def create(self, name, mode='choose',waiting_room=False,design=None):
        from session_design import validate
        design=validate(design)
        if type(waiting_room) is not bool:raise ValueError('Ungültige Warteraum-Einstellung.')
        name = ' '.join(str(name).split())
        if not name or len(name)>80 or any(ord(c)<32 for c in name):
            raise ValueError('Bitte einen Sitzungsnamen mit 1 bis 80 Zeichen eingeben.')
        if mode not in ('choose','random'):
            raise ValueError('Ungueltiger Spielmodus.')
        with self.store.connect() as db:
            if db.execute('SELECT count(*) FROM game_rooms WHERE active=1').fetchone()[0]>=16:
                raise ValueError('Maximal 16 gleichzeitige Spielsitzungen.')
            alphabet='23456789ABCDEFGHJKMNPQRSTUVWXYZ'
            while True:
                code=''.join(secrets.choice(alphabet) for _ in range(6))
                if not db.execute('SELECT 1 FROM game_rooms WHERE code=?',(code,)).fetchone():
                    break
            room_id=secrets.token_hex(12)
            state={'players':{},'banned':[],'mode':mode,'design':design,'rules':{'waiting_room':waiting_room,'waiting_released':False}}
            db.execute('INSERT INTO game_rooms VALUES(?,?,?,?,?,NULL,?)',
                       (room_id,name,code,1,int(time.time()),json.dumps(state)))
        self.get(room_id)
        return {'id':room_id,'name':name,'code':code}

    def summaries(self):
        with self.store.connect() as db:
            rows=db.execute('SELECT * FROM game_rooms ORDER BY active DESC,created DESC,id DESC').fetchall()
        result=[]
        for row in rows:
            room=self.rooms.get(row['id'])
            state=json.loads(row['state'])
            result.append({'id':row['id'],'name':row['name'],'code':row['code'] if row['active'] else None,
                           'public_status_id':'session-'+hashlib.sha256(('public-status:'+row['id']).encode()).hexdigest()[:12],
                           'active':bool(row['active']),'created':row['created'],'ended':row['ended'],
                           'players':len(room.players) if room else len(state['players']),
                           'online':sum(p.online for p in room.players.values()) if room else 0,
                           'matches':len(room.matches) if room else 0,'mode':room.mode if room else state['mode']})
        return result

    async def end(self, room_id):
        room=self.get(room_id)
        if not room.room_active:
            raise ValueError('Diese Spielsitzung ist bereits beendet.')
        room.room_active=False
        room.flow.cancel_all();room.projector.token=None
        with self.store.connect() as db:
            db.execute('UPDATE game_rooms SET active=0,ended=? WHERE id=?',(int(time.time()),room_id))
        # Administrative end is neutral: no invented wins or losses.
        for match in list(room.matches.values()):
            await room.control.cancel_match(match)
        for conn in list(room.joined_connections):
            await conn.send({'t':'session_ended','msg':'Die Spielleitung hat diese Sitzung beendet.'})
            conn.authed=False
            conn.alive=False
            conn.writer.close()
        for player in room.players.values():
            player.conn=None;player.out_challenge=None
        self.persist(room)
        if room.worker: await room.worker.stop()
        self.rooms.pop(room_id,None)
        return 'Spielsitzung beendet. Ergebnisse bleiben gespeichert.'

    async def message(self, conn, player, obj):
        if obj.get('t')=='login':
            now=time.monotonic()
            failed=self.server.failed_logins
            while failed and failed[0]<now-60:
                failed.popleft()
            if conn.login_attempts>=5 or len(failed)>=120:
                await conn.send({'t':'login_err','msg':'Zu viele Versuche. Bitte spaeter erneut versuchen.'})
                return player
            code=str(obj.get('code','')).strip().upper().replace('-','').replace(' ','')
            room=next((r for r in self.rooms.values() if r.room_active and secrets.compare_digest(code.encode(),r.login_code.encode())),None)
            if not room:
                conn.login_attempts+=1;failed.append(now)
                await conn.send({'t':'login_err','msg':'Sitzungscode ungueltig oder Sitzung bereits beendet.'})
                return player
            old=getattr(conn,'arena',None)
            if old and old is not room:
                if player and player.conn is conn:
                    await old._on_disconnect(player,reconnect=False)
                old.joined_connections.discard(conn)
                player=None
            conn.arena=room
            room.joined_connections.add(conn)
            result=await room._on_message(conn,player,{**obj,'code':code})
            self.hosts.observe(room.room_id)
            return result
        room=getattr(conn,'arena',None)
        if room and room.room_active:
            return await room._on_message(conn,player,obj)
        return player

    async def action(self,obj):
        action=obj.get('action')
        if action=='create-session':
            return self.create(obj.get('value',''),obj.get('mode','choose'),obj.get('waiting_room',False),obj.get('design'))
        if action=='sessions':
            return self.summaries()
        room_id=str(obj.get('session',''))
        if action=='end-session':
            return await self.end(room_id)
        if not room_id:
            if action=='status':
                rows=self.summaries()
                return {'sessions':rows,'active_sessions':sum(r['active'] for r in rows),'players':[],
                        'matches':sum(r['matches'] for r in rows),'connections':len(self.server.connections),'mode':'choose'}
            raise ValueError('Bitte zuerst eine Spielsitzung auswaehlen.')
        room=self.get(room_id)
        if not room.room_active and action not in ('status','saves'):
            raise ValueError('Beendete Spielsitzungen koennen nicht veraendert werden.')
        if action=='session-design':
            from session_design import validate,name
            design=validate(obj.get('design'));title=name(obj.get('value'))
            room.design=design;room.room_name=title
            with self.store.connect() as db:db.execute('UPDATE game_rooms SET name=? WHERE id=?',(title,room_id))
            room.save()
            for conn in list(room.joined_connections):
                if conn.alive and conn.authed:await conn.send({'t':'session-design','session_name':title,'design':design})
            await room.push_lobby()
            return 'Sitzungsdesign gespeichert.'
        return await room.admin_action(obj)

    def overview(self,room_id='',allowed=None):
        rows=self.summaries()
        if allowed is not None:rows=[r for r in rows if r['id'] in allowed]
        if room_id and allowed is not None and room_id not in allowed:raise ValueError('Kein Zugriff')
        room=self.get(room_id) if room_id else None
        if not room and rows:
            room=self.get(rows[0]['id'])
        return {'sessions':rows,'selected_session':room.room_id if room else None,
                'session_active':room.room_active if room else False,
                'session_name':room.room_name if room else None,'design':room.design if room else {},
                'status':{'mode':room.mode if room else 'choose','players':room.admin_list() if room else [],
                          'matches':len(room.matches) if room else 0,'connections':len(room.joined_connections) if room else 0},
                'code':room.login_code if room and room.room_active else None,
                'saves':room.admin_list_saves() if room else [],
                'projector':room.projector.overview() if room else {},'flow':room.flow.summary() if room else {},'rules':room.rules if room else {},'history':room.history if room else [],
                'replays':self.server.replays.metadata(room.room_id) if room else [],
                'matches_detail':[{'id':m.id,'game':m.gid,'name':m.name,'players':[p.nick for p in m.active],
                                   'recording':bool(m.recorder and not m.recorder.closed),'replay_partial':bool(m.recorder and m.recorder.truncated),
                                   'spectators_allowed':not m.game.per_view,'watch_url':'/watch#'+m.spectator_token if m.spectator_token else None,
                                   'paused':m.is_paused,'manual_paused':m.paused,'waiting':[p.nick for p in m.disconnected],'duration':int(time.monotonic()-m.start_t)} for m in room.matches.values()] if room else []}
