"""Explicit allowlist for the private monitoring feed; no game state is serialized."""
import hashlib
import time


def snapshot(server):
    with server.web_admin.store.connect() as db:
        db.execute('SELECT 1').fetchone()
    sessions=[]
    if server.session_hub:
        for row in server.session_hub.summaries():
            room=server.session_hub.rooms.get(row['id'])
            public_id=hashlib.sha256(('public-status:'+row['id']).encode()).hexdigest()[:12]
            state='ended'
            if row['active']:
                state='standby'
                if room and room.rules['paused']:state='paused'
                elif room and room.matches:state='paused' if all(m.is_paused for m in room.matches.values()) else 'operational'
                if room and room.worker:
                    worker=room.worker
                    recent=time.time()-getattr(worker,'last_error_at',0)<300
                    healthy=worker.process and worker.process.returncode is None
                    if recent and not healthy:state='degraded'
            sessions.append({'id':'session-'+public_id,'label':'Sitzung '+public_id[:6].upper(),
                             'kind':'session','state':state,'online':row['online'],
                             'matches':row['matches'],'active':row['active']})
    return {'version':1,'database':'operational','sessions':sessions}
