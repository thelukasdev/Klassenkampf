import json
import os
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch
import test_server as base
from game_sessions import GameSessions


class PlayerAccountTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app);self.app.session_hub=self.hub;self.auth=self.app.web_admin.player_auth
        self.env=patch.dict(os.environ,{'SMTP_HOST':'mail.test','SMTP_USER':'sender@example.org','SMTP_PASSWORD':'test-only','SMTP_FROM':'sender@example.org'});self.env.start()
        self.mail=patch.object(self.auth,'send');self.sender=self.mail.start()
        with self.auth.store.connect() as db:db.execute("INSERT INTO admins VALUES('owner@example.org',NULL,'owner',0)")
    async def asyncTearDown(self):
        self.mail.stop();self.env.stop();await base.ServerTests.asyncTearDown(self)
    def body(self,response):return json.loads(response.split(b'\r\n\r\n',1)[1])
    def cookie(self,response,name):
        cookies=SimpleCookie()
        for line in response.split(b'\r\n\r\n',1)[0].decode().split('\r\n'):
            if line.startswith('Set-Cookie: '):cookies.load(line[12:])
        return cookies[name].value
    async def preauth(self):
        response=await self.http('/auth/player/csrf');self.csrf=self.body(response)['csrf']
        return {'Origin':'https://games.example.org','Content-Type':'application/json','X-CSRF-Token':self.csrf,
                'Cookie':self.auth.CSRF+'='+self.cookie(response,self.auth.CSRF),'X-Forwarded-For':'192.0.2.1'}
    async def signup(self,email='owner@example.org'):
        headers=await self.preauth();response=await self.http('/auth/player/register',method='POST',extra_headers=headers,data={'email':email,'password':'test-player-password-123'})
        self.assertIn(b'200',response);code=self.sender.call_args.args[1]
        headers['Cookie']+='; '+self.auth.PENDING+'='+self.cookie(response,self.auth.PENDING)
        response=await self.http('/auth/player/verify',method='POST',extra_headers=headers,data={'code':code})
        self.assertIn(b'200',response);token=self.cookie(response,self.auth.COOKIE);session=self.auth.store.session(token)
        return {'Origin':'https://games.example.org','Content-Type':'application/json','X-CSRF-Token':session['csrf'],'Cookie':self.auth.COOKIE+'='+token},token,headers,code
    async def test_signup_requires_email_code_and_is_separate_from_admin(self):
        h,token,pre,code=await self.signup()
        me=self.body(await self.http('/api/player/me',extra_headers=h))['user'];self.assertEqual(me['role'],'host');self.assertEqual(me['display_email'],'owner@example.org')
        with self.auth.store.connect() as db:self.assertEqual(db.execute("SELECT role FROM admins WHERE email='owner@example.org'").fetchone()[0],'owner')
        forged={**h,'Cookie':self.app.web_admin.COOKIE+'='+token}
        self.assertIn(b'401',await self.http('/api/admin/overview',extra_headers=forged))
        self.assertIn(b'400',await self.http('/auth/player/verify',method='POST',extra_headers=pre,data={'code':code}))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'role','value':'player:owner@example.org','role':'admin'}))
    async def test_owned_session_limit_and_minimal_permissions(self):
        h,*_=await self.signup();private=self.hub.create('ADMIN PRIVATE')
        response=await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'One','mode':'random'})
        self.assertIn(b'200',response);rid=self.body(response)['result']['id']
        self.assertEqual(self.hub.get(rid).mode,'choose')
        self.assertIn(b'400',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Two'}))
        overview=self.body(await self.http('/api/player/overview',extra_headers=h));self.assertEqual(overview['session']['id'],rid)
        self.assertEqual(set(overview),{'session'})
        self.assertNotIn('ADMIN PRIVATE',json.dumps(overview))
        for path in ('/api/player/replay','/api/player/replay-chunk'):
            self.assertIn(b'403',await self.http(path+'?session='+rid,extra_headers=h))
        self.assertIn(b'200',await self.http('/api/player/join?session='+rid,extra_headers=h))
        self.assertIn(b'403',await self.http('/api/player/join?session='+private['id'],extra_headers=h))
        for action in ('rules','ban','kick','save','load','mode','spectators','reset-credits','remove-player','move-player'):
            self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':action,'session':rid}))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'end-session','session':private['id']}))
        self.assertIn(b'200',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'end-session','session':rid}))
        self.assertIn(b'200',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Replacement'}))

    async def test_wrong_code_attempt_limit_csrf_and_no_account_before_verify(self):
        h=await self.preauth();data={'email':'new@example.org','password':'test-player-password-123'}
        self.assertIn(b'403',await self.http('/auth/player/register',method='POST',extra_headers={**h,'Origin':'https://evil.test'},data=data))
        r=await self.http('/auth/player/register',method='POST',extra_headers=h,data=data)
        self.assertIn(b'200',r);pending=self.cookie(r,self.auth.PENDING);code=self.sender.call_args.args[1];h['Cookie']+='; '+self.auth.PENDING+'='+pending
        with self.auth.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM player_accounts').fetchone()[0],0)
        wrong='000000' if code!='000000' else '111111'
        for _ in range(5):self.assertIn(b'400',await self.http('/auth/player/verify',method='POST',extra_headers=h,data={'code':wrong}))
        self.assertIn(b'400',await self.http('/auth/player/verify',method='POST',extra_headers=h,data={'code':code}))
    async def test_each_login_needs_email_and_logout_revokes_player_cookie(self):
        h,token,*_=await self.signup();self.assertIn(b'200',await self.http('/auth/player/logout',method='POST',extra_headers=h,data={}))
        self.assertIsNone(self.auth.store.session(token));pre=await self.preauth()
        response=await self.http('/auth/player/login',method='POST',extra_headers=pre,data={'email':'owner@example.org','password':'wrong'})
        self.assertIn(b'401',response)
        response=await self.http('/auth/player/login',method='POST',extra_headers=pre,data={'email':'owner@example.org','password':'test-player-password-123'})
        self.assertIn(b'200',response);self.assertNotIn((self.auth.COOKIE+'=').encode(),response)
        self.assertIn(b'401',await self.http('/api/player/overview'))
    async def test_delivery_failure_does_not_create_account_or_pending_session(self):
        h=await self.preauth();self.sender.side_effect=OSError('mail service unavailable')
        r=await self.http('/auth/player/register',method='POST',extra_headers=h,data={'email':'new@example.org','password':'test-player-password-123'})
        self.assertIn(b'400',r)
        with self.auth.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM player_codes').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM player_accounts').fetchone()[0],0)

    async def test_reset_revokes_player_sessions_and_pending_codes_only(self):
        from password_auth import PasswordAuth
        h,old,_,_=await self.signup()
        second=self.auth.store.new_session('player:owner@example.org')
        admin=self.auth.store.new_session('owner@example.org')
        pending=await self.auth.challenge('owner@example.org')
        with patch.object(self.auth,'send_reset') as mail:
            token=await self.auth.request_reset('owner@example.org');code=mail.call_args.args[1]
        with self.assertRaises(ValueError):self.auth.verify(token,code)
        with self.assertRaises(ValueError):await self.auth.reset_password(pending,code,'replacement-password-123')
        self.assertIsNotNone(self.auth.store.session(old))
        await self.auth.reset_password(token,code,'replacement-password-123')
        self.assertIsNone(self.auth.store.session(old));self.assertIsNone(self.auth.store.session(second))
        self.assertIsNotNone(self.auth.store.session(admin))
        with self.auth.store.connect() as db:
            encoded=db.execute('SELECT hash FROM player_accounts').fetchone()[0]
            self.assertEqual(db.execute('SELECT count(*) FROM player_codes').fetchone()[0],0)
        self.assertTrue(PasswordAuth.verify('replacement-password-123',encoded))
        self.assertFalse(PasswordAuth.verify('test-player-password-123',encoded))
        with self.assertRaises(ValueError):await self.auth.reset_password(token,code,'another-password-123')

    async def test_reset_attempts_expiry_and_generic_request(self):
        await self.signup();h=await self.preauth()
        with patch.object(self.auth,'send_reset') as mail:
            r=await self.http('/auth/player/reset-request',method='POST',extra_headers=h,data={'email':'missing@example.org'})
            self.assertIn(b'200',r);mail.assert_not_called();missing=self.body(r)
            r=await self.http('/auth/player/reset-request',method='POST',extra_headers=h,data={'email':'owner@example.org'})
            self.assertEqual(missing,self.body(r));token=self.cookie(r,self.auth.RESET);code=mail.call_args.args[1]
        h['Cookie']+='; '+self.auth.RESET+'='+token
        self.assertIn(b'400',await self.http('/auth/player/reset-confirm',method='POST',extra_headers=h,data={'code':code,'password':'short'}))
        wrong='000000' if code!='000000' else '111111'
        for _ in range(5):
            with self.assertRaises(ValueError):await self.auth.reset_password(token,wrong,'replacement-password-123')
        with self.assertRaises(ValueError):await self.auth.reset_password(token,code,'replacement-password-123')
        with patch.object(self.auth,'send_reset') as mail:
            token=await self.auth.request_reset('owner@example.org');code=mail.call_args.args[1]
        with self.auth.store.connect() as db:db.execute('UPDATE player_resets SET expires=0')
        with self.assertRaises(ValueError):await self.auth.reset_password(token,code,'replacement-password-123')

    async def test_reset_http_success_and_csrf(self):
        await self.signup();h=await self.preauth()
        self.assertIn(b'403',await self.http('/auth/player/reset-request',method='POST',extra_headers={**h,'Origin':'https://evil.test'},data={'email':'owner@example.org'}))
        with patch.object(self.auth,'send_reset') as mail:
            r=await self.http('/auth/player/reset-request',method='POST',extra_headers=h,data={'email':'owner@example.org'})
            code=mail.call_args.args[1]
        h['Cookie']+='; '+self.auth.RESET+'='+self.cookie(r,self.auth.RESET)
        r=await self.http('/auth/player/reset-confirm',method='POST',extra_headers=h,data={'code':code,'password':'replacement-password-123'})
        self.assertIn(b'200',r);self.assertEqual(self.cookie(r,self.auth.COOKIE),'')

    def admin_headers(self,role='owner'):
        email='owner@example.org' if role=='owner' else role+'@example.org'
        with self.auth.store.connect() as db:db.execute('INSERT OR IGNORE INTO admins VALUES(?,NULL,?,0)',(email,role))
        token=self.auth.store.new_session(email);session=self.auth.store.session(token)
        return {'Origin':'https://games.example.org','Content-Type':'application/json','X-CSRF-Token':session['csrf'],'Cookie':self.app.web_admin.COOKIE+'='+token},token

    async def test_admin_delete_account_revokes_access_closes_own_rooms_preserves_admin(self):
        h,token,*_=await self.signup();owner,owner_token=self.admin_headers()
        room=self.hub.create('Host room');unrelated=self.hub.create('Admin room')
        with self.auth.store.connect() as db:db.execute('INSERT INTO session_access VALUES(?,?)',('player:owner@example.org',room['id']))
        self.hub.hosts.attach(room['id'],'player:owner@example.org')
        pending=await self.auth.challenge('owner@example.org')
        with patch.object(self.auth,'send_reset'):reset=await self.auth.request_reset('owner@example.org')
        r=await self.http('/api/admin/action',method='POST',extra_headers=owner,data={'action':'delete-player-account','value':'owner@example.org'})
        self.assertIn(b'200',r);self.assertIsNone(self.auth.store.session(token));self.assertIsNotNone(self.auth.store.session(owner_token))
        self.assertFalse(self.hub.get(room['id']).room_active);self.assertTrue(self.hub.get(unrelated['id']).room_active)
        with self.auth.store.connect() as db:
            for table in ('player_accounts','player_codes','player_resets','player_permissions','host_rooms','session_access'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM admins WHERE email='owner@example.org' AND role='owner'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='delete-player-account'").fetchone()[0],1)
        self.assertIn(b'401',await self.http('/api/player/overview',extra_headers=h))

    async def test_account_listing_permissions_search_and_pagination(self):
        h,*_=await self.signup();owner,_=self.admin_headers();admin,_=self.admin_headers('admin');guide,_=self.admin_headers('guide')
        with self.auth.store.connect() as db:
            for n in range(30):db.execute('INSERT INTO player_accounts VALUES(?,?,0)',(f'user{n:02}@example.org','private-password-hash'))
        self.assertIn(b'401',await self.http('/api/admin/accounts'))
        for headers,path in ((guide,'/api/admin/accounts'),(h,'/api/player/accounts')):
            self.assertIn(b'403',await self.http(path,extra_headers=headers))
        first=self.body(await self.http('/api/admin/accounts?q=user',extra_headers=admin));self.assertEqual(len(first['accounts']),25)
        second=self.body(await self.http('/api/admin/accounts?q=user&after='+first['next'],extra_headers=owner))
        self.assertEqual(len(second['accounts']),5);self.assertIsNone(second['next'])
        self.assertNotIn('private-password-hash',json.dumps(first))
        for headers,path in ((guide,'/api/admin/action'),(h,'/api/player/action')):
            self.assertIn(b'403',await self.http(path,method='POST',extra_headers=headers,data={'action':'delete-player-account','value':'owner@example.org'}))
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers={**owner,'Origin':'https://evil.test'},data={'action':'delete-player-account','value':'owner@example.org'}))

    async def test_admin_revoke_keeps_account_and_room(self):
        h,token,*_=await self.signup();admin,_=self.admin_headers('admin');room=self.hub.create('Retained')
        with self.auth.store.connect() as db:db.execute('INSERT INTO session_access VALUES(?,?)',('player:owner@example.org',room['id']))
        self.hub.hosts.attach(room['id'],'player:owner@example.org')
        await self.auth.challenge('owner@example.org')
        r=await self.http('/api/admin/action',method='POST',extra_headers=admin,data={'action':'revoke-player-logins','value':'owner@example.org'})
        self.assertIn(b'200',r);self.assertIsNone(self.auth.store.session(token));self.assertTrue(self.hub.get(room['id']).room_active)
        with self.auth.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM player_accounts').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM player_codes').fetchone()[0],0)

    async def test_inflight_old_password_login_cannot_issue_code_after_reset(self):
        import asyncio,threading
        from password_auth import PasswordAuth
        await self.signup();h=await self.preauth();started=threading.Event();release=threading.Event();task=None
        def verify(*args):started.set();release.wait(5);return True
        try:
            with patch.object(PasswordAuth,'verify',side_effect=verify):
                task=asyncio.create_task(self.http('/auth/player/login',method='POST',extra_headers=h,data={'email':'owner@example.org','password':'test-player-password-123'}))
                self.assertTrue(await asyncio.to_thread(started.wait,3))
                with self.auth.store.connect() as db:db.execute("UPDATE player_accounts SET hash='changed-by-reset'")
                self.sender.reset_mock();release.set();r=await task
                self.assertIn(b'401',r);self.sender.assert_not_called()
        finally:
            release.set()
            if task and not task.done():await task

    async def grant(self,**rights):
        from player_permissions import DEFAULTS
        owner,_=self.admin_headers()
        r=await self.http('/api/admin/action',method='POST',extra_headers=owner,data={'action':'player-permissions','value':'owner@example.org','permissions':{**DEFAULTS,**rights}})
        self.assertIn(b'200',r)

    async def test_delegated_rights_allow_only_own_rooms_and_custom_session_limit(self):
        h,*_=await self.signup();private=self.hub.create('Private admin room')
        await self.grant(max_sessions=2,moderate_players=True,manage_games=True,manage_saves=True,view_results=True)
        ids=[]
        for name in ('One','Two'):
            r=await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':name,'mode':'random'})
            self.assertIn(b'200',r);ids.append(self.body(r)['result']['id'])
        self.assertEqual(self.hub.get(ids[0]).mode,'random')
        self.assertIn(b'400',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Third'}))
        p=self.hub.get(ids[0])._add_player('Participant')
        for data in ({'action':'ban','value':p.nick.lower()},{'action':'unban','value':p.nick.lower()},{'action':'rules','rules':{'speed':2}},{'action':'save','value':'owned-save'}):
            self.assertIn(b'200',await self.http('/api/player/action',method='POST',extra_headers=h,data={**data,'session':ids[0]}))
        overview=self.body(await self.http('/api/player/overview?manage=1&session='+ids[0],extra_headers=h))
        self.assertEqual({r['id'] for r in overview['sessions']},set(ids));self.assertNotIn(private['id'],json.dumps(overview))
        for action in ('player-permissions','add-admin','remove-admin','role','assign-session','delete-player-account'):
            self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':action,'value':'owner@example.org'}))
        self.assertNotIn('memory',overview['server']);self.assertEqual(overview['admins'],[]);self.assertEqual(overview['audit'],[])
        self.assertIn(b'403',await self.http('/api/player/overview?manage=1&session='+private['id'],extra_headers=h))
        for action in ('rules','ban','save','end-session'):
            self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':action,'session':private['id'],'value':'Participant'}))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'move-player','session':ids[0],'target':private['id'],'value':p.nick.lower()}))

    async def test_player_permission_grants_are_strict_and_revocation_is_immediate(self):
        from player_permissions import DEFAULTS
        h,*_=await self.signup();owner,_=self.admin_headers();guide,_=self.admin_headers('guide')
        data={'action':'player-permissions','value':'owner@example.org','permissions':{**DEFAULTS,'manage_games':True}}
        self.assertIn(b'403',await self.http('/api/admin/action',method='POST',extra_headers=guide,data=data))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data=data))
        for policy in ({**DEFAULTS,'role':'admin'},{**DEFAULTS,'max_sessions':True},{**DEFAULTS,'max_sessions':17},{**DEFAULTS,'keep_empty':1},{}):
            self.assertIn(b'400',await self.http('/api/admin/action',method='POST',extra_headers=owner,data={**data,'permissions':policy}))
        await self.grant(manage_games=True)
        r=await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Own'})
        rid=self.body(r)['result']['id']
        self.assertIn(b'200',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'rules','session':rid,'rules':{'speed':2}}))
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'save','session':rid,'value':'not-allowed'}))
        self.assertIn(b'403',await self.http('/api/player/accounts',extra_headers=h))
        await self.grant()
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'rules','session':rid,'rules':{'speed':1}}))
        self.assertIn(b'403',await self.http('/api/player/overview?manage=1',extra_headers=h))
        self.assertFalse(self.body(await self.http('/api/player/me',extra_headers=h))['user']['permissions']['manage_games'])

    async def test_replay_permission_is_independent_and_foreign_recordings_stay_private(self):
        h,*_=await self.signup();private=self.hub.create('Secret')
        r=await self.http('/api/player/action',method='POST',extra_headers=h,data={'action':'create-session','value':'Own'})
        rid=self.body(r)['result']['id'];self.hub.get(rid)._add_player('Hidden without profile rights')
        await self.grant(view_replays=True)
        def metadata(room,record=None):return {'id':'test-record'} if record else [{'id':'test-record'}]
        with patch.object(self.app.replays,'metadata',side_effect=metadata):
            overview=self.body(await self.http('/api/player/overview?manage=1&session='+rid,extra_headers=h))
            self.assertEqual(overview['status']['players'],[]);self.assertEqual(overview['history'],[]);self.assertEqual(overview['saves'],[])
            self.assertEqual(overview['replays'],[{'id':'test-record'}])
            self.assertIn(b'200',await self.http('/api/player/replay?session='+rid+'&id=test-record',extra_headers=h))
            self.assertIn(b'403',await self.http('/api/player/replay?session='+private['id']+'&id=test-record',extra_headers=h))
        await self.grant(view_results=True)
        self.assertIn(b'403',await self.http('/api/player/replay?session='+rid+'&id=test-record',extra_headers=h))
        overview=self.body(await self.http('/api/player/overview?manage=1&session='+rid,extra_headers=h))
        self.assertEqual(len(overview['status']['players']),1);self.assertEqual(overview['replays'],[])

    async def test_account_password_change_requires_current_password_and_revokes_all_player_auth(self):
        from password_auth import PasswordAuth
        h,token,*_=await self.signup();admin,admin_token=self.admin_headers()
        second=self.auth.store.new_session('player:owner@example.org')
        await self.auth.challenge('owner@example.org')
        with patch.object(self.auth,'send_reset'):await self.auth.request_reset('owner@example.org')
        data={'current_password':'test-player-password-123','password':'replacement-account-password-456'}
        self.assertIn(b'403',await self.http('/auth/player/change-password',method='POST',data=data))
        self.assertIn(b'403',await self.http('/auth/player/change-password',method='POST',extra_headers={**h,'Origin':'https://evil.test'},data=data))
        self.assertIn(b'400',await self.http('/auth/player/change-password',method='POST',extra_headers=h,data={**data,'current_password':'wrong'}))
        self.assertIsNotNone(self.auth.store.session(token))
        self.assertIn(b'400',await self.http('/auth/player/change-password',method='POST',extra_headers=h,data={**data,'password':'short'}))
        with patch.dict(os.environ,{'SMTP_PASSWORD':''}):
            r=await self.http('/auth/player/change-password',method='POST',extra_headers=h,data=data)
        self.assertIn(b'200',r);self.assertEqual(self.cookie(r,self.auth.COOKIE),'')
        self.assertIsNone(self.auth.store.session(token));self.assertIsNone(self.auth.store.session(second));self.assertIsNotNone(self.auth.store.session(admin_token))
        with self.auth.store.connect() as db:
            encoded=db.execute('SELECT hash FROM player_accounts').fetchone()[0]
            self.assertTrue(PasswordAuth.verify(data['password'],encoded));self.assertFalse(PasswordAuth.verify(data['current_password'],encoded))
            self.assertEqual(db.execute('SELECT count(*) FROM player_codes').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM player_resets').fetchone()[0],0)

    async def test_manual_reports_private_access_resolution_and_input_protection(self):
        r=await self.http('/auth/report/csrf');csrf=self.body(r)['csrf'];report=self.app.web_admin.reports
        headers={'Origin':'https://games.example.org','Content-Type':'application/json','X-CSRF-Token':csrf,'Cookie':report.COOKIE+'='+self.cookie(r,report.COOKIE),'X-Forwarded-For':'192.0.2.5'}
        data={'page':'/','description':'Die Spielrunde bleibt beim Start hängen.'}
        self.assertIn(b'403',await self.http('/auth/report/submit',method='POST',extra_headers={**headers,'Origin':'https://evil.test'},data=data))
        self.assertIn(b'400',await self.http('/auth/report/submit',method='POST',extra_headers=headers,data={**data,'page':'/?code=PRIVATE'}))
        r=await self.http('/auth/report/submit',method='POST',extra_headers=headers,data=data)
        self.assertIn(b'200',r);reference=self.body(r)['reference'];self.assertRegex(reference,r'^KK-[A-F0-9]{12}$')
        owner,_=self.admin_headers();guide,_=self.admin_headers('guide');player,*_=await self.signup()
        self.assertIn(b'401',await self.http('/api/admin/reports'))
        self.assertIn(b'403',await self.http('/api/admin/reports',extra_headers=guide))
        self.assertIn(b'403',await self.http('/api/player/reports',extra_headers=player))
        rows=self.body(await self.http('/api/admin/reports?q='+reference,extra_headers=owner))['reports']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['description'],data['description'])
        self.assertEqual(set(rows[0]),{'id','reference','created','page','description','resolved'})
        action={'action':'resolve-report','value':reference,'resolved':True}
        self.assertIn(b'403',await self.http('/api/player/action',method='POST',extra_headers=player,data=action))
        self.assertIn(b'200',await self.http('/api/admin/action',method='POST',extra_headers=owner,data=action))
        self.assertEqual(self.body(await self.http('/api/admin/reports',extra_headers=owner))['reports'],[])
        self.assertEqual(self.body(await self.http('/api/admin/reports?state=resolved',extra_headers=owner))['reports'][0]['reference'],reference)
        for _ in range(4):self.assertIn(b'200',await self.http('/auth/report/submit',method='POST',extra_headers=headers,data=data))
        self.assertIn(b'400',await self.http('/auth/report/submit',method='POST',extra_headers=headers,data=data))

    async def test_concurrent_password_changes_cannot_overwrite_new_credentials(self):
        import asyncio
        h,token,*_=await self.signup()
        a,b=await asyncio.gather(*[self.http('/auth/player/change-password',method='POST',extra_headers=h,data={'current_password':'test-player-password-123','password':new}) for new in ('changed-password-one-123','changed-password-two-123')])
        self.assertEqual(sorted([int(r.split(b' ',2)[1]) for r in (a,b)]),[200,403])
        self.assertIsNone(self.auth.store.session(token))

    async def test_report_history_pages_have_no_duplicates(self):
        owner,_=self.admin_headers()
        with self.auth.store.connect() as db:
            for n in range(31):db.execute('INSERT INTO issue_reports(reference,created,page,description) VALUES(?,0,?,?)',(f'KK-TEST{n:08}', '/','Pagination fixture'))
        first=self.body(await self.http('/api/admin/reports?state=all',extra_headers=owner))
        second=self.body(await self.http('/api/admin/reports?state=all&before='+str(first['next']),extra_headers=owner))
        self.assertEqual(len(first['reports']),25);self.assertEqual(len(second['reports']),6)
        self.assertIsNone(second['next']);self.assertEqual(len({r['id'] for r in first['reports']+second['reports']}),31)
