"""Small player-host surface and persistent idle deadlines."""
import asyncio
import json
import time


class HostSessions:
    def __init__(self,hub):
        self.hub=hub;self.store=hub.store;self.lock=asyncio.Lock()
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS host_rooms(room_id TEXT PRIMARY KEY,email TEXT NOT NULL,created INTEGER NOT NULL,joined INTEGER NOT NULL,empty_since INTEGER)')
            rows=db.execute("SELECT r.*,a.email FROM game_rooms r JOIN session_access a ON a.room_id=r.id JOIN admins u ON u.email=a.email WHERE u.role='host'").fetchall()
            for r in rows:
                joined=bool(json.loads(r['state']).get('players'))
                db.execute('INSERT OR IGNORE INTO host_rooms VALUES(?,?,?,?,?)',(r['id'],r['email'],r['created'],int(joined),int(time.time()) if joined else None))

    def attach(self,room_id,email):
        with self.store.connect() as db:
            db.execute('INSERT INTO host_rooms VALUES(?,?,?,0,NULL)',(room_id,email,int(time.time())))

    def online(self,room):
        return sum(bool(c.alive and c.authed and not c.writer.is_closing()) for c in room.joined_connections)

    def observe(self,room_id,now=None):
        now=int(time.time()) if now is None else now
        room=self.hub.rooms.get(room_id)
        online=self.online(room) if room else 0
        with self.store.connect() as db:
            if online:db.execute('UPDATE host_rooms SET joined=1,empty_since=NULL WHERE room_id=?',(room_id,))
            else:db.execute('UPDATE host_rooms SET empty_since=COALESCE(empty_since,?) WHERE room_id=? AND joined=1',(now,room_id))

    async def sweep(self,now=None):
        async with self.lock:await self._sweep(now)

    async def _sweep(self,now=None):
        now=int(time.time()) if now is None else now
        with self.store.connect() as db:
            rows=db.execute('SELECT h.* FROM host_rooms h JOIN game_rooms r ON h.room_id=r.id WHERE r.active=1 ORDER BY h.created DESC').fetchall()
        # Existing accounts may have started two rooms before this change.
        rows=sorted(rows,key=lambda r:bool(self.hub.rooms.get(r['room_id']) and self.online(self.hub.rooms[r['room_id']])),reverse=True)
        seen={}
        for row in rows:
            rid=row['room_id'];reason=None
            if rid not in self.hub.rooms or not self.hub.rooms[rid].room_active:continue
            policy=self.hub.server.web_admin.player_auth.permissions.get(row['email'])
            seen[row['email']]=seen.get(row['email'],0)+1
            if seen[row['email']]>policy['max_sessions']:reason='Sitzungslimit'
            self.observe(rid,now)
            with self.store.connect() as db:state=db.execute('SELECT * FROM host_rooms WHERE room_id=?',(rid,)).fetchone()
            if state is None:continue
            if not policy['keep_empty'] and not state['joined'] and now-state['created']>=300:reason=reason or 'Kein Beitritt innerhalb von 5 Minuten'
            if not policy['keep_empty'] and state['joined'] and state['empty_since'] is not None and now-state['empty_since']>=60:reason=reason or 'Seit 1 Minute leer'
            if reason:
                await self.hub.end(rid)
                self.store.log(row['email'],'auto-end-session',rid+' '+reason)

    def overview(self,email):
        with self.store.connect() as db:
            row=db.execute('SELECT r.id,r.name,r.code,h.* FROM host_rooms h JOIN game_rooms r ON r.id=h.room_id WHERE h.email=? AND r.active=1 ORDER BY r.created DESC LIMIT 1',(email,)).fetchone()
        if not row:return {'session':None}
        room=self.hub.rooms.get(row['id']);online=self.online(room) if room else 0
        policy=self.hub.server.web_admin.player_auth.permissions.get(email)
        deadline=None if online or policy['keep_empty'] else row['created']+300 if not row['joined'] else (row['empty_since'] or int(time.time()))+60
        return {'session':{'id':row['id'],'name':row['name'],'code':row['code'],'online':online,
                           'matches':len(room.matches) if room else 0,'closes_at':deadline}}
