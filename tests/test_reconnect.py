import asyncio
import json
import time
import unittest
import test_server as base
from game_sessions import GameSessions


class ReconnectTests(unittest.IsolatedAsyncioTestCase):
    websocket=base.ServerTests.websocket
    until=base.ServerTests.until
    receive=base.ServerTests.receive
    send=base.ServerTests.send
    asyncTearDown=base.ServerTests.asyncTearDown

    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app);self.app.session_hub=self.hub
        self.room=self.hub.get(self.hub.create('Reconnect')['id'])

    async def login(self,nick,token=None):
        reader,writer,headers=await self.websocket()
        await self.until(reader,'welcome')
        await self.send(writer,{'t':'login','code':self.room.login_code,'nick':nick,'tok':token})
        result=await self.until(reader,'nick_ok')
        return reader,writer,result['tok']

    async def pair(self):
        self.ra,self.wa,self.token=await self.login('Alice')
        self.rb,self.wb,_=await self.login('Bob')
        self.a=self.room.players['alice'];self.b=self.room.players['bob']
        self.match=self.room.start_match('pong',[self.a,self.b])
        await self.until(self.ra,'state');await self.until(self.rb,'state')
        return self.match

    async def drop(self,writer):
        writer.close();await writer.wait_closed()
        for _ in range(100):
            if self.match.disconnected:return
            await asyncio.sleep(.01)
        self.fail('No reconnect deadline')

    async def test_real_worker_pause_reclaim_same_role_and_manual_pause_survives(self):
        m=await self.pair();role=self.a.role;credits=self.a.credits
        await self.drop(self.wa)
        message=await self.until(self.rb,'match_pause')
        self.assertTrue(message['paused']);self.assertEqual(message['waiting'][0]['nick'],'Alice')
        self.assertLessEqual(message['waiting'][0]['seconds'],30)
        await asyncio.sleep(.15);frame=json.dumps(m.last_frame);await asyncio.sleep(.2)
        self.assertEqual(json.dumps(m.last_frame),frame);self.assertFalse(m.finished)
        deadline=m.disconnected[self.a]
        r,w,_=await self.websocket();await self.until(r,'welcome')
        await self.send(w,{'t':'login','code':self.room.login_code,'nick':'Alice','tok':'wrong'})
        await self.until(r,'nick_err');self.assertEqual(m.disconnected[self.a],deadline)
        m.paused=True
        ra,wa,token=await self.login('Alice',self.token)
        resumed=await self.until(ra,'match_start');await self.until(ra,'state')
        self.assertEqual(resumed['role'],role);self.assertEqual(token,self.token);self.assertIs(self.a.match,m)
        self.assertFalse(m.disconnected);self.assertTrue(m.is_paused);self.assertEqual(self.a.credits,credits)
        m.paused=False;await m.pause_notice()
        await asyncio.sleep(.2);self.assertNotEqual(json.dumps(m.last_frame),frame)

    async def test_timeout_awards_once_and_late_return_gets_lobby(self):
        m=await self.pair();await self.drop(self.wa)
        m.disconnected[self.a]=time.monotonic()-1;await m.expire_connections()
        result=await self.until(self.rb,'match_end');self.assertEqual(result['reason'],'opp_disconnected')
        self.assertEqual(self.b.record['pong'][0],1);await m.expire_connections();self.assertEqual(self.b.record['pong'][0],1)
        ra,wa,_=await self.login('Alice',self.token)
        await self.until(ra,'lobby');self.assertIsNone(self.a.match);self.assertNotIn(m.id,self.room.matches)

    async def test_everyone_offline_cancels_without_credits_and_deadline_cannot_extend(self):
        m=await self.pair();before=[p.credits for p in m.players]
        await self.drop(self.wa);deadline=m.disconnected[self.a]
        await self.room._on_disconnect(self.a);self.assertEqual(m.disconnected[self.a],deadline)
        self.wb.close();await self.wb.wait_closed()
        for _ in range(100):
            if self.b in m.disconnected:break
            await asyncio.sleep(.01)
        self.assertIn(self.b,m.disconnected)
        m.disconnected[self.a]=time.monotonic()-1;await m.expire_connections()
        self.assertTrue(m.finished);self.assertEqual(m.end_reason,'connection_lost')
        self.assertEqual(before,[p.credits for p in m.players]);self.assertFalse(m.outcomes);self.assertFalse(m.disconnected)

    async def test_explicit_leave_and_admin_end_do_not_wait_for_grace(self):
        m=await self.pair();await self.send(self.wa,{'t':'leave'})
        result=await self.until(self.rb,'match_end');self.assertEqual(result['reason'],'opp_left');self.assertTrue(m.finished)
        m=self.room.start_match('pong',[self.a,self.b]);self.match=m
        await self.until(self.ra,'match_start');await self.drop(self.wa)
        await self.room.control.cancel_match(m)
        self.assertTrue(m.finished);self.assertFalse(m.disconnected);self.assertIsNone(self.a.match)
