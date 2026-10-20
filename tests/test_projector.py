import asyncio
import json
import time
import unittest
import test_replays as base


class ProjectorTests(unittest.IsolatedAsyncioTestCase):
    http=base.ReplayTests.http
    headers=base.ReplayTests.headers
    body=base.ReplayTests.body
    match=base.ReplayTests.match
    asyncSetUp=base.ReplayTests.asyncSetUp
    asyncTearDown=base.ReplayTests.asyncTearDown

    async def public(self,token,**kwargs):
        return await self.http('/api/beamer',extra_headers={'X-Projector-Token':token},**kwargs)

    async def test_explicit_release_header_only_and_public_view_allowlist(self):
        m=await self.match()
        self.assertIn(b'404',await self.public(''))
        self.r.projector.select('match:'+str(m.id));token=self.r.projector.token
        self.assertEqual(len(token),64)
        self.assertIn(b'404',await self.http('/api/beamer?token='+token))
        self.assertIn(b'404',await self.public(token,method='POST',data={'u':63}))
        for bad in (token[:-1],token+'a','x'*64):self.assertIn(b'404',await self.public(bad))
        m.last_frame['views']['1']={'secret':'NEVER-PROJECT'}
        result=await self.public(token);data=self.body(result)
        self.assertIn(b'200',result);self.assertIn(b'Cache-Control: no-store',result)
        self.assertEqual(data['game'],'pong');self.assertEqual(set(data['frame']['views']),{'0'})
        for secret in (self.r.login_code,self.r.room_id,'token_hash','NEVER-PROJECT',token):self.assertNotIn(secret,json.dumps(data))
        self.assertIn(b'200',await self.http('/beamer'));self.assertIn(b'200',await self.http('/beamer.js'))

    async def test_switch_match_and_ranking_keeps_link_then_revoke_rotates(self):
        first=await self.match();self.r.projector.select('match:'+str(first.id));token=self.r.projector.token
        players=[self.r._add_player('Three'),self.r._add_player('Four')]
        second=self.r.start_match('tron',players)
        for _ in range(50):
            if second.last_frame:break
            await asyncio.sleep(.02)
        previous=self.body(await self.public(token))['revision']
        self.r.projector.select('match:'+str(second.id));self.assertEqual(self.r.projector.token,token)
        data=self.body(await self.public(token));self.assertEqual(data['game'],'tron');self.assertGreater(data['revision'],previous)
        self.assertEqual(data['players'],['Three','Four'])
        self.r.players['three'].credits=25
        self.r.projector.select('ranking');data=self.body(await self.public(token))
        self.assertEqual(data['mode'],'ranking');self.assertNotIn('frame',data);self.assertEqual(data['ranking'][0],{'name':'Three','credits':25})
        self.r.projector.select('off');self.assertIn(b'404',await self.public(token))
        self.r.projector.select('ranking');self.assertNotEqual(self.r.projector.token,token)
        self.assertIn(b'404',await self.public(token))

    async def test_match_end_pause_and_session_end_clear_projection(self):
        m=await self.match();self.r.projector.select('match:'+str(m.id));token=self.r.projector.token
        m.paused=True;m.disconnected[m.players[0]]=time.monotonic()+20
        data=self.body(await self.public(token));self.assertEqual(data['state'],'paused');self.assertEqual(data['reconnecting'],['One'])
        await self.r.control.cancel_match(m)
        data=self.body(await self.public(token));self.assertEqual(data['mode'],'ranking');self.assertEqual(data['state'],'finished');self.assertNotIn('frame',data)
        await self.hub.end(self.r.room_id);self.assertIn(b'404',await self.public(token));self.assertIsNone(self.r.projector.token)

    async def test_hidden_games_never_reach_projector_and_invalid_selection_is_atomic(self):
        m=await self.match('wnr');self.r.projector.select('ranking');token=self.r.projector.token
        with self.assertRaises(ValueError):self.r.projector.select('match:'+str(m.id))
        self.assertEqual(self.r.projector.mode,'ranking');self.assertEqual(self.r.projector.token,token)
        for bad in ('match:999999','match:-1','everything',None):
            with self.assertRaises(ValueError):self.r.projector.select(bad)
        self.r.projector.mode='match';self.r.projector.match_id=m.id
        data=self.body(await self.public(token));self.assertEqual(data['mode'],'ranking');self.assertNotIn('frame',data);self.assertNotIn('game',data)

    async def test_guide_room_scope_csrf_and_admin_overview(self):
        guide=self.headers('guide@example.org');action={'action':'projector','value':'ranking','session':self.r.room_id}
        self.assertIn(b'401',await self.http('/api/admin/action',method='POST',data=action))
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',data=action,extra_headers={**guide,'X-CSRF-Token':'bad'}))
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',data={**action,'session':self.b['id']},extra_headers=guide))
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',data=action,extra_headers=guide))
        overview=self.body(await self.http('/api/admin/overview?session='+self.r.room_id,extra_headers=guide))
        self.assertEqual(overview['projector']['url'],'/beamer#'+self.r.projector.token)
        self.assertNotIn('projector',self.r._state_dict())
        self.assertIn(b'403',await self.http('/api/admin/overview?session='+self.b['id'],extra_headers=guide))

    async def test_player_requires_both_permissions_and_own_room(self):
        web=self.app.web_admin;identity='player:host@example.org'
        with web.store.connect() as db:
            db.execute("INSERT INTO player_accounts VALUES('host@example.org','unused',0)")
            db.execute("INSERT INTO admins VALUES(?,NULL,'host',0)",(identity,))
            db.execute('INSERT INTO session_access VALUES(?,?)',(identity,self.r.room_id))
        token=web.store.new_session(identity);session=web.store.session(token)
        headers={'Cookie':web.player_auth.COOKIE+'='+token,'X-CSRF-Token':session['csrf'],'Origin':'https://games.example.org','Content-Type':'application/json'}
        action={'action':'projector','value':'ranking','session':self.r.room_id}
        from player_permissions import DEFAULTS
        for permissions in ({},{'manage_games':True}):
            web.player_auth.permissions.set({'email':'owner@example.org','role':'owner'},'host@example.org',{**DEFAULTS,**permissions})
            self.assertIn(b'403',await self.http('/api/player/action',method='POST',data=action,extra_headers=headers))
        web.player_auth.permissions.set({'email':'owner@example.org','role':'owner'},'host@example.org',{**DEFAULTS,'manage_games':True,'view_results':True})
        self.assertIn(b'200',await self.http('/api/player/action',method='POST',data=action,extra_headers=headers))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',data={**action,'session':self.b['id']},extra_headers=headers))

    async def test_ranking_is_bounded_and_excludes_banned_players(self):
        for i in range(30):self.r._add_player('Player'+str(i)).credits=i
        self.r.banned.add('player29');self.r.projector.select('ranking')
        data=self.body(await self.public(self.r.projector.token));self.assertEqual(len(data['ranking']),20)
        self.assertEqual(data['ranking'][0]['name'],'Player28');self.assertNotIn('Player29',json.dumps(data))
