import json
import time
import unittest
from http.cookies import SimpleCookie
import test_server as base
from web_admin import Denied,AdminStore
from mfa_auth import totp

class WebAdminTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    asyncTearDown=base.ServerTests.asyncTearDown
    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.web=self.app.web_admin;self.store=self.web.store;self.auth=self.web.password_auth
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO admins VALUES(?,NULL,?,0)',('owner@example.org','owner'))

    def headers(self,email='owner@example.org'):
        token=self.store.new_session(email);session=self.store.session(token)
        return {'Cookie':self.web.COOKIE+'='+token,'X-CSRF-Token':session['csrf'],
                'Origin':'https://games.example.org','Content-Type':'application/json'}

    async def login_headers(self):
        response=await self.http('/auth/password/csrf')
        header,body=response.split(b'\r\n\r\n',1)
        raw=next(line[12:] for line in header.decode().split('\r\n') if line.startswith('Set-Cookie: '))
        cookie=SimpleCookie();cookie.load(raw)
        return {'Cookie':self.auth.COOKIE+'='+cookie[self.auth.COOKIE].value,
                'Origin':'https://games.example.org','X-CSRF-Token':json.loads(body)['csrf'],
                'Content-Type':'application/json'}

    async def test_password_login_cookie_hash_logout_and_no_google(self):
        password='correct-test-password-123'
        self.auth.set_encoded('owner@example.org',self.auth.encode(password))
        self.assertTrue(self.auth.ready)
        headers=await self.login_headers()
        response=await self.http('/auth/password/login',method='POST',extra_headers=headers,
                                 data={'email':'OWNER@example.org','password':password})
        self.assertIn(b'200 OK',response)
        setup=json.loads(response.split(b'\r\n\r\n',1)[1])
        self.assertEqual(setup['stage'],'setup')
        self.assertTrue(setup['qr'].startswith('data:image/svg+xml;base64,'))
        self.assertNotIn((self.web.COOKIE+'=').encode(),response)
        self.assertIn(b'401',await self.http('/api/admin/overview'))
        raw=response.split(b'\r\n\r\n',1)[0].decode()
        partial=SimpleCookie();partial.load(next(line[12:] for line in raw.split('\r\n') if line.startswith('Set-Cookie: ')))
        headers['Cookie']+='; '+self.auth.mfa.COOKIE+'='+partial[self.auth.mfa.COOKIE].value
        response=await self.http('/auth/password/mfa',method='POST',extra_headers=headers,
                                 data={'code':totp(setup['secret'],int(time.time())//30)})
        self.assertEqual(len(json.loads(response.split(b'\r\n\r\n',1)[1])['recovery_codes']),10)
        self.assertIn(b'HttpOnly; Secure; SameSite=Lax',response)
        header=response.split(b'\r\n\r\n',1)[0].decode()
        cookie=SimpleCookie();cookie.load(next(line[12:] for line in header.split('\r\n') if line.startswith('Set-Cookie: ')))
        token=cookie[self.web.COOKIE].value
        session=self.store.session(token);self.assertEqual(session['role'],'owner')
        authorized={'Cookie':self.web.COOKIE+'='+token,'Origin':'https://games.example.org','X-CSRF-Token':session['csrf']}
        self.assertIn(b'200 OK',await self.http('/api/admin/overview',extra_headers=authorized))
        self.assertIn(b'200 OK',await self.http('/auth/logout',method='POST',data={},extra_headers=authorized))
        self.assertIsNone(self.store.session(token))
        self.assertIn(b'404',await self.http('/auth/google/start'))
        self.assertIn(b'404',await self.http('/auth/google/callback?code=anything'))
        with open(self.store.path,'rb') as f:self.assertNotIn(password.encode(),f.read())

    async def test_login_csrf_wrong_password_and_rate_limit(self):
        self.auth.set_encoded('owner@example.org',self.auth.encode('correct-test-password-123'))
        headers=await self.login_headers()
        data={'email':'owner@example.org','password':'wrong-password'}
        self.assertIn(b'403',await self.http('/auth/password/login',method='POST',data=data))
        self.assertIn(b'403',await self.http('/auth/password/login',method='POST',data=data,extra_headers={**headers,'Origin':'https://evil.example'}))
        self.assertIn(b'401',await self.http('/auth/password/login',method='POST',data=data,extra_headers=headers))
        for _ in range(20):self.auth.attempts.append(time.monotonic())
        self.assertIn(b'503',await self.http('/auth/password/login',method='POST',data=data,extra_headers=headers))
        self.assertFalse(self.auth.verify('wrong-password',self.auth.encode('correct-test-password-123')))
        with self.assertRaises(ValueError):self.auth.encode('short')

    async def test_admin_management_owner_only_password_reset_revokes(self):
        owner=self.headers()
        self.assertIn(b'200 OK',await self.http('/api/admin/action',method='POST',extra_headers=owner,
            data={'action':'add-admin','value':'helper@example.org','password':'helper-test-password-123'}))
        helper=self.headers('helper@example.org')
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers=helper,
            data={'action':'add-admin','value':'bad@example.org','password':'helper-test-password-123'}))
        self.assertIn(b'200 OK',await self.http('/api/admin/action',method='POST',extra_headers=owner,
            data={'action':'reset-admin-password','value':'helper@example.org','password':'new-helper-password-123'}))
        self.assertIn(b'401',await self.http('/api/admin/overview',extra_headers=helper))
        self.assertIn(b'200 OK',await self.http('/api/admin/action',method='POST',extra_headers=owner,
            data={'action':'remove-admin','value':'helper@example.org'}))
        with self.store.connect() as db:self.assertIsNone(db.execute('SELECT 1 FROM admin_passwords WHERE email=?',('helper@example.org',)).fetchone())
        with self.assertRaises(Denied):self.store.access('owner@example.org','remove-admin','owner@example.org')

    async def test_guest_api_and_admin_csrf_and_storage(self):
        self.assertIn(b'401',await self.http('/api/admin/overview'))
        h=self.headers()
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',data={'action':'mode','value':'random'},extra_headers={**h,'X-CSRF-Token':'bad'}))
        self.assertEqual(self.app.mode,'choose')
        self.app.mode='random';self.app.save()
        reopened=AdminStore(self.store.path,'different@example.org')
        self.assertEqual(reopened.load_game()['mode'],'random')
        self.assertNotIn('different@example.org',[a['email'] for a in reopened.admins()])
