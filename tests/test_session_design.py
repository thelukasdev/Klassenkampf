import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock
import test_player_accounts as accountbase
from session_design import validate,DEFAULT

class SessionDesignTests(unittest.IsolatedAsyncioTestCase):
    http=accountbase.PlayerAccountTests.http
    asyncSetUp=accountbase.PlayerAccountTests.asyncSetUp
    asyncTearDown=accountbase.PlayerAccountTests.asyncTearDown
    body=accountbase.PlayerAccountTests.body
    cookie=accountbase.PlayerAccountTests.cookie
    signup=accountbase.PlayerAccountTests.signup
    preauth=accountbase.PlayerAccountTests.preauth
    async def test_design_is_owned_persistent_and_broadcast(self):
        h,_,_,_=await self.signup()
        response=await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Sommerfest','design':{'accent':'#CC88FF','background':'#181020'}})
        self.assertIn(b'200 OK',response);rid=self.body(response)['result']['id'];room=self.hub.get(rid)
        class Connection:pass
        conn=Connection();conn.alive=True;conn.authed=True;conn.send=AsyncMock()
        room.joined_connections.add(conn)
        update={'action':'session-design','session':rid,'value':'Klassenfest','design':{'accent':'#ffbb44','background':'#101c20'}}
        self.assertIn(b'200 OK',await self.http('/api/player/action',method='POST',extra_headers=h,data=update))
        self.assertEqual(room.design,update['design']);self.assertEqual(room.room_name,'Klassenfest')
        conn.send.assert_awaited_once();self.assertEqual(conn.send.call_args.args[0]['t'],'session-design')
        state=self.hub.state(rid);self.assertEqual(state['design'],update['design'])
        del self.hub.rooms[rid];loaded=self.hub.get(rid)
        self.assertEqual(loaded.design,update['design']);self.assertEqual(loaded.room_name,'Klassenfest')
        other=self.hub.create('Andere Klasse');self.assertEqual(self.hub.get(other['id']).design,DEFAULT)
        update['session']=other['id']
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data=update))
        self.assertEqual(self.hub.get(other['id']).room_name,'Andere Klasse')
    async def test_bad_colors_names_and_csrf_do_not_mutate(self):
        h,_,_,_=await self.signup()
        rid=self.body(await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Original'}))['result']['id']
        for design in ({'accent':'red;url(x)'},{'background':'#ffffff'},{'accent':None},{'css':'body{}'},[]):
            r=await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'session-design','session':rid,'value':'Changed','design':design})
            self.assertIn(b'400',r);self.assertEqual(self.hub.get(rid).room_name,'Original')
        self.assertIn(b'400',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'session-design','session':rid,'value':'x'*81}))
        bad={**h,'X-CSRF-Token':'wrong'}
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=bad,data={'action':'session-design','session':rid,'value':'Changed'}))
    async def test_lobby_payload_and_legacy_state(self):
        row=self.hub.create('Test');room=self.hub.get(row['id']);p=room._add_player('Spieler')
        self.assertEqual(room.lobby_view(p)['design'],DEFAULT)
        room._apply_state({'players':{},'design':{'background':'invalid'}})
        self.assertEqual(room.design,DEFAULT)

class PreviewMetadataTests(unittest.TestCase):
    def test_every_registered_game_has_small_local_preview_and_duration(self):
        import games
        for item in games.GAME_INFO:
            self.assertGreaterEqual(item['max'],item['min'])
            self.assertTrue(item['duration'].endswith('Min.'))
            path=Path(__file__).parents[1]/'static'/item['preview'].lstrip('/')
            self.assertTrue(path.is_file());self.assertLess(path.stat().st_size,12000)
            self.assertNotIn('<script',path.read_text())
