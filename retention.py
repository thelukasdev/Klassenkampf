"""Scheduled application-data retention; active rooms and accounts are never purged."""
import logging
from pathlib import Path
import re
import shutil
import time

DAY=86400
ROOM_DAYS=30
REPORT_DAYS=90
RESOLVED_REPORT_DAYS=30
AUDIT_DAYS=90


def cleanup(server,now=None):
    now=int(time.time()) if now is None else int(now)
    store=server.web_admin.store
    server.replays.cleanup()
    hub=server.session_hub
    protected=set(hub.rooms) if hub else set()
    removed=[]
    if hub:
        with store.connect() as db:
            rows=db.execute("""SELECT id FROM game_rooms r WHERE active=0 AND ended IS NOT NULL AND ended<=?
                AND NOT EXISTS(SELECT 1 FROM replays p WHERE p.room_id=r.id AND (p.ended IS NULL OR p.ended>=?))
                ORDER BY ended LIMIT 100""",(now-ROOM_DAYS*DAY,now-7*DAY)).fetchall()
        data_root=Path(store.path).parent.resolve()
        root=data_root/'session-saves'
        safe_root=not root.is_symlink() and root.resolve().parent==data_root
        for row in rows:
            rid=row['id']
            if rid in protected or not safe_root:continue
            if not re.fullmatch(r'[0-9a-f]{24}',rid):continue
            path=root/rid
            if path.is_symlink() or path.resolve().parent!=root:
                logging.error('Session retention refused unsafe save path');continue
            try:
                if path.exists():shutil.rmtree(path)
            except OSError:
                logging.error('Session retention could not remove saves');continue
            removed.append(rid)
    with store.connect() as db:
        for rid in removed:
            # Recheck the deadline and state before removing relational data.
            if not db.execute('SELECT 1 FROM game_rooms WHERE id=? AND active=0 AND ended<=?',(rid,now-ROOM_DAYS*DAY)).fetchone():continue
            for table in ('session_access','host_rooms'):
                db.execute('DELETE FROM '+table+' WHERE room_id=?',(rid,))
            db.execute('DELETE FROM replay_shares WHERE replay_id IN (SELECT id FROM replays WHERE room_id=?)',(rid,))
            db.execute('DELETE FROM replays WHERE room_id=?',(rid,))
            db.execute('DELETE FROM game_rooms WHERE id=?',(rid,))
        db.execute('DELETE FROM issue_reports WHERE (resolved=1 AND resolved_at<=?) OR (resolved=0 AND created<=?)',
                   (now-RESOLVED_REPORT_DAYS*DAY,now-REPORT_DAYS*DAY))
        db.execute('DELETE FROM audit WHERE time<=?',(now-AUDIT_DAYS*DAY,))
        for table in ('sessions','oauth','player_codes','player_resets','mfa_pending'):
            db.execute('DELETE FROM '+table+' WHERE expires<=?',(now,))
        db.execute('DELETE FROM player_limits WHERE started<=?',(now-DAY,))
        db.execute('DELETE FROM mfa_limits WHERE window_start<=?',(now-DAY,))
    return len(removed)
