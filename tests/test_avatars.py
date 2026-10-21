import json
from pathlib import Path
import test_player_accounts as accounts
import unittest
from avatars import safe_avatar

class AvatarTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=accounts.PlayerAccountTests.asyncSetUp
    asyncTearDown=accounts.PlayerAccountTests.asyncTearDown
    http=accounts.PlayerAccountTests.http
    body=accounts.PlayerAccountTests.body
    cookie=accounts.PlayerAccountTests.cookie
    preauth=accounts.PlayerAccountTests.preauth
    signup=accounts.PlayerAccountTests.signup

    async def test_persistence_csrf_allowlist_and_isolation(self):
        h,*_=await self.signup('avatar@example.org')
        path='/auth/player/avatar'
        self.assertIn(b'403',await self.http(path))
        default=self.body(await self.http(path,extra_headers=h));self.assertEqual(default['avatar'],'robot');self.assertEqual(len(default['choices']),8)
        bad={**h,'X-CSRF-Token':'wrong'}
        self.assertIn(b'403',await self.http(path,method='POST',extra_headers=bad,data={'avatar':'fox'}))
        for value in ['../admin','https://example.org/p.png','<svg>',None,[],{}]:
            self.assertIn(b'400',await self.http(path,method='POST',extra_headers=h,data={'avatar':value}))
        r=await self.http(path,method='POST',extra_headers=h,data={'avatar':'fox','email':'other@example.org'})
        self.assertIn(b'200',r);self.assertEqual(self.auth.avatar('avatar@example.org'),'fox');self.assertEqual(self.auth.avatar('other@example.org'),'robot')
        from player_auth import PlayerAuth
        self.assertEqual(PlayerAuth(self.app.web_admin).avatar('avatar@example.org'),'fox')
        me=self.body(await self.http('/api/player/me',extra_headers=h));self.assertEqual(me['user']['role'],'host')

    async def test_join_live_update_sanitized_restore_and_delete(self):
        from server import Conn
        h,*_=await self.signup('avatar@example.org')
        room=self.hub.get(self.hub.create('Avatar test')['id'])
        class Writer:
            def write(self,b):pass
            async def drain(self):pass
        conn=Conn(Writer());conn.account_email='avatar@example.org'
        p=room._add_player('Test');p.conn=conn
        await self.http('/auth/player/avatar',method='POST',extra_headers=h,data={'avatar':'owl'})
        self.assertEqual(p.avatar,'owl');self.assertEqual(room.lobby_view(p)['players'][0]['avatar'],'owl')
        state=room._state_dict();self.assertNotIn('avatar@example.org',json.dumps(state));self.assertEqual(state['players']['Test']['avatar'],'owl')
        state['players']['Test']['avatar']='../../evil';room._apply_state(state);self.assertEqual(room.players['test'].avatar,'robot')
        await self.app.web_admin.manage_player({'email':'owner@example.org','role':'owner'},'delete-player-account','avatar@example.org')
        with self.auth.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM player_avatars').fetchone()[0],0)
        self.assertEqual(safe_avatar([]),'robot')

    async def test_local_assets_and_account_picker(self):
        for id in ('robot','fox','cat','bear','owl','ghost','rocket','bolt'):
            r=await self.http('/avatars/'+id+'.svg');self.assertIn(b'200',r);self.assertIn(b'image/svg+xml',r);self.assertNotIn(b'<script',r)
        page=await self.http('/account/security');self.assertIn(b'avatarChoices',page)
