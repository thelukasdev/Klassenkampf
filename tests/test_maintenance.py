import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import maintenance
import server
import test_player_accounts

class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_player_accounts.PlayerAccountTests.asyncSetUp
    asyncTearDown=test_player_accounts.PlayerAccountTests.asyncTearDown
    http=test_player_accounts.PlayerAccountTests.http
    body=test_player_accounts.PlayerAccountTests.body
    admin_headers=test_player_accounts.PlayerAccountTests.admin_headers
    async def test_admin_activation_blocks_public_pages_but_keeps_admin_and_assets(self):
        h,_=self.admin_headers()
        end=int(time.time())+3600
        data={'action':'maintenance','maintenance':{'enabled':True,'message':'Test <script>alert(1)</script>','ends_at':end}}
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=h,data=data))
        for path in ('/','/login','/account','/demo','/impressum','/datenschutz','/api/v1/games','/api/player/me','/auth/player/register'):
            r=await self.http(path)
            self.assertIn(b'503 Service Unavailable',r)
            self.assertIn(b'Retry-After:',r)
            self.assertIn(b'&lt;script&gt;',r)
            self.assertNotIn(b'<script>alert',r)
            self.assertIn(b'href="/status"',r)
            self.assertNotIn(b'href="/login"',r)
        self.assertIn(b'200',await self.http('/admin'))
        self.assertIn(b'200',await self.http('/healthz'))
        self.assertIn(b'200',await self.http('/maintenance.css'))
        self.assertIn(b'200',await self.http('/api/admin/maintenance',extra_headers=h))
        data['maintenance']['enabled']=False;data['maintenance']['ends_at']=None
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=h,data=data))
        self.assertIn(b'200',await self.http('/'))
    async def test_permissions_validation_and_expiry(self):
        owner,_=self.admin_headers();guide,_=self.admin_headers('guide')
        data={'action':'maintenance','maintenance':{'enabled':True,'message':'Wartung','ends_at':None}}
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers=guide,data=data))
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers={**owner,'X-CSRF-Token':'bad'},data=data))
        data['maintenance']['ends_at']=int(time.time())-1
        self.assertIn(b'400',await self.http('/api/admin/action',method='POST',extra_headers=owner,data=data))
        end=int(time.time())+10;data['maintenance']['ends_at']=end
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=owner,data=data))
        with patch('maintenance.time.time',return_value=end+1):self.assertIn(b'200',await self.http('/'))
    async def test_existing_match_inputs_continue_but_new_matches_are_blocked(self):
        from types import SimpleNamespace
        arena=self.hub.get(self.hub.create('Live')['id'])
        conn=SimpleNamespace(authed=True,alive=True,login_attempts=0,send=AsyncMock())
        p=arena._add_player('Playing');p.conn=conn
        game=SimpleNamespace(set_input=lambda *x:None)
        p.match=SimpleNamespace(finished=False,is_paused=False,gid='c4',game=game,id='live')
        with patch.object(game,'set_input') as input_fn:
            maintenance.save(Path(self.app.web_admin.store.path).parent,{'enabled':True,'message':'Wartung','ends_at':None})
            await arena._on_message(conn,p,{'t':'in','u':1})
            input_fn.assert_called_once()
        await arena._on_message(conn,p,{'t':'challenge'})
        self.assertEqual(conn.send.call_args.args[0]['t'],'maintenance')
        with self.assertRaisesRegex(ValueError,'Wartungsmodus'):arena.start_match('c4',[])
        import hashlib
        p.token_hash=hashlib.sha256(b'return-key').hexdigest()
        conn.send.reset_mock()
        await arena._on_message(conn,None,{'t':'login','nick':'Playing','tok':'wrong','code':arena.login_code})
        self.assertEqual(conn.send.call_args.args[0]['t'],'maintenance')
        with patch.object(arena,'_claim',AsyncMock(return_value=p)) as claim:
            await arena._on_message(conn,None,{'t':'login','nick':'Playing','tok':'return-key','code':arena.login_code})
            claim.assert_awaited_once()
        self.assertTrue(any(c.args[0].get('t')=='maintenance' and c.args[0].get('finish') for c in conn.send.call_args_list))
        # Remove the dummy match before fixture cleanup.
        p.match=None

