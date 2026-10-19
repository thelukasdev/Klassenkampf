import json
import asyncio
import os
from pathlib import Path
import tempfile
import unittest
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import test_server as base
from game_sessions import GameSessions
from public_status import StatusStore,probe,make_handler


def component(state='operational',cid='platform'):
    return {'id':cid,'label':'Test','kind':'service' if cid=='platform' else 'session','state':state}


class StatusStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'status.sqlite3';self.store=StatusStore(self.path)
        self.start=1700000000
    def tearDown(self):self.tmp.cleanup()
    def seconds(self,data,state):return sum(r['seconds'] for r in data['daily'] if r['state']==state)
    def test_complete_intervals_gaps_and_restart_persistence(self):
        s=self.start;self.store.observe([component()],s);self.store.observe([component()],s+15)
        self.store.observe([component('down')],s+135)
        data=self.store.read(now=s+135)
        self.assertEqual(self.seconds(data,'operational'),30)
        self.assertEqual(self.seconds(data,'unknown'),105)
        self.assertEqual([e['state'] for e in data['events']],['down','unknown','operational'])
        self.store=StatusStore(self.path);self.store.observe([component()],s+150)
        data=self.store.read(now=s+150)
        self.assertEqual(self.seconds(data,'down'),15);self.assertEqual(data['started'],s)
        self.assertEqual(len(data['events']),4)
    def test_utc_midnight_split_and_stale_is_unknown(self):
        start=(self.start//86400+1)*86400-10
        self.store.observe([component()],start);self.store.observe([component()],start+20)
        data=self.store.read(now=start+20)
        self.assertEqual(sorted(r['seconds'] for r in data['daily']),[10,10])
        stale=self.store.read(now=start+120)
        self.assertTrue(stale['stale']);self.assertEqual(stale['components'][0]['state'],'unknown')
        self.assertEqual(self.seconds(stale,'unknown'),85)
        # Reading stale state never changes durable history.
        self.assertEqual(len(stale['events']),1)
    def test_timeline_pagination_has_no_gaps_or_duplicates(self):
        for n in range(70):self.store.observe([component('down' if n%2 else 'operational')],self.start+n*15)
        first=self.store.read(now=self.start+69*15)
        second=self.store.read(before=tuple(map(int,first['next'].split(':'))),now=self.start+69*15)
        events=first['events']+second['events'];self.assertEqual(len(events),70)
        self.assertEqual(len({e['id'] for e in events}),70)
        self.assertEqual([e['time'] for e in events],sorted([e['time'] for e in events],reverse=True))
        self.assertIsNone(second['next'])
    def test_app_outage_keeps_sessions_and_ended_state(self):
        self.store.observe([component(cid='session-one'),component('ended',cid='session-old')],self.start)
        with patch('public_status.urllib.request.urlopen',side_effect=OSError()),patch('public_status.websocket_probe',return_value=False):
            items=probe(self.store,'http://app:8080','secret','https://example.org')
        states={r['id']:r['state'] for r in items}
        self.assertEqual(states['player-login'],'down');self.assertEqual(states['admin-login'],'down')
        self.assertEqual(states['platform'],'down');self.assertEqual(states['session-one'],'down');self.assertEqual(states['session-old'],'ended')

    def test_public_https_failure_degrades_otherwise_healthy_system(self):
        class Response:
            status=200
            def __init__(self,body):self.body=body
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.body
        def open_url(url,**kwargs):
            if isinstance(url,str):
                if url.startswith('https:'):raise OSError('TLS failure')
                return Response(b'ok')
            return Response(b'{"version":1,"database":"operational","sessions":[]}')
        with patch('public_status.urllib.request.urlopen',side_effect=open_url),patch('public_status.websocket_probe',return_value=True):
            items=probe(self.store,'http://app:8080','secret','https://example.org',check_public=True)
        states={r['id']:r['state'] for r in items}
        self.assertEqual(states['http'],'operational');self.assertEqual(states['websocket'],'operational')
        self.assertEqual(states['https'],'down');self.assertEqual(states['platform'],'degraded')

    def test_login_services_probe_readiness_failures_and_record_history(self):
        class Response:
            status=200
            def __init__(self,body):self.body=body
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.body
        ready=True;admin_up=True
        def open_url(url,**kwargs):
            if not isinstance(url,str):return Response(b'{"version":1,"database":"operational","sessions":[]}')
            if url.endswith('/auth/player/csrf'):return Response(json.dumps({'csrf':'x'*32,'ready':ready}).encode())
            if url.endswith('/auth/password/csrf'):
                if not admin_up:raise OSError('login unavailable')
                return Response(b'{"csrf":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}')
            return Response(b'ok')
        with patch('public_status.urllib.request.urlopen',side_effect=open_url),patch('public_status.websocket_probe',return_value=True):
            healthy=probe(self.store,'http://app:8080','secret','https://example.org')
            states={r['id']:r['state'] for r in healthy}
            self.assertEqual(states['player-login'],'operational');self.assertEqual(states['admin-login'],'operational')
            self.assertEqual(states['platform'],'operational');self.store.observe(healthy,self.start)
            ready=False;admin_up=False
            failed=probe(self.store,'http://app:8080','secret','https://example.org')
            states={r['id']:r['state'] for r in failed}
            self.assertEqual(states['player-login'],'degraded');self.assertEqual(states['admin-login'],'down')
            self.assertEqual(states['platform'],'degraded');self.store.observe(failed,self.start+15)
            ready=True;admin_up=True
            self.store.observe(probe(self.store,'http://app:8080','secret','https://example.org'),self.start+30)
        history=self.store.read(component='admin-login',now=self.start+30)
        self.assertEqual([e['state'] for e in history['events']],['operational','down','operational'])
        self.assertTrue(any(r['state']=='down' and r['seconds']==15 for r in history['daily']))


class StatusFeedTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    asyncTearDown=base.ServerTests.asyncTearDown
    async def asyncSetUp(self):await base.ServerTests.asyncSetUp(self)
    async def test_private_feed_authentication_and_public_allowlist(self):
        hub=GameSessions(self.app);self.app.session_hub=hub;room=hub.create('SECRET_CLASS_NAME')
        hub.get(room['id'])._add_player('SECRET_PLAYER')
        with patch.dict(os.environ,{'KLASSENKAMPF_STATUS_TOKEN':'monitor-test-token'}):
            self.assertIn(b'404',await self.http('/internal/status.json'))
            self.assertIn(b'404',await self.http('/internal/status.json',extra_headers={'Authorization':'Bearer bad'}))
            result=await self.http('/internal/status.json',extra_headers={'Authorization':'Bearer monitor-test-token'})
        self.assertIn(b'200',result);data=json.loads(result.split(b'\r\n\r\n',1)[1])
        text=json.dumps(data)
        for private in (room['code'],room['id'],'SECRET_CLASS_NAME','SECRET_PLAYER','token_hash','admin','record'):
            self.assertNotIn(private,text)
        self.assertEqual(data['database'],'operational');self.assertEqual(len(data['sessions']),2)

    async def test_independent_public_http_survives_app_outage(self):
        store=StatusStore(Path(self.tmp.name)/'public.sqlite3')
        static=Path(__file__).resolve().parents[1]/'static'
        public=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store,static))
        thread=threading.Thread(target=public.serve_forever,daemon=True);thread.start()
        target='http://127.0.0.1:'+str(self.port)
        token='monitor-test-token'
        def get(path):
            with urllib.request.urlopen('http://127.0.0.1:'+str(public.server_port)+path,timeout=3) as r:return r.status,r.read()
        try:
            with patch.dict(os.environ,{'KLASSENKAMPF_STATUS_TOKEN':token}):
                items=await asyncio.to_thread(probe,store,target,token,'https://games.example.org')
            store.observe(items)
            self.assertEqual(next(i['state'] for i in items if i['id']=='websocket'),'operational')
            self.assertEqual((await asyncio.to_thread(get,'/status'))[0],200)
            with self.assertRaises(urllib.error.HTTPError) as missing:
                await asyncio.to_thread(get,'/status/fehlt')
            self.assertEqual(missing.exception.code,404)
            self.assertIn(b'Seite nicht gefunden',missing.exception.read())
            self.listener.close();await self.listener.wait_closed()
            items=await asyncio.to_thread(probe,store,target,token,'https://games.example.org');store.observe(items)
            status,body=await asyncio.to_thread(get,'/api/status')
            self.assertEqual(status,200)
            self.assertEqual(next(i['state'] for i in json.loads(body)['components'] if i['id']=='platform'),'down')
            self.assertEqual((await asyncio.to_thread(get,'/status/status.css'))[0],200)
        finally:
            await asyncio.to_thread(public.shutdown);public.server_close();thread.join()
