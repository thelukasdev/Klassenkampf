import asyncio
import json
import unittest
from pathlib import Path
import test_server as base
from game_sessions import GameSessions
from game_worker import SessionWorker,RemoteGame
import games

class ControlTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    websocket=base.ServerTests.websocket
    receive=base.ServerTests.receive
    until=base.ServerTests.until
    send=base.ServerTests.send
    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app);self.app.session_hub=self.hub
        self.a=self.hub.create('A');self.b=self.hub.create('B')
        self.store=self.app.web_admin.store
        with self.store.connect() as db:
            db.execute("INSERT INTO admins VALUES('owner@example.org',NULL,'owner',0)")
            db.execute("INSERT INTO admins VALUES('guide@example.org',NULL,'guide',0)")
            db.execute('INSERT INTO session_access VALUES(?,?)',('guide@example.org',self.a['id']))
    async def asyncTearDown(self):
        for r in self.hub.rooms.values():
            for m in list(r.matches.values()):await r.control.cancel_match(m)
            if r.worker:await r.worker.stop()
        await base.ServerTests.asyncTearDown(self)
    def headers(self,email='owner@example.org'):
        w=self.app.web_admin;t=self.store.new_session(email);s=self.store.session(t)
        return {'Cookie':w.COOKIE+'='+t,'X-CSRF-Token':s['csrf'],'Origin':'https://games.example.org','Content-Type':'application/json'}
    async def test_guide_scope_and_mutation_boundaries(self):
        h=self.headers('guide@example.org')
        response=await self.http('/api/admin/overview',extra_headers=h)
        data=json.loads(response.split(b'\r\n\r\n',1)[1])
        self.assertEqual([s['id'] for s in data['sessions']],[self.a['id']])
        self.assertNotIn('memory',data['server'])
        self.assertIn(b'403',await self.http('/api/admin/overview?session='+self.b['id'],extra_headers=h))
        for obj in ({'action':'create-session','value':'Forbidden'}, {'action':'mode','value':'random','session':self.b['id']},
                    {'action':'move-player','session':self.a['id'],'value':'p','target':self.b['id']},
                    {'action':'role','value':'guide@example.org','role':'admin'}):
            self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers=h,data=obj))
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=h,data={'action':'mode','value':'random','session':self.a['id']}))
    async def test_worker_processes_and_match_instances_are_private(self):
        w1,w2=SessionWorker(),SessionWorker()
        try:
            a=RemoteGame(w1,'a','pong',2);b=RemoteGame(w1,'b','pong',2);c=RemoteGame(w2,'a','pong',2)
            await a.step();await b.step();await c.step()
            self.assertNotEqual(w1.process.pid,w2.process.pid)
            a.set_input(1,1);await a.step()
            self.assertEqual(len(w1.ids),2);self.assertEqual(len(w2.ids),1)
            await a.close();self.assertIsNotNone(w1.process)
            await b.close();self.assertIsNone(w1.process)
            await c.step();self.assertIsNotNone(w2.process)
        finally:await w1.stop();await w2.stop()
    async def test_all_game_engines_run_in_worker(self):
        w=SessionWorker()
        try:
            for gid,cls in games.GAMES.items():
                g=RemoteGame(w,gid,gid,cls.min_players);await g.step();self.assertTrue(g.snapshot(1) if cls.per_view else g.snapshot());await g.close()
        finally:await w.stop()
    async def test_rules_pause_neutral_cancel_history_and_restore(self):
        r=self.hub.get(self.a['id']);p=r._add_player('one');q=r._add_player('two')
        await r.control.action({'action':'rules','rules':{'enabled':['pong'],'credits_win':7}})
        with self.assertRaises(ValueError):r.start_match('tron',[p,q])
        m=r.start_match('pong',[p,q]);await asyncio.sleep(.2)
        await r.control.action({'action':'pause-match','value':m.id});self.assertTrue(m.paused)
        await r.control.action({'action':'end-match','value':m.id})
        self.assertEqual((p.credits,q.credits),(0,0));self.assertEqual(r.history[-1]['reason'],'admin')
        r.admin_save('before');r.rules['credits_win']=2;await r.admin_load('before');self.assertEqual(r.rules['credits_win'],7)
        self.assertEqual(len(r.history),1)
    async def test_move_preserves_profile_and_rejects_collisions(self):
        r=self.hub.get(self.a['id']);t=self.hub.get(self.b['id']);p=r._add_player('Same');p.credits=12;p.token_hash='hash';r.save()
        t._add_player('Same')
        with self.assertRaises(ValueError):await r.control.action({'action':'move-player','value':'same','target':t.room_id})
        self.assertIn('same',r.players);t.players.clear()
        await r.control.action({'action':'move-player','value':'same','target':t.room_id})
        self.assertNotIn('same',r.players);self.assertEqual(t.players['same'].credits,12);self.assertEqual(t.players['same'].token_hash,'hash')
    async def test_qr_scoped_and_roles_assigned(self):
        h=self.headers();g=self.headers('guide@example.org')
        self.assertIn(b'403',await self.http('/api/admin/join?session='+self.b['id'],extra_headers=g))
        response=await self.http('/api/admin/join?session='+self.a['id'],extra_headers=g)
        data=json.loads(response.split(b'\r\n\r\n',1)[1]);self.assertIn('?code='+self.a['code'],data['url']);self.assertTrue(data['qr'].startswith('data:image/svg+xml'))
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=h,data={'action':'assign-session','value':'guide@example.org','session':self.b['id']}))
        self.assertIn(self.b['id'],self.store.allowed_rooms(self.store.session(g['Cookie'].split('=',1)[1])))

    async def test_real_websocket_match_worker_and_failure_isolation(self):
        from test_game_sessions import SessionTests
        a=self.hub.get(self.a['id']);b=self.hub.get(self.b['id'])
        ra,wa,*_=await SessionTests.join(self,self.a['code'],'A1')
        rb,wb,*_=await SessionTests.join(self,self.a['code'],'A2')
        await self.send(wa,{'t':'challenge','target':a.players['a2'].pid,'game':'pong'})
        await self.until(rb,'challenged')
        await self.send(wb,{'t':'accept','from':a.players['a1'].pid})
        await self.until(ra,'match_start');await self.until(rb,'match_start')
        self.assertIsInstance((await self.until(ra,'state'))['s'],dict)
        other=b.start_match('pong',[b._add_player('B1'),b._add_player('B2')])
        await asyncio.sleep(.2)
        self.assertIsNotNone(other.game.worker.process)
        a.worker.process.kill()
        await self.until(ra,'match_cancelled')
        await asyncio.sleep(.1)
        self.assertFalse(other.finished);self.assertTrue(b.worker.process.returncode is None)
        self.assertEqual(a.history[-1]['reason'],'worker_error');self.assertEqual(a.players['a1'].credits,0)

    async def test_cancelling_one_match_keeps_shared_session_worker_alive(self):
        r=self.hub.get(self.a['id'])
        m=r.start_match('pong',[r._add_player('P1'),r._add_player('P2')])
        other=r.start_match('pong',[r._add_player('P3'),r._add_player('P4')])
        await asyncio.sleep(.2);pid=r.worker.process.pid
        await r.control.cancel_match(m)
        await asyncio.sleep(.15)
        self.assertFalse(other.finished);self.assertEqual(r.worker.process.pid,pid);self.assertEqual(r.worker.failures,0)
