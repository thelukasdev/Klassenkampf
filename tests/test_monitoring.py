import os
import unittest
from unittest.mock import patch
import test_server as base
from game_sessions import GameSessions

class MonitoringTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    asyncSetUp=base.ServerTests.asyncSetUp
    asyncTearDown=base.ServerTests.asyncTearDown

    async def test_metrics_require_secret_and_exclude_identifiers(self):
        self.app.session_hub=GameSessions(self.app)
        before=sum(getattr(r,'room_active',True) for r in self.app.session_hub.rooms.values())
        room=self.app.session_hub.create('PRIVATE-ROOM-NAME')
        r=self.app.session_hub.get(room['id']);r._add_player('PRIVATE-NICK')
        self.app.metrics.observe('/auth/player/login?email=private@example.org',.1)
        with patch.dict(os.environ,{'KLASSENKAMPF_STATUS_TOKEN':'test-private-status-token'}):
            for headers in ({},{'Authorization':'Bearer wrong'}):
                self.assertIn(b'404',await self.http('/internal/metrics',extra_headers=headers))
            headers={'Authorization':'Bearer test-private-status-token'}
            self.assertIn(b'404',await self.http('/internal/metrics',method='POST',extra_headers=headers))
            response=await self.http('/internal/metrics',extra_headers=headers)
        self.assertIn(b'200 OK',response);self.assertIn(b'text/plain; version=0.0.4',response)
        self.assertIn(('kk_sessions_active '+str(before+1)).encode(),response);self.assertIn(b'kk_http_requests_total{kind="auth"} 1',response)
        self.assertIn(b'kk_http_duration_seconds_bucket{le="+Inf"}',response)
        for secret in ('PRIVATE-ROOM-NAME','PRIVATE-NICK','private@example.org',room['code'],room['id'],'test-private-status-token'):
            self.assertNotIn(secret.encode(),response)

    def test_dashboard_url_only_accepts_direct_cloud_https(self):
        from monitoring_metrics import dashboard_url
        for url in ('http://example.grafana.net/','https://evil.example/','https://user:pw@example.grafana.net/','https://example.grafana.net/?token=secret'):
            with patch.dict(os.environ,{'KLASSENKAMPF_MONITORING_URL':url}):self.assertEqual(dashboard_url(),'')
        with patch.dict(os.environ,{'KLASSENKAMPF_MONITORING_URL':'https://example.grafana.net/d/klassenkampf'}):self.assertEqual(dashboard_url(),'https://example.grafana.net/d/klassenkampf')

    async def test_http_observation_has_bounded_labels_and_excludes_scrapes(self):
        await self.http('/healthz')
        for n in range(10):await self.http('/not-found-'+str(n)+'?secret=do-not-record')
        self.assertEqual(set(self.app.metrics.requests),{'health','static'})
        count=self.app.metrics.count
        with patch.dict(os.environ,{'KLASSENKAMPF_STATUS_TOKEN':'test-token'}):
            await self.http('/internal/metrics',extra_headers={'Authorization':'Bearer test-token'})
        self.assertEqual(self.app.metrics.count,count)
        text=self.app.metrics.render().decode();self.assertNotIn('not-found',text);self.assertNotIn('do-not-record',text)

    async def test_dashboard_link_is_admin_only_and_anonymous_me_stays_available(self):
        with patch.dict(os.environ,{'KLASSENKAMPF_MONITORING_URL':'https://example.grafana.net/d/klassenkampf'}):
            response=await self.http('/api/admin/me')
            self.assertIn(b'200 OK',response);self.assertIn(b'"monitoring_url": ""',response)
            web=self.app.web_admin
            for role in ('owner','admin','guide'):
                email=role+'@example.org'
                with web.store.connect() as db:db.execute('INSERT INTO admins VALUES(?,NULL,?,0)',(email,role))
                token=web.store.new_session(email)
                response=await self.http('/api/admin/me',extra_headers={'Cookie':web.COOKIE+'='+token})
                self.assertIn(b'200 OK',response)
                self.assertEqual(b'https://example.grafana.net/d/klassenkampf' in response,role in ('owner','admin'))
