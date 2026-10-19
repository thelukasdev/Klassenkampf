import asyncio
import json
from pathlib import Path
import unittest

import server
import test_server as base
from game_sessions import GameSessions


class SessionTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    websocket=base.ServerTests.websocket
    receive=base.ServerTests.receive
    until=base.ServerTests.until
    send=base.ServerTests.send
    asyncTearDown=base.ServerTests.asyncTearDown

    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app)
        self.app.session_hub=self.hub
        self.a=self.hub.create('Klasse A')
        self.b=self.hub.create('Klasse B')

    async def join(self,code,nick,tok=None):
        reader,writer,headers=await self.websocket()
        await self.until(reader,'welcome')
        await self.send(writer,{'t':'login','code':code,'nick':nick,'tok':tok})
        login=await self.until(reader,'login_ok')
        profile=await self.until(reader,'nick_ok')
        lobby=await self.until(reader,'lobby')
        return reader,writer,profile['tok'],lobby,login

    async def test_codes_same_nickname_and_players_are_isolated(self):
        self.assertNotEqual(self.a['code'],self.b['code'])
        ra,wa,ta,la,login=await self.join(self.a['code'].lower(),'Sam')
        rb,wb,tb,lb,_=await self.join(self.b['code'],'Sam')
        self.assertEqual(login['session_name'],'Klasse A')
        self.assertNotEqual(ta,tb)
        self.assertEqual(len(la['players']),1)
        self.assertEqual(len(lb['players']),1)
        a,b=self.hub.get(self.a['id']),self.hub.get(self.b['id'])
        a.players['sam'].credits=19;a.save()
        self.assertEqual(b.players['sam'].credits,0)
        await a.admin_ban('sam')
        self.assertNotIn('sam',b.banned)
        await self.send(wb,{'t':'lobby'})
        self.assertEqual((await self.until(rb,'lobby'))['you']['credits'],0)

    async def test_cross_session_challenge_cannot_target_other_session(self):
        ra,wa,*_=await self.join(self.a['code'],'Alice')
        rb,wb,*_=await self.join(self.b['code'],'Bob')
        target=self.hub.get(self.b['id']).players['bob'].pid
        await self.send(wa,{'t':'challenge','target':target,'game':'pong'})
        await self.until(ra,'err')
        self.assertEqual(len(self.hub.get(self.a['id']).matches),0)
        self.assertEqual(len(self.hub.get(self.b['id']).matches),0)

    async def test_end_closes_only_its_players_and_does_not_award_a_win(self):
        ra,wa,*_=await self.join(self.a['code'],'Alice')
        ro,wo,*_=await self.join(self.a['code'],'Other')
        rb,wb,*_=await self.join(self.b['code'],'Bob')
        room=self.hub.get(self.a['id'])
        await self.send(wa,{'t':'challenge','target':room.players['other'].pid,'game':'pong'})
        await self.until(ro,'challenged')
        await self.send(wo,{'t':'accept','from':room.players['alice'].pid})
        await self.until(ra,'match_start')
        await self.hub.end(self.a['id'])
        await self.until(ra,'session_ended')
        self.assertEqual(room.players['alice'].credits,0)
        self.assertEqual(room.players['other'].credits,0)
        self.assertEqual(room.players['alice'].record,{})
        await self.send(wb,{'t':'lobby'})
        self.assertEqual((await self.until(rb,'lobby'))['session_name'],'Klasse B')
        reader,writer,_=await self.websocket();await self.until(reader,'welcome')
        await self.send(writer,{'t':'login','code':self.a['code']})
        await self.until(reader,'login_err')
        with self.assertRaises(ValueError):
            await self.hub.action({'action':'mode','value':'random','session':self.a['id']})
        archived=self.hub.overview(self.a['id'])
        self.assertIsNone(archived['code'])
        self.assertFalse(archived['session_active'])

    async def test_restart_preserves_codes_data_and_ended_status(self):
        ra,wa,token,*_=await self.join(self.b['code'],'Bob')
        room=self.hub.get(self.b['id']);room.players['bob'].credits=11;room.save()
        await self.hub.end(self.a['id'])
        reloaded=server.Server('127.0.0.1',0,False,headless=True,sessions=True)
        hub=reloaded.session_hub
        self.assertNotIn(self.a['id'],hub.rooms)
        self.assertEqual(hub.get(self.b['id']).login_code,self.b['code'])
        self.assertEqual(hub.get(self.b['id']).players['bob'].credits,11)
        self.assertFalse(hub.get(self.b['id']).players['bob'].online)
        self.assertEqual(hub.get(self.b['id']).players['bob'].token_hash,room.players['bob'].token_hash)

    async def test_admin_selection_and_snapshots_cannot_spill_between_sessions(self):
        a,b=self.hub.get(self.a['id']),self.hub.get(self.b['id'])
        await self.hub.action({'action':'mode','value':'random','session':self.a['id']})
        self.assertEqual(a.mode,'random');self.assertEqual(b.mode,'choose')
        pa=a.admin_save('same-name');pb=b.admin_save('same-name')
        self.assertNotEqual(pa,pb)
        self.assertEqual(json.loads(Path(pa).read_text())['mode'],'random')
        self.assertEqual(json.loads(Path(pb).read_text())['mode'],'choose')
        with self.assertRaises(ValueError):
            await self.hub.action({'action':'mode','value':'random'})
        store=self.app.web_admin.store
        with store.connect() as db:
            db.execute('INSERT OR IGNORE INTO admins VALUES(?,NULL,?,0)',('owner@example.org','owner'))
        token=store.new_session('owner@example.org');session=store.session(token)
        headers={'Cookie':self.app.web_admin.COOKIE+'='+token,'Origin':'https://games.example.org',
                 'X-CSRF-Token':session['csrf'],'Content-Type':'application/json'}
        response=await self.http('/api/admin/overview?session='+self.b['id'],extra_headers=headers)
        body=json.loads(response.split(b'\r\n\r\n',1)[1])
        self.assertEqual(body['selected_session'],self.b['id'])
        self.assertEqual(body['code'],self.b['code'])
        self.assertIn(b'400',await self.http('/api/admin/action',method='POST',
                                           data={'action':'mode','value':'random'},extra_headers=headers))

    async def test_legacy_access_is_migrated_once_and_limits_are_enforced(self):
        legacy=[s for s in self.hub.summaries() if s['name']=='Bisherige Spielsitzung']
        self.assertEqual(len(legacy),1)
        await self.join('test-login-secret','Legacy')
        reloaded=GameSessions(self.app)
        self.assertEqual(len(reloaded.summaries()),3)
        for i in range(13):self.hub.create('Room '+str(i))
        with self.assertRaises(ValueError):self.hub.create('Too many')
        with self.assertRaises(ValueError):self.hub.create('')

    async def test_service_shutdown_does_not_create_artificial_wins(self):
        service=asyncio.create_task(self.app.serve())
        await asyncio.sleep(0.05)
        ra,wa,*_=await self.join(self.a['code'],'Alice')
        ro,wo,*_=await self.join(self.a['code'],'Other')
        room=self.hub.get(self.a['id'])
        room.start_match('pong',[room.players['alice'],room.players['other']])
        await self.until(ra,'match_start')
        service.cancel()
        with self.assertRaises(asyncio.CancelledError):await service
        await asyncio.sleep(0.05)
        self.assertEqual(room.players['alice'].credits,0)
        self.assertEqual(room.players['other'].credits,0)
        self.assertEqual(room.players['other'].record,{})

    async def test_opaque_room_address_is_not_a_login_credential(self):
        r,w,token,lobby,login=await self.join(self.a['code'],'AddressTest')
        path=login['room_path'];self.assertRegex(path,r'^/raum/[0-9a-f]{64}$')
        self.assertEqual(path,self.hub.get(self.a['id']).room_path)
        self.assertNotEqual(path,self.hub.get(self.b['id']).room_path)
        response=await self.http(path)
        self.assertIn(b'200 OK',response)
        body=response.split(b'\r\n\r\n',1)[1].decode()
        self.assertNotIn(self.a['code'],body);self.assertIn('src="/app.js"',body)
        guest,gw,_=await self.websocket();await self.until(guest,'welcome')
        await self.send(gw,{'t':'login','code':path.rsplit('/',1)[-1],'nick':'Intruder'})
        await self.until(guest,'login_err');self.assertNotIn('intruder',self.hub.get(self.a['id']).players)
