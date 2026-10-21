"""Private account aggregates, populated only from server-scored matches."""
import logging
import games

class PlayerStats:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS player_stats(
                email TEXT NOT NULL,game TEXT NOT NULL,played INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,losses INTEGER NOT NULL DEFAULT 0,draws INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(email,game))""")

    def participants(self,players):
        accounts={}
        for p in players:
            token=getattr(p.conn,'account_session_token',None) if p.conn else None
            session=self.store.session(token) if token else None
            if session and session['role']=='host' and session['email'].startswith('player:'):
                accounts[p]=session['email'][7:]
        # An account occupying several seats has no unambiguous personal result.
        return {p:email for p,email in accounts.items() if list(accounts.values()).count(email)==1}

    def record(self,match):
        if match.end_reason not in ('normal','leave','connection_timeout'):return
        rows=[]
        for player,email in getattr(match,'account_participants',{}).items():
            outcome=match.outcomes.get(player.nick)
            if outcome in ('win','loss','draw'):
                rows.append((email,match.gid,int(outcome=='win'),int(outcome=='loss'),int(outcome=='draw'),email))
        if not rows:return
        try:
            with self.store.connect() as db:
                db.executemany("""INSERT INTO player_stats(email,game,played,wins,losses,draws)
                    SELECT ?,?,1,?,?,? WHERE EXISTS(SELECT 1 FROM player_accounts WHERE email=?)
                    ON CONFLICT(email,game) DO UPDATE SET played=played+1,wins=wins+excluded.wins,
                    losses=losses+excluded.losses,draws=draws+excluded.draws""",rows)
        except Exception:logging.exception('Personal statistics could not be saved')

    def get(self,email):
        with self.store.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT game,played,wins,losses,draws FROM player_stats WHERE email=? ORDER BY played DESC,game',(email,))]
        for row in rows:row['name']=games.GAMES[row['game']].name if row['game'] in games.GAMES else row['game']
        return {'played':sum(r['played'] for r in rows),'wins':sum(r['wins'] for r in rows),
                'losses':sum(r['losses'] for r in rows),'draws':sum(r['draws'] for r in rows),
                'favorite':rows[0]['name'] if rows else None,'games':rows}
