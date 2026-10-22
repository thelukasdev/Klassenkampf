import json
from pathlib import Path
import unittest
import test_server as base
from external_api import API
from game_sessions import GameSessions

class ExternalAPITests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    asyncTearDown=base.ServerTests.asyncTearDown
    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.key='integration-test-'+'a'*40
        keyfile=Path(self.tmp.name)/'external-api.key';keyfile.write_text(self.key)
        self.app.external_api=API(self.app,keyfile)
    async def test_public_status_games_and_openapi(self):
        for route,field in [('/api/v1/status','status'),('/api/v1/games','games'),('/api/openapi.json','openapi')]:
            r=await self.http(route);self.assertIn(b'200 OK',r);self.assertIn(field.encode(),r)
        spec=json.loads((Path(__file__).parents[1]/'static/openapi.json').read_text(encoding='utf-8'))
        self.assertEqual(len(spec['paths']),4)
        self.assertEqual(spec['paths']['/api/v1/sessions']['get']['security'],[{'bearerAuth':[]}])
    async def test_private_data_requires_dedicated_key(self):
        for h in ({},{'Authorization':'Bearer wrong'},{'Cookie':'__Host-kk_admin=pretend'}):
            self.assertIn(b'401 Unauthorized',await self.http('/api/v1/sessions',extra_headers=h))
        self.assertIn(b'200 OK',await self.http('/api/v1/sessions',extra_headers={'Authorization':'Bearer '+self.key}))
        self.app.external_api.keyfile.unlink()
        self.assertIn(b'503 Service Unavailable',await self.http('/api/v1/results'))
    async def test_no_identifiers_and_aggregate_results(self):
        self.app.session_hub=GameSessions(self.app)
        row=self.app.session_hub.create('PRIVATE ROOM');room=self.app.session_hub.get(row['id'])
        room._add_player('PRIVATE PLAYER');room.history=[{'game':'connect4','players':['PRIVATE PLAYER'],'outcomes':[1,0]}]
        headers={'Authorization':'Bearer '+self.key}
        r=await self.http('/api/v1/sessions',extra_headers=headers)
        for value in (row['id'],row['code'],'PRIVATE ROOM','PRIVATE PLAYER',self.key):self.assertNotIn(value.encode(),r)
        r=await self.http('/api/v1/results',extra_headers=headers)
        self.assertIn(b'"completed_matches": 1',r);self.assertNotIn(b'PRIVATE PLAYER',r)
    async def test_methods_routes_limits_and_retry_after(self):
        headers={'Authorization':'Bearer '+self.key}
        self.assertIn(b'405 Method Not Allowed',await self.http('/api/v1/results',method='POST',extra_headers=headers))
        self.assertIn(b'404 Not Found',await self.http('/api/v1/missing',extra_headers=headers))
        import time
        self.app.external_api.windows['private'].extend([time.monotonic()]*120)
        r=await self.http('/api/v1/results',extra_headers=headers)
        self.assertIn(b'429 Too Many Requests',r);self.assertIn(b'Retry-After: 60',r)
        r=await self.http('/api/v1/status');self.assertIn(b'200 OK',r)
