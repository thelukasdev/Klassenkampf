"""Explicit, own-room-only player capabilities; admin roles stay separate."""
import json
import time

DEFAULTS = {'max_sessions': 1, 'keep_empty': False, 'moderate_players': False,
            'manage_games': False, 'view_results': False, 'view_replays': False,
            'manage_saves': False}
ACTIONS = {
    'kick': 'moderate_players', 'ban': 'moderate_players', 'unban': 'moderate_players',
    'reset-credits': 'moderate_players', 'remove-player': 'moderate_players',
    'move-player': 'moderate_players', 'mode': 'manage_games', 'rules': 'manage_games',
    'pause-match': 'manage_games', 'end-match': 'manage_games', 'spectators': 'manage_games',
    'save': 'manage_saves', 'load': 'manage_saves',
}


def extended(policy):
    return policy['max_sessions'] > 1 or any(policy[k] for k in ACTIONS.values()) or policy['view_results'] or policy['view_replays']


class PlayerPermissions:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS player_permissions(email TEXT PRIMARY KEY,data TEXT NOT NULL)')

    def get(self, email):
        if email.startswith('player:'):
            email = email[7:]
        with self.store.connect() as db:
            row = db.execute('SELECT data FROM player_permissions WHERE email=?', (email,)).fetchone()
        return {**DEFAULTS, **(json.loads(row['data']) if row else {})}

    def set(self, actor, email, policy):
        from web_admin import Denied
        if actor['role'] not in ('owner', 'admin'):
            raise Denied('Nur Administratoren dürfen Spielerrechte vergeben.')
        email = self.store.email(email)
        if not isinstance(policy, dict) or set(policy) != set(DEFAULTS):
            raise ValueError('Ungültige Spielerrechte.')
        if type(policy['max_sessions']) is not int or not 1 <= policy['max_sessions'] <= 16:
            raise ValueError('Sitzungslimit muss zwischen 1 und 16 liegen.')
        if any(type(policy[k]) is not bool for k in DEFAULTS if k != 'max_sessions'):
            raise ValueError('Ungültige Spielerrechte.')
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM player_accounts WHERE email=?', (email,)).fetchone():
                raise ValueError('Spielerkonto nicht gefunden.')
            db.execute('INSERT OR REPLACE INTO player_permissions VALUES(?,?)', (email, json.dumps(policy)))
            db.execute('INSERT INTO audit(time,email,action,detail) VALUES(?,?,?,?)',
                       (int(time.time()), actor['email'], 'player-permissions', email+' '+json.dumps(policy)))

    @staticmethod
    def permits(policy, action):
        return action in ('create-session', 'end-session') or bool(policy.get(ACTIONS.get(action, ''), False))
