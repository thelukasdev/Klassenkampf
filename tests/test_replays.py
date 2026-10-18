import asyncio
import json
import time
import unittest
from unittest.mock import patch
import test_server as base
from game_sessions import GameSessions


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app);self.app.session_hub=self.hub
        self.a=self.hub.create('A');self.b=self.hub.create('B');self.r=self.hub.get(self.a['id'])
        with self.app.web_admin.store.connect() as db:
            db.execute("INSERT INTO admins VALUES('owner@example.org',NULL,'owner',0)")
            db.execute("INSERT INTO admins VALUES('guide@example.org',NULL,'guide',0)")
            db.execute('INSERT INTO session_access VALUES(?,?)',('guide@example.org',self.a['id']))
    async def asyncTearDown(self):
        for r in self.hub.rooms.values():
            for m in list(r.matches.values()):await r.control.cancel_match(m)
            if r.worker:await r.worker.stop()
        await self.app.replays.drain()
        await base.ServerTests.asyncTearDown(self)
    def headers(self,email='owner@example.org'):
        w=self.app.web_admin;t=w.store.new_session(email);s=w.store.session(t)
        return {'Cookie':w.COOKIE+'='+t,'X-CSRF-Token':s['csrf'],'Origin':'https://games.example.org','Content-Type':'application/json'}
    async def match(self,gid='pong'):
        m=self.r.start_match(gid,[self.r._add_player('One'),self.r._add_player('Two')])
        for _ in range(50):
            if m.last_frame:break
            await asyncio.sleep(.02)
        self.assertIsNotNone(m.last_frame);return m
    def body(self,response):return json.loads(response.split(b'\r\n\r\n',1)[1])
    async def test_spectators_need_release_revocation_and_never_get_inputs(self):
        m=await self.match();self.assertIn(b'404',await self.http('/api/watch'))
        await self.r.control.action({'action':'spectators','value':m.id});token=m.spectator_token
        result=await self.http('/api/watch',extra_headers={'X-Spectator-Token':token})
        data=self.body(result);self.assertEqual(data['game'],'pong');self.assertIn('0',data['frame']['views'])
        self.assertNotIn(self.r.login_code,json.dumps(data));self.assertNotIn('token_hash',json.dumps(data))
        self.assertIn(b'404',await self.http('/api/watch',method='POST',data={'u':63},extra_headers={'X-Spectator-Token':token}))
        await self.r.control.action({'action':'spectators','value':m.id})
        self.assertIn(b'404',await self.http('/api/watch',extra_headers={'X-Spectator-Token':token}))
        await self.r.control.action({'action':'spectators','value':m.id});self.assertNotEqual(m.spectator_token,token)
        await self.r.control.cancel_match(m)
        self.assertIn(b'404',await self.http('/api/watch',extra_headers={'X-Spectator-Token':token}))
    async def test_hidden_views_recorded_for_staff_but_not_released(self):
        m=await self.match('wnr')
        with self.assertRaises(ValueError):await self.r.control.action({'action':'spectators','value':m.id})
        await self.r.control.cancel_match(m);await self.app.replays.drain()
        meta=self.app.replays.metadata(self.r.room_id,m.recorder.id)
        frames=self.app.replays.chunk(self.r.room_id,meta['id'],0)
        self.assertEqual(set(frames[0]['views']),{'1','2'})
    async def test_chunked_recording_and_server_side_scope(self):
        m=await self.match();m.paused=True
        for i in range(130):m.recorder.capture({'t':i+1.,'views':m.last_frame['views']})
        await self.r.control.cancel_match(m);await self.app.replays.drain()
        meta=self.app.replays.metadata(self.r.room_id,m.recorder.id);self.assertGreaterEqual(len(meta['segments']),2)
        endpoint='/api/admin/replay?session='+self.r.room_id+'&id='+meta['id']
        self.assertIn(b'401',await self.http(endpoint))
        self.assertIn(b'200',await self.http(endpoint,extra_headers=self.headers('guide@example.org')))
        self.assertIn(b'403',await self.http(endpoint.replace(self.r.room_id,self.b['id']),extra_headers=self.headers('guide@example.org')))
        self.assertIn(b'400',await self.http(endpoint.replace(self.r.room_id,self.b['id']),extra_headers=self.headers()))
        response=await self.http(endpoint.replace('/replay?','/replay-chunk?')+'&chunk=1',extra_headers=self.headers())
        self.assertTrue(self.body(response)['result'])
        self.assertIn(b'400',await self.http(endpoint.replace('/replay?','/replay-chunk?')+'&chunk=-1',extra_headers=self.headers()))
    async def test_retention_deletes_files_and_raw_limit_marks_partial(self):
        m=await self.match()
        with patch('replays.MAX_RAW',1):m.recorder.capture({'t':10.,'views':m.last_frame['views']})
        await self.app.replays.drain();meta=self.app.replays.metadata(self.r.room_id,m.recorder.id)
        self.assertTrue(meta['truncated']);self.assertFalse(m.finished)
        with self.app.web_admin.store.connect() as db:db.execute('UPDATE replays SET ended=? WHERE id=?',(int(time.time())-8*86400,meta['id']))
        self.app.replays.cleanup();self.assertIsNone(self.app.replays.metadata(self.r.room_id,meta['id']))
        self.assertFalse(self.app.replays.directory(meta['id']).exists())
    async def test_storage_failure_does_not_stop_game(self):
        m=await self.match()
        with patch.object(m.recorder,'write',side_effect=OSError('disk full')):
            m.recorder.finish('normal');await self.app.replays.drain()
        self.assertFalse(m.finished)
        meta=self.app.replays.metadata(self.r.room_id,m.recorder.id)
        self.assertTrue(meta['truncated']);self.assertEqual(meta['reason'],'storage_error')
