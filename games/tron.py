"""Neon Tail (TRON-Prinzip) fuer 2-4 Spieler. Wer als letzter faehrt, gewinnt
die Runde; erster mit 3 Rundensiegen gewinnt den Match."""
from .base import Game, LEFT, RIGHT, UP, DOWN

TR_UP, TR_RT, TR_DN, TR_LF = 0, 1, 2, 3
GW = GH = 57
CELL = 4
OFF_X, OFF_Y = 6, 26
MATCH_WINS = 3
ROUND_DELAY_TICKS = 19  # ~1500 ms bei 80 ms/Tick
# Startpunkte zu zweit: gegenueber, zur Mitte fahrend (wie im Original)
STARTS_2 = [(8, 28, TR_RT), (48, 28, TR_LF)]
# Ab drei Spielern versetzt wie ein Windrad: niemand faehrt frontal auf die
# Mitte zu, jeder hat gleich lange (28 Schritte) bis zur ersten fremden Spur.
STARTS_4 = [(8, 20, TR_RT), (48, 36, TR_LF), (36, 8, TR_DN), (20, 48, TR_UP)]


def _opp(a, b):
    return (a + 2) % 4 == b


def _nxt(x, y, d):
    if d == TR_UP:
        return x, y - 1
    if d == TR_DN:
        return x, y + 1
    if d == TR_LF:
        return x - 1, y
    return x + 1, y


class Tron(Game):
    gid = "tron"
    name = "Neon Tail"
    tick_ms = 80
    max_players = 4

    def __init__(self, n=2):
        super().__init__(n)
        self.score = [0] * n
        self.active = [True] * n     # False = hat das Spiel verlassen
        self.rnd = 0
        self.status = 0              # 0 laeuft, 1 Rundenpause
        self.rwin = 0                # Rundensieger (1..n), 0 = unentschieden
        self._delay = 0
        self._init_round()

    def _init_round(self):
        self.grid = [[0] * GH for _ in range(GW)]
        self.pos = []
        self.alive = []
        for i in range(self.n):
            x, y, d = (STARTS_2 if self.n == 2 else STARTS_4)[i]
            self.pos.append([x, y, d])
            self.alive.append(self.active[i])
            if self.active[i]:
                self.grid[x][y] = i + 1
        self.status = 0
        self.rnd += 1

    def _dir_from_edge(self, p, cur):
        e = self.edge(p)
        # Prioritaet UP, RIGHT, DOWN, LEFT; Umkehr (180 Grad) verboten.
        for bit, d in ((UP, TR_UP), (RIGHT, TR_RT), (DOWN, TR_DN), (LEFT, TR_LF)):
            if e & bit and not _opp(d, cur):
                return d
        return cur

    def remove_player(self, p):
        i = p - 1
        self.active[i] = False
        self.alive[i] = False
        left = [k for k in range(self.n) if self.active[k]]
        if len(left) == 1:
            self.finish(f"p{left[0] + 1}")

    def _step(self):
        if self.status != 0:
            # Rundenpause; danach neue Runde oder Match-Ende.
            self._delay += 1
            if self._delay >= ROUND_DELAY_TICKS:
                self._delay = 0
                for i in range(self.n):
                    if self.score[i] >= MATCH_WINS:
                        self.finish(f"p{i + 1}")
                        return
                self._init_round()
            return

        live = [i for i in range(self.n) if self.alive[i]]
        nxt = {}
        for i in live:
            x, y, d = self.pos[i]
            d = self._dir_from_edge(i + 1, d)
            self.pos[i][2] = d
            nxt[i] = _nxt(x, y, d)

        dead = set()
        for i in live:
            x, y = nxt[i]
            if x < 0 or x >= GW or y < 0 or y >= GH or self.grid[x][y] != 0:
                dead.add(i)
        # Frontal (gleiches Zielfeld) oder Positionstausch -> beide tot.
        for a in live:
            for b in live:
                if a < b:
                    if nxt[a] == nxt[b] or (nxt[a] == tuple(self.pos[b][:2]) and
                                            nxt[b] == tuple(self.pos[a][:2])):
                        dead.update((a, b))
        for i in live:
            if i in dead:
                self.alive[i] = False
            else:
                self.pos[i][0], self.pos[i][1] = nxt[i]
                self.grid[nxt[i][0]][nxt[i][1]] = i + 1

        survivors = [i for i in range(self.n) if self.alive[i]]
        if len(survivors) <= 1:
            self.status = 1
            self._delay = 0
            if survivors:
                self.rwin = survivors[0] + 1
                self.score[survivors[0]] += 1
            else:
                self.rwin = 0

    def snapshot(self, view=None):
        return {
            "g": self.gid,
            "rnd": self.rnd,
            "h": [[p[0], p[1], 1 if a else 0] for p, a in zip(self.pos, self.alive)],
            "act": [1 if a else 0 for a in self.active],
            "st": self.status,
            "rw": self.rwin,
            "sc": self.score,
            "win": MATCH_WINS,
            "cell": CELL,
            "off": [OFF_X, OFF_Y],
            "gsz": [GW, GH],
        }

    def console_stat(self):
        return ":".join(str(s) for s in self.score)
