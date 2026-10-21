import unittest
import test_player_accounts as accounts
from server import Match
from player_stats import PlayerStats

class Connection:
    alive=True
    account_email=None
    def __init__(self,token=None):self.account_session_token=token
    async def send(self,obj):pass

class PersonalStatsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=accounts.PlayerAccountTests.asyncSetUp
    asyncTearDown=accounts.PlayerAccountTests.asyncTearDown
    http=accounts.PlayerAccountTests.http
    body=accounts.PlayerAccountTests.body
    cookie=accounts.PlayerAccountTests.cookie
    preauth=accounts.PlayerAccountTests.preauth
    signup=accounts.PlayerAccountTests.signup

    def player(self,nick,token=None):
        p=self.app._add_player(nick);p.conn=Connection(token);return p

    async def test_private_read_only_endpoint(self):
        path='/auth/player/stats'
        self.assertIn(b'403',await self.http(path))
        h,t,*_=await self.signup('stats@example.org')
        data=self.body(await self.http(path,extra_headers=h));self.assertEqual(data['played'],0);self.assertIsNone(data['favorite'])
        self.assertIn(b'405',await self.http(path,method='POST',extra_headers=h,data={'wins':9000}))
        a=self.player('Member',t);guest=self.player('Guest')
        await Match(self.app,'c4',[a,guest])._end_by_result('p1')
        other,*_=await self.signup('other@example.org')
        private=self.body(await self.http(path+'?email=stats@example.org',extra_headers=other));self.assertEqual(private['played'],0)
        mine=self.body(await self.http(path,extra_headers=h));self.assertEqual((mine['played'],mine['wins']),(1,1));self.assertNotIn('stats@example.org',str(mine))

    async def test_aggregate_results_persistence_and_no_double_count(self):
        _,t,*_=await self.signup('stats@example.org');a=self.player('Member',t);b=self.player('Guest')
        for game,outcome in [('c4','p1'),('c4','draw'),('pong','p2')]:
            m=Match(self.app,game,[a,b]);await m._end_by_result(outcome);self.app.close_match(m)
        stats=PlayerStats(self.auth.store).get('stats@example.org')
        self.assertEqual((stats['played'],stats['wins'],stats['draws'],stats['losses']),(3,1,1,1));self.assertEqual(stats['favorite'],__import__('games').GAMES['c4'].name)
        self.assertEqual(sum(g['played'] for g in stats['games']),3)

    async def test_cancelled_guest_and_revoked_login_do_not_count(self):
        _,t,*_=await self.signup('stats@example.org');a=self.player('Member',t);b=self.player('Guest')
        m=Match(self.app,'c4',[a,b]);await self.app.control.cancel_match(m)
        self.assertEqual(self.auth.stats('stats@example.org')['played'],0)
        a.conn.account_session_token=None
        m=Match(self.app,'c4',[a,b]);a.conn.account_session_token=t;await m._end_by_result('p1')
        self.assertEqual(self.auth.stats('stats@example.org')['played'],0)
        with self.auth.store.connect() as db:db.execute('DELETE FROM sessions WHERE token=?',(self.auth.store.digest(t),))
        await Match(self.app,'c4',[a,b])._end_by_result('p1')
        self.assertEqual(self.auth.stats('stats@example.org')['played'],0)

    async def test_start_identity_quit_and_account_deletion(self):
        _,t,*_=await self.signup('stats@example.org');a=self.player('Member',t);b=self.player('Guest')
        m=Match(self.app,'c4',[a,b]);a.conn.account_session_token=None;await m.abort(a)
        stats=self.auth.stats('stats@example.org');self.assertEqual((stats['played'],stats['losses']),(1,1))
        a.conn.account_session_token=t;b.conn.account_session_token=t
        await Match(self.app,'c4',[a,b])._end_by_result('p1');self.assertEqual(self.auth.stats('stats@example.org')['played'],1)
        b.conn.account_session_token=None;m=Match(self.app,'c4',[a,b])
        await self.app.web_admin.manage_player({'email':'owner@example.org','role':'owner'},'delete-player-account','stats@example.org')
        await m._end_by_result('p1')
        with self.auth.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM player_stats').fetchone()[0],0)
