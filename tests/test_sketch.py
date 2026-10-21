import asyncio
import base64
import json
import unittest
from unittest.mock import patch
import games
from games.sketch import Sketch,clean_event,normalize,MAX_SEGMENTS,DRAW_MS,REVEAL_MS
import test_server as base
from game_sessions import GameSessions


class SketchEngineTests(unittest.TestCase):
    def event(self,g,p,op,**extra):
        g.handle_event(p,{'op':op,'turn':g.turn,'seq':g.ack[p]+1,**extra})

    def test_player_limits_private_word_and_hidden_view(self):
        for n in (2,3,9):
            with self.assertRaises(ValueError):games.create('sketch',n)
        for n in (4,8):
            g=games.create('sketch',n)
            self.assertEqual(g.min_players,4)
            for p in range(1,n+1):self.assertEqual(g.snapshot(p)['word'],g.word if p==g.drawer else None)
            with self.assertRaises(ValueError):g.snapshot(0)

    def test_drawing_is_authoritative_bounded_and_wrong_roles_are_ignored(self):
        g=Sketch(4);drawer=g.drawer;other=next(p for p in g.alive if p!=drawer);segment=[2,3,20,30,3,4]
        self.event(g,other,'draw',segments=[segment]);self.assertEqual(g.encoded,'')
        self.event(g,drawer,'draw',segments=[segment]);self.assertEqual(list(base64.b64decode(g.encoded)),[2,3,20,30,27])
        revision=g.revision
        g.handle_event(drawer,{'op':'clear','turn':g.turn,'seq':g.ack[drawer]});self.assertEqual(g.revision,revision)
        while len(g.ink)//5<MAX_SEGMENTS:
            g.clock+=150;self.event(g,drawer,'draw',segments=[segment]*min(8,MAX_SEGMENTS-len(g.ink)//5))
        self.assertTrue(g.snapshot(drawer)['limit'])
        self.event(g,drawer,'draw',segments=[segment]);self.assertEqual(len(g.ink),MAX_SEGMENTS*5)
        self.event(g,drawer,'clear');self.assertEqual(g.encoded,'');self.assertFalse(g.snapshot(drawer)['limit'])

    def test_validation_guesses_cooldown_no_spoilers_and_duplicate_scoring(self):
        g=Sketch(4);g.word='Schlüssel';p=next(p for p in g.alive if p!=g.drawer)
        self.assertEqual(normalize('SCHLÜSSEL!'),normalize('Schluessel'))
        self.event(g,p,'guess',text='Es ist ein Schlüssel');self.assertFalse(g.chat)
        g.clock+=1000;self.event(g,p,'guess',text='<img src=x>');self.assertEqual(g.chat[-1]['text'],'<img src=x>')
        self.event(g,p,'guess',text='Schlüssel');self.assertNotIn(p,g.guessed)
        g.clock+=1000;self.event(g,p,'guess',text='Schluessel!');self.assertIn(p,g.guessed)
        points=dict(g.scores);self.event(g,p,'guess',text='Schlüssel');self.assertEqual(g.scores,points)
        self.assertNotIn('Schlüssel',json.dumps(g.chat,ensure_ascii=False))
        self.assertEqual(g.scores[g.drawer],50)
        for value in (None,{}, {'op':'guess','turn':True,'seq':1,'text':'x'}, {'op':'guess','turn':1,'seq':1,'text':'x'*41}, {'op':'draw','turn':1,'seq':1,'segments':[[0,0,999,0,0,2]]}):self.assertIsNone(clean_event(value))

    def test_round_timer_reveal_rotation_everyone_once_and_final_score(self):
        g=Sketch(4);seen=[];words=[]
        while g.result is None:
            seen.append(g.drawer);words.append(g.word)
            for p in g.alive-{g.drawer}:self.event(g,p,'guess',text=g.word)
            self.assertEqual(g.phase,'reveal')
            self.assertTrue(all(g.snapshot(p)['word']==g.word for p in g.alive))
            while g.phase=='reveal':g.tick()
        self.assertEqual(len(set(seen)),4);self.assertEqual(len(set(words)),4)
        self.assertEqual(g.result,'draw')
        timed=Sketch(4)
        for _ in range((DRAW_MS+149)//150):timed.tick()
        self.assertEqual(timed.phase,'reveal')

    def test_departures_remove_future_drawers_and_end_below_four(self):
        g=Sketch(5);drawer=g.drawer;g.remove_player(drawer)
        self.assertEqual(g.phase,'reveal');self.assertIsNone(g.result)
        for _ in range((REVEAL_MS+149)//150):g.tick()
        self.assertNotEqual(g.drawer,drawer)
        g.remove_player(next(iter(g.alive)));self.assertEqual(g.result,'draw')


class SketchServerTests(unittest.IsolatedAsyncioTestCase):
    websocket=base.ServerTests.websocket
    until=base.ServerTests.until
    receive=base.ServerTests.receive
    send=base.ServerTests.send
    http=base.ServerTests.http
    asyncTearDown=base.ServerTests.asyncTearDown

    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.hub=GameSessions(self.app);self.app.session_hub=self.hub
        self.room=self.hub.get(self.hub.create('Sketch')['id'])

    async def join(self,n):
        r,w,_=await self.websocket();await self.until(r,'welcome')
        await self.send(w,{'t':'login','code':self.room.login_code,'nick':'Sketch'+str(n)})
        await self.until(r,'nick_ok');await self.until(r,'lobby')
        return r,w,self.room.players['sketch'+str(n)]

    async def group(self,n=4):return [await self.join(i) for i in range(n)]

    async def test_challenge_never_starts_under_four_and_explicit_start_is_required(self):
        peers=await self.group();host=peers[0][2]
        for r,w,p in peers[1:]:
            await self.room._challenge(host,{'target':p.pid,'game':'sketch'})
            await self.room._accept(p,{'from':host.pid})
            self.assertFalse(self.room.matches)
        with self.assertRaises(ValueError):self.room.start_match('sketch',[p for r,w,p in peers[:3]])
        await self.room._maybe_start(host.out_challenge,force=True)
        for r,w,p in peers:await self.until(r,'match_start')
        self.assertEqual(len(self.room.matches),1)
        self.assertEqual(next(iter(self.room.matches.values())).gid,'sketch')

    async def test_worker_private_words_drawing_guess_pause_and_wrong_match(self):
        peers=await self.group();m=self.room.start_match('sketch',[p for r,w,p in peers])
        states=[]
        for r,w,p in peers:states.append((await self.until(r,'state'))['s'])
        drawer=states[0]['drawer'];self.assertTrue(states[drawer-1]['word'])
        self.assertTrue(all(s['word'] is None for i,s in enumerate(states,1) if i!=drawer))
        word=states[drawer-1]['word'];artist=peers[drawer-1];other=next(x for i,x in enumerate(peers,1) if i!=drawer)
        event={'t':'sketch','mid':m.id,'turn':1,'seq':1,'op':'draw','segments':[[1,1,80,70,0,2]]}
        await self.send(other[1],event);await asyncio.sleep(.2)
        self.assertFalse(m.last_frame['views'][str(drawer)]['drawing'])
        await self.send(artist[1],{**event,'mid':m.id+999});await asyncio.sleep(.2)
        self.assertFalse(m.last_frame['views'][str(drawer)]['drawing'])
        await self.send(artist[1],event)
        for _ in range(100):
            if m.last_frame['views'][str(drawer)]['drawing']:break
            await asyncio.sleep(.02)
        self.assertTrue(m.last_frame['views'][str(drawer)]['drawing'])
        await self.send(other[1],{'t':'sketch','mid':m.id,'turn':1,'seq':2,'op':'guess','text':word})
        for _ in range(100):
            if other[2].role in m.last_frame['views'][str(drawer)]['guessed']:break
            await asyncio.sleep(.02)
        self.assertIn(other[2].role,m.last_frame['views'][str(drawer)]['guessed'])
        m.paused=True;await asyncio.sleep(.2);before=m.last_frame['views'][str(drawer)]['drawing']
        await self.send(artist[1],{**event,'seq':2,'op':'clear'});await asyncio.sleep(.2)
        self.assertEqual(m.last_frame['views'][str(drawer)]['drawing'],before)
        with self.assertRaises(ValueError):self.room.projector.select('match:'+str(m.id))
        with self.assertRaises(ValueError):await self.room.control.action({'action':'spectators','value':m.id})

    async def test_below_four_cancels_without_awarding_remaining_players(self):
        peers=await self.group();m=self.room.start_match('sketch',[p for r,w,p in peers]);await self.until(peers[0][0],'state')
        before=[p.credits for r,w,p in peers[1:]]
        await m.abort(peers[0][2]);self.assertTrue(m.finished);self.assertEqual(m.end_reason,'not_enough_players')
        self.assertEqual(before,[p.credits for r,w,p in peers[1:]])
        self.assertFalse(self.room.flow.offers)

    async def test_default_registry_upgrade_respects_explicit_game_disabling(self):
        state=self.room._state_dict();old=[g for g in games.GAMES if g!='sketch']
        state.pop('registry');state['rules']={**state['rules'],'enabled':old}
        self.room._apply_state(state);self.assertIn('sketch',self.room.rules['enabled'])
        state=self.room._state_dict();state['rules']={**state['rules'],'enabled':old}
        self.room._apply_state(state);self.assertNotIn('sketch',self.room.rules['enabled'])
        state.pop('registry');state['rules']={**state['rules'],'enabled':['pong']}
        self.room._apply_state(state);self.assertEqual(self.room.rules['enabled'],['pong'])

    async def test_random_game_selection_filters_minimum_players(self):
        peers=await self.group(2);self.room.mode='random';self.room.rules['enabled']=['sketch']
        await self.room._challenge(peers[0][2],{'target':peers[1][2].pid})
        await self.room._accept(peers[1][2],{'from':peers[0][2].pid})
        self.assertFalse(self.room.matches)

    async def test_eight_player_worker_views_and_real_time_clock_ignore_game_speed(self):
        players=[self.room._add_player('Eight'+str(i)) for i in range(8)]
        self.room.rules['speed']=3;m=self.room.start_match('sketch',players)
        for _ in range(100):
            if m.last_frame:break
            await asyncio.sleep(.02)
        views=m.last_frame['views'];self.assertEqual(set(views),set(map(str,range(1,9))))
        self.assertEqual(sum(v['word'] is not None for v in views.values()),1)
        await asyncio.sleep(1.1)
        self.assertGreaterEqual(m.last_frame['views']['1']['seconds'],58)
        self.assertLess(len(json.dumps(m.last_frame)),65536)
