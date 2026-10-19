import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import test_server as base
from game_sessions import GameSessions
from public_status import StatusStore
from retention import cleanup,DAY


class RetentionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=base.ServerTests.asyncSetUp
    asyncTearDown=base.ServerTests.asyncTearDown

    async def test_old_closed_rooms_saves_reports_and_audit_but_never_active_rooms(self):
        hub=GameSessions(self.app);self.app.session_hub=hub;now=int(time.time())
        old=hub.create('old');fresh=hub.create('fresh');active=hub.create('active')
        await hub.end(old['id']);await hub.end(fresh['id'])
        root=Path(self.tmp.name)/'session-saves'
        for room in (old,fresh,active):
            folder=root/room['id'];folder.mkdir(parents=True);(folder/'save.json').write_text('{}')
        with self.app.web_admin.store.connect() as db:
            db.execute('UPDATE game_rooms SET ended=?,created=? WHERE id=?',(now-31*DAY,now-40*DAY,old['id']))
            db.execute('UPDATE game_rooms SET created=? WHERE id=?',(now-40*DAY,active['id']))
            db.execute('INSERT INTO session_access VALUES(?,?)',('guide@example.org',old['id']))
            for ref,created,resolved,resolved_at in [('old-open',now-91*DAY,0,None),('fresh-open',now,0,None),('old-done',now-100*DAY,1,now-31*DAY),('fresh-done',now-100*DAY,1,now)]:
                db.execute("INSERT INTO issue_reports(reference,created,page,description,resolved,resolved_at) VALUES(?,?,'/','test',?,?)",(ref,created,resolved,resolved_at))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',(now-91*DAY,'test@example.org','test','old'))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',(now,'test@example.org','test','fresh'))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('expired','nobody','csrf',now-1))
        self.assertEqual(cleanup(self.app,now),1)
        self.assertFalse((root/old['id']).exists());self.assertTrue((root/fresh['id']).exists());self.assertTrue((root/active['id']).exists())
        with self.app.web_admin.store.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM game_rooms WHERE id=?',(old['id'],)).fetchone())
            self.assertIsNotNone(db.execute('SELECT 1 FROM game_rooms WHERE id=?',(active['id'],)).fetchone())
            self.assertIsNone(db.execute('SELECT 1 FROM session_access WHERE room_id=?',(old['id'],)).fetchone())
            self.assertEqual({r[0] for r in db.execute('SELECT reference FROM issue_reports')},{'fresh-open','fresh-done'})
            self.assertEqual({r[0] for r in db.execute("SELECT detail FROM audit WHERE action='test'")},{'fresh'})
            self.assertIsNone(db.execute("SELECT 1 FROM sessions WHERE token='expired'").fetchone())
        self.assertEqual(cleanup(self.app,now),0)

    async def test_resolved_report_window_and_reopen(self):
        reports=self.app.web_admin.reports;store=self.app.web_admin.store
        with store.connect() as db:db.execute("INSERT INTO issue_reports(reference,created,page,description) VALUES('KK-TEST',1,'/','test')")
        with patch('reports.time.time',return_value=100):reports.resolve({'role':'owner','email':'a@example.org'},'KK-TEST',True)
        with patch('reports.time.time',return_value=200):reports.resolve({'role':'owner','email':'a@example.org'},'KK-TEST',True)
        with store.connect() as db:self.assertEqual(db.execute('SELECT resolved_at FROM issue_reports').fetchone()[0],100)
        reports.resolve({'role':'owner','email':'a@example.org'},'KK-TEST',False)
        with store.connect() as db:self.assertIsNone(db.execute('SELECT resolved_at FROM issue_reports').fetchone()[0])


class StatusRetentionTests(unittest.TestCase):
    def test_status_90_days_and_ended_sessions_30_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=StatusStore(Path(tmp)/'status.sqlite3');now=int(time.time())
            with store.connect() as db:
                for cid,kind,state,since in [('platform','service','operational',now-100*DAY),('old','session','ended',now-31*DAY),('fresh','session','ended',now)]:
                    db.execute('INSERT INTO components VALUES(?,?,?,?,?,?,?)',(cid,cid,kind,state,since,now,'{}'))
                    db.execute('INSERT INTO events(time,component,state,detail) VALUES(?,?,?,?)',(now,cid,state,'fresh'))
                db.execute("INSERT INTO events(time,component,state,detail) VALUES(?,'platform','down','old')",(now-91*DAY,))
                db.execute("INSERT INTO daily VALUES('platform',?,'down',15)",(time.strftime('%Y-%m-%d',time.gmtime(now-91*DAY)),))
            store.cleanup(now)
            with store.connect() as db:
                self.assertEqual({r[0] for r in db.execute('SELECT id FROM components')},{'platform','fresh'})
                self.assertFalse(db.execute("SELECT 1 FROM events WHERE detail='old' OR component='old'").fetchall())
                self.assertFalse(db.execute('SELECT 1 FROM daily').fetchall())
