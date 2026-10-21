"""Session controls and restricted operational status."""
import asyncio
import os
import shutil
import time
import games
import secrets

class ArenaControl:
    def __init__(self,room): self.room=room
    async def cancel_match(self,m,reason='admin'):
        if m.finished:return
        m.finished=True;m.end_reason=reason
        for p in m.active:
            await m._send(p,{'t':'match_cancelled','msg':'Partie durch Spielleitung beendet.' if reason=='admin' else 'Partie ohne Wertung beendet: Alle Spieler haben die Verbindung verloren.' if reason=='connection_lost' else 'Partie ohne weitere Wertung beendet: Zeichnen & Raten benötigt mindestens vier Spieler.' if reason=='not_enough_players' else 'Partie wegen eines technischen Fehlers beendet.'})
        self.room.close_match(m)
        if m.task and m.task is not asyncio.current_task():
            m.task.cancel(); await asyncio.gather(m.task,return_exceptions=True)
    async def action(self,obj):
        r=self.room; action=obj['action']; value=str(obj.get('value',''))
        if action=='projector':return r.projector.select(value)
        if action=='release-waiting-room':
            result=r.flow.release();await r.push_lobby();return result
        if action=='spectators':
            m=r.matches.get(int(value))
            if not m or m.finished:raise ValueError('Partie nicht gefunden')
            if m.game.per_view:raise ValueError('Verdeckte Spielansichten bleiben privat.')
            m.spectator_token=None if m.spectator_token else secrets.token_urlsafe(24)
            await r.push_lobby()
            return 'Zuschauer freigegeben.' if m.spectator_token else 'Zuschauerfreigabe beendet.'
        if action=='rules':
            rules=obj.get('rules',{})
            if not isinstance(rules,dict): raise ValueError('Ungueltige Regeln')
            allowed={'enabled','paused','speed','credits_win','credits_loss','credits_draw'}
            if set(rules)-allowed: raise ValueError('Unbekannte Regel')
            proposed={**r.rules,**rules}
            enabled=proposed['enabled']
            if not isinstance(enabled,list) or not enabled or any(g not in games.GAMES for g in enabled): raise ValueError('Mindestens ein bekanntes Spiel freigeben.')
            if type(proposed['paused']) is not bool:raise ValueError('Ungueltige Pause')
            if type(proposed['speed']) is not int or proposed['speed'] not in (1,2):raise ValueError('Ungueltiges Tempo')
            for key in ('credits_win','credits_loss','credits_draw'):
                if type(proposed[key]) is not int or not -100<=proposed[key]<=100:raise ValueError('Credits zwischen -100 und 100')
            r.rules=proposed
            for p in r.players.values():p.out_challenge=None
            for m in r.matches.values():
                await m.pause_notice()
            r.save();await r.push_lobby();return 'Spielregeln gespeichert.'
        if action in ('pause-match','end-match'):
            m=r.matches.get(int(value))
            if not m:raise ValueError('Partie nicht gefunden')
            if action=='end-match':await self.cancel_match(m);return 'Partie ohne Wertung beendet.'
            m.paused=not m.paused
            await m.pause_notice()
            return 'Partie pausiert.' if m.paused else 'Partie fortgesetzt.'
        key=value.lower().strip();p=r.players.get(key)
        if not p:raise ValueError('Spieler nicht gefunden')
        if p.busy:raise ValueError('Zuerst die laufende Partie beenden.')
        if action=='move-player':
            if not r.hub:raise ValueError('Sitzungen erforderlich')
            target=r.hub.get(str(obj.get('target','')))
            if target is r or not target.room_active:raise ValueError('Aktive andere Sitzung erforderlich')
            if key in target.players or key in target.banned:raise ValueError('Name in Zielsitzung bereits belegt oder gesperrt.')
            # Create first, before disconnecting the source, and keep browser credentials.
            q=target._add_player(p.nick);q.credits=p.credits;q.record={k:list(v) for k,v in p.record.items()};q.token_hash=p.token_hash
            if p.conn: await p.conn.send({'t':'session_moved','code':target.login_code})
            await r.admin_kick(key)
            r.players.pop(key);r.by_pid.pop(p.pid,None)
            r.banned.discard(key);target.save();r.save();await target.push_lobby()
            return 'Spieler zugeordnet. Zum Beitreten denselben Browser verwenden.'
        if action=='remove-player':
            await r.admin_kick(key);r.players.pop(key);r.by_pid.pop(p.pid,None);r.banned.discard(key);r.save();await r.push_lobby()
            return 'Spielerprofil entfernt.'
        raise ValueError('Unbekannte Aktion')

def server_status(server):
    rooms=list(server.session_hub.rooms.values()) if server.session_hub else [server]
    memory={}
    try:
        with open('/sys/fs/cgroup/memory.current') as f:memory['used_mb']=round(int(f.read())/1048576,1)
        with open('/sys/fs/cgroup/memory.max') as f:
            value=f.read().strip();memory['limit_mb']=round(int(value)/1048576,1) if value!='max' else None
    except (OSError,ValueError):pass
    disk=shutil.disk_usage(os.path.dirname(server.web_admin.store.path))
    return {'uptime':round(time.monotonic()-server.started_at),'load':list(os.getloadavg()) if hasattr(os,'getloadavg') else None,
        'memory':memory,'disk_free_mb':round(disk.free/1048576),'connections':len(server.connections),
        'workers':[{'session':getattr(r,'room_name',''),'pid':r.worker.process.pid,'matches':len(r.worker.ids)} for r in rooms if r.worker and r.worker.process and r.worker.process.returncode is None],
        'worker_errors':sum(r.worker.failures for r in rooms if r.worker),'worker_limit':8,
        'architecture':'Ein Spielprozess je spielender Sitzung, eine private Instanz je Partie',
        'games':games.GAME_INFO}
