import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_player_accounts as accounts
from turnstile import Turnstile

class TurnstileTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=accounts.PlayerAccountTests.asyncSetUp
    asyncTearDown=accounts.PlayerAccountTests.asyncTearDown
    http=accounts.PlayerAccountTests.http
    body=accounts.PlayerAccountTests.body
    cookie=accounts.PlayerAccountTests.cookie
    preauth=accounts.PlayerAccountTests.preauth
    signup=accounts.PlayerAccountTests.signup

    def enable(self):
        c=self.auth.turnstile;c.sitekey='test-public-sitekey';c.secret='test-private-secret';return c

    async def test_required_before_mail_and_password_hashing(self):
        c=self.enable();h=await self.preauth()
        self.assertEqual(self.body(await self.http('/auth/player/csrf'))['turnstile_sitekey'],'test-public-sitekey')
        for token in [None,'',{},'x'*2049]:
            with patch.object(c,'request') as remote:
                r=await self.http('/auth/player/register',method='POST',extra_headers=h,data={'email':'new@example.org','password':'valid-password-123','turnstile_token':token})
                self.assertIn(b'400',r);remote.assert_not_called();self.sender.assert_not_called()

    async def test_verification_checks_hostname_action_and_replay_failure(self):
        c=self.enable()
        for response in [{'success':False,'error-codes':['timeout-or-duplicate']},{'success':True,'hostname':'evil.example.org','action':'register'},{'success':True,'hostname':'games.example.org','action':'login'},[],{'success':1,'hostname':'games.example.org','action':'register'}]:
            with patch.object(c,'request',return_value=response):
                with self.assertRaises(ValueError):await c.verify('token')
        with patch.object(c,'request',return_value={'success':True,'hostname':'games.example.org','action':'register'}):await c.verify('token')
        with patch.object(c,'request',side_effect=TimeoutError('private-secret-token')):
            with self.assertRaisesRegex(ValueError,'momentan nicht erreichbar') as error:await c.verify('token')
            self.assertNotIn('private-secret',str(error.exception))

    async def test_registration_succeeds_only_after_verification(self):
        c=self.enable();h=await self.preauth()
        with patch.object(c,'request',return_value={'success':True,'hostname':'games.example.org','action':'register'}) as remote:
            r=await self.http('/auth/player/register',method='POST',extra_headers=h,data={'email':'new@example.org','password':'valid-password-123','turnstile_token':'browser-token'})
        self.assertIn(b'200',r);remote.assert_called_once_with('browser-token');self.sender.assert_called_once()

    async def test_login_and_recovery_do_not_require_turnstile(self):
        h,token,pre,code=await self.signup();self.enable();headers=await self.preauth()
        with patch.object(self.auth.turnstile,'verify') as verify:
            r=await self.http('/auth/player/login',method='POST',extra_headers=headers,data={'email':'owner@example.org','password':'test-player-password-123'})
            self.assertIn(b'200',r);verify.assert_not_called()

    async def test_private_config_loading_and_api_payload(self):
        path=Path(self.auth.store.path).parent/'turnstile.json'
        path.write_text(json.dumps({'sitekey':'public-key','secret':'private-key'}),encoding='utf-8')
        c=Turnstile(self.app.web_admin);self.assertEqual(c.sitekey,'public-key')
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"success":true}'
        with patch('urllib.request.urlopen',return_value=Response()) as request:
            self.assertEqual(c.request('one-time-token'),{'success':True});req=request.call_args.args[0]
            self.assertEqual(req.full_url,Turnstile.ENDPOINT);self.assertIn(b'response=one-time-token',req.data);self.assertEqual(request.call_args.kwargs['timeout'],8)
        path.write_text('{"sitekey":"only-one-key"}',encoding='utf-8')
        with self.assertRaises(ValueError):Turnstile(self.app.web_admin)
