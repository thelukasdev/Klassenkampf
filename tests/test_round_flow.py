import asyncio
import time
import unittest
from unittest.mock import patch
import test_server as base
from game_sessions import GameSessions


class RoundFlowTests(unittest.IsolatedAsyncioTestCase):
    websocket=base.ServerTests.websocket
    until=base.ServerTests.until
    receive=base.ServerTests.receive
    send=base.ServerTests.send
    asyncTearDown=base.ServerTests.asyncTearDown

    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app);self.app.session_hub=self.hub
        self.room=self.hub.get(self.hub.create('Rounds')['id'])

    async def join(self,nick,room=None):
        room=room or self.room
        reader,writer,_=await self.websocket();await self.until(reader,'welcome')
        await self.send(writer,{'t':'login','code':room.login_code,'nick':nick})
        await self.until(reader,'nick_ok');await self.until(reader,'lobby')
        return reader,writer,room.players[nick.lower()]

    async def finish(self,count=2,gid='pong'):
        peers=[await self.join('Player'+str(i)) for i in range(count)]
        match=self.room.start_match(gid,[p for r,w,p in peers])
        for r,w,p in peers:await self.until(r,'state')
        await match._end_by_result('p1')
        for r,w,p in peers:await self.until(r,'match_end')
        return peers,match,next(iter(self.room.flow.offers.values()))

    async def test_waiting_requires_every_online_player_and_explicit_release(self):
        room=self.hub.get(self.hub.create('Waiting',waiting_room=True)['id'])
        with self.assertRaises(ValueError):self.hub.create('Invalid',waiting_room='yes')
        a=await self.join('Alice',room);b=await self.join('Bob',room)
        with self.assertRaises(ValueError):room.start_match('pong',[a[2],b[2]])
        with self.assertRaises(ValueError):room.flow.release()
        await room.flow.handle(a[2],{'t':'ready','ready':True})
        self.assertFalse(room.flow.summary()['can_release'])
        await room.flow.handle(b[2],{'t':'ready','ready':True})
        self.assertTrue(room.flow.summary()['can_release']);self.assertTrue(room.flow.waiting)
        with self.assertRaises(ValueError):await room.flow.handle(a[2],{'t':'ready','ready':'yes'})
        await room.control.action({'action':'release-waiting-room'})
        self.assertFalse(room.flow.waiting)
        self.assertTrue(room.rules['waiting_released'])
        room.start_match('pong',[a[2],b[2]])
        self.assertEqual(len(room.matches),1)

    async def test_ready_disconnect_resets_and_cannot_release(self):
        self.room.rules['waiting_room']=True
        a=await self.join('Alice');b=await self.join('Bob')
        for _,_,p in (a,b):await self.room.flow.handle(p,{'t':'ready','ready':True})
        await self.room._on_disconnect(b[2])
        self.assertFalse(b[2].ready);self.assertFalse(self.room.flow.summary()['can_release'])

    async def test_rematch_needs_both_same_players_and_consumes_offer_once(self):
        peers,old,offer=await self.finish()
        for r,w,p in peers:self.assertEqual(self.room.flow.view(p)['offer']['kind'],'rematch')
        a,b=[p for r,w,p in peers]
        command={'t':'round_vote','id':offer['id'],'game':'pong'}
        await self.room.flow.handle(a,command);self.assertFalse(self.room.matches)
        await self.room.flow.handle(b,command)
        new=next(iter(self.room.matches.values()))
        self.assertNotEqual(new.id,old.id);self.assertEqual(new.players,[a,b]);self.assertEqual(new.gid,'pong')
        self.assertFalse(self.room.flow.offers)
        with self.assertRaises(ValueError):await self.room.flow.handle(b,command)
        self.assertEqual(len(self.room.matches),1)

    async def test_four_player_vote_majority_only_after_all_four(self):
        peers,old,offer=await self.finish(4,'tron')
        self.assertEqual(offer['kind'],'vote');self.assertEqual(set(offer['choices']),{'tron','bomber','jnb'})
        for index,(r,w,p) in enumerate(peers):
            await self.room.flow.handle(p,{'t':'round_vote','id':offer['id'],'game':'bomber' if index<3 else 'tron'})
            self.assertEqual(len(self.room.matches),int(index==3))
        new=next(iter(self.room.matches.values()))
        self.assertEqual(new.gid,'bomber');self.assertEqual(new.players,old.players)

    async def test_leave_disconnect_expiry_and_foreign_player(self):
        peers,old,offer=await self.finish(4,'tron')
        other=self.hub.get(self.hub.create('Other')['id']);_,_,outsider=await self.join('Foreign',other)
        with self.assertRaises(ValueError):await self.room.flow.handle(outsider,{'t':'round_vote','id':offer['id'],'game':'tron'})
        _,_,challenger=await self.join('Challenger')
        await self.room._challenge(challenger,{'target':peers[0][2].pid,'game':'tron'})
        self.assertIn(offer['id'],self.room.flow.offers)  # An unsolicited invitation cannot cancel another group.
        await self.room.flow.handle(peers[0][2],{'t':'round_leave'})
        self.assertFalse(self.room.flow.offers)
        self.room.flow.completed(old);self.assertTrue(self.room.flow.offers)
        await self.room._on_disconnect(peers[0][2]);self.assertFalse(self.room.flow.offers)
        peers[0][2].conn=peers[1][2].conn
        self.room.flow.completed(old);offer=next(iter(self.room.flow.offers.values()))
        offer['deadline']=time.monotonic()-1
        self.assertTrue(self.room.flow.prune());self.assertFalse(self.room.flow.offers)

    async def test_capacity_failure_can_retry_and_pause_does_not_accept_vote(self):
        peers,old,offer=await self.finish();a,b=[p for r,w,p in peers]
        command={'t':'round_vote','id':offer['id'],'game':'pong'}
        self.room.rules['paused']=True
        with self.assertRaises(ValueError):await self.room.flow.handle(a,command)
        self.assertFalse(offer['votes']);self.room.rules['paused']=False
        await self.room.flow.handle(a,command)
        with patch.object(self.room,'start_match',side_effect=ValueError('capacity')):
            with self.assertRaises(ValueError):await self.room.flow.handle(b,command)
        self.assertNotIn(b.pid,offer['votes'])
        await self.room.flow.handle(b,command);self.assertEqual(len(self.room.matches),1)

    async def test_cancelled_or_incomplete_four_player_match_has_no_offer(self):
        peers=[await self.join('Player'+str(i)) for i in range(4)]
        m=self.room.start_match('tron',[p for r,w,p in peers])
        await self.until(peers[0][0],'state');await self.room.control.cancel_match(m)
        self.assertFalse(self.room.flow.offers)
        m.end_reason='leave';m.left.add(peers[0][2]);self.room.flow.completed(m)
        self.assertFalse(self.room.flow.offers)
        m.end_reason='normal';m.left.clear();m.followup_blocked=True;self.room.flow.completed(m)
        self.assertFalse(self.room.flow.offers)
