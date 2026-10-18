"""BomberBob (Bomberman-Prinzip). 2-4 Spieler, gitterbasierte Arena.

Bombe legen (A), Timer laeuft, Flammenkreuz zerstoert zerstoerbare Bloecke und
toetet Spieler. Zerstoerte Bloecke geben evtl. Power-ups (mehr Bomben / mehr
Reichweite). Letzter Ueberlebender gewinnt; gleichzeitiger Tod / Zeitablauf =
Unentschieden. Einzelrunde.
"""
import math
import random

from .base import Game, LEFT, RIGHT, UP, DOWN, BTN_A, BTN_B

EMPTY, SOLID, BLOCK = 0, 1, 2
COLS, ROWS = 11, 13
CS = 20
OX, OY = 10, 18
SPEED = 1.7         # Pixel/Tick, Bewegung von Feldmitte zu Feldmitte
BOMB_TICKS = 60     # ~2 s
FLAME_TICKS = 16    # ~0.5 s
LIMIT_MS = 90000
PU_CHANCE = 0.30
CAP_BOMBS = 6
CAP_RANGE = 6
# Startecken: oben links, unten rechts, oben rechts, unten links
STARTS = [(1, 1), (COLS - 2, ROWS - 2), (COLS - 2, 1), (1, ROWS - 2)]
START_CLEAR = {(1, 1), (2, 1), (1, 2), (COLS - 2, ROWS - 2),
               (COLS - 3, ROWS - 2), (COLS - 2, ROWS - 3),
               (COLS - 2, 1), (COLS - 3, 1), (COLS - 2, 2),
               (1, ROWS - 2), (2, ROWS - 2), (1, ROWS - 3)}


def _cx(c):
    return OX + c * CS + CS / 2


def _cy(r):
    return OY + r * CS + CS / 2


class Bomber(Game):
    gid = "bomber"
    name = "BomberBob"
    tick_ms = 33
    max_players = 4

    def __init__(self, n=2):
        super().__init__(n)
        self.status = 0           # 0 laeuft, 1 beendet
        self.winner = 0           # Sieger 1..n, 0 = unentschieden
        self.tleft = LIMIT_MS
        self._gen_grid()
        self.p = {i + 1: self._mk(i + 1, *STARTS[i]) for i in range(n)}
        self.bombs = []           # {c,r,t,owner,range,phase:set}
        self.bomb_at = {}         # (c,r) -> bomb
        self.flames = {}          # (c,r) -> life
        self.powerups = {}        # (c,r) -> 'b'|'f'

    def _gen_grid(self):
        self.grid = [[EMPTY] * ROWS for _ in range(COLS)]
        for c in range(COLS):
            for r in range(ROWS):
                if c == 0 or r == 0 or c == COLS - 1 or r == ROWS - 1:
                    self.grid[c][r] = SOLID
                elif c % 2 == 0 and r % 2 == 0:
                    self.grid[c][r] = SOLID
        for c in range(1, COLS - 1):
            for r in range(1, ROWS - 1):
                if (self.grid[c][r] == EMPTY and (c, r) not in START_CLEAR
                        and random.random() < 0.75):
                    self.grid[c][r] = BLOCK

    def _mk(self, pid, c, r):
        x, y = _cx(c), _cy(r)
        return {"id": pid, "x": x, "y": y, "tx": x, "ty": y, "alive": True,
                "max_bombs": 1, "range": 2}

    # ---------- Hilfen ----------
    def _cell_c(self, x):
        return max(0, min(COLS - 1, int((x - OX) // CS)))

    def _cell_r(self, y):
        return max(0, min(ROWS - 1, int((y - OY) // CS)))

    def _passable(self, c, r, pid):
        if c < 0 or c >= COLS or r < 0 or r >= ROWS:
            return False
        if self.grid[c][r] != EMPTY:
            return False
        b = self.bomb_at.get((c, r))
        if b is not None and pid not in b["phase"]:
            return False
        return True

    # ---------- Bewegung (strikt kachelweise, immer auf den Linien) ----------
    def _move(self, p, dx, dy):
        # Am Zielfeld eingerastet -> ggf. neues Ziel in gedrueckter Richtung
        if abs(p["x"] - p["tx"]) <= SPEED and abs(p["y"] - p["ty"]) <= SPEED:
            p["x"], p["y"] = p["tx"], p["ty"]
            col, row = self._cell_c(p["x"]), self._cell_r(p["y"])
            if dx and self._passable(col + dx, row, p["id"]):
                p["tx"] = _cx(col + dx)
            elif dy and self._passable(col, row + dy, p["id"]):
                p["ty"] = _cy(row + dy)
        # Auf das Ziel zubewegen (nur eine Achse weicht je Schritt ab)
        if p["x"] < p["tx"]:
            p["x"] = min(p["tx"], p["x"] + SPEED)
        elif p["x"] > p["tx"]:
            p["x"] = max(p["tx"], p["x"] - SPEED)
        if p["y"] < p["ty"]:
            p["y"] = min(p["ty"], p["y"] + SPEED)
        elif p["y"] > p["ty"]:
            p["y"] = max(p["ty"], p["y"] - SPEED)

    def _update_phase(self, p):
        pc = (self._cell_c(p["x"]), self._cell_r(p["y"]))
        for b in self.bombs:
            if p["id"] in b["phase"] and (b["c"], b["r"]) != pc:
                b["phase"].discard(p["id"])

    # ---------- Bomben ----------
    def _place_bomb(self, p):
        active = sum(1 for b in self.bombs if b["owner"] == p["id"])
        if active >= p["max_bombs"]:
            return
        c = self._cell_c(p["x"])
        r = self._cell_r(p["y"])
        if (c, r) in self.bomb_at:
            return
        b = {"c": c, "r": r, "t": BOMB_TICKS, "owner": p["id"],
             "range": p["range"], "phase": {p["id"]}}
        self.bombs.append(b)
        self.bomb_at[(c, r)] = b

    def _add_flame(self, c, r):
        self.flames[(c, r)] = FLAME_TICKS
        self.powerups.pop((c, r), None)

    def _maybe_powerup(self, c, r):
        if random.random() < PU_CHANCE:
            self.powerups[(c, r)] = random.choice(["b", "f"])

    def _explode(self, b, queue, done):
        self._add_flame(b["c"], b["r"])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for i in range(1, b["range"] + 1):
                c = b["c"] + dx * i
                r = b["r"] + dy * i
                if c < 0 or c >= COLS or r < 0 or r >= ROWS:
                    break
                cell = self.grid[c][r]
                if cell == SOLID:
                    break
                if cell == BLOCK:
                    self.grid[c][r] = EMPTY
                    self._add_flame(c, r)
                    self._maybe_powerup(c, r)
                    break
                ob = self.bomb_at.get((c, r))
                if ob is not None and ob is not b and id(ob) not in done:
                    queue.append(ob)
                    self._add_flame(c, r)
                    break
                self._add_flame(c, r)

    def _tick_bombs(self):
        for b in self.bombs:
            b["t"] -= 1
        queue = [b for b in self.bombs if b["t"] <= 0]
        done = set()
        while queue:
            b = queue.pop()
            if id(b) in done:
                continue
            done.add(id(b))
            self._explode(b, queue, done)
        if done:
            self.bombs = [b for b in self.bombs if id(b) not in done]
            self.bomb_at = {k: v for k, v in self.bomb_at.items() if id(v) not in done}

    def _decay_flames(self):
        for k in list(self.flames.keys()):
            self.flames[k] -= 1
            if self.flames[k] <= 0:
                del self.flames[k]

    def _pickup(self, p):
        key = (self._cell_c(p["x"]), self._cell_r(p["y"]))
        t = self.powerups.pop(key, None)
        if t == "b":
            p["max_bombs"] = min(CAP_BOMBS, p["max_bombs"] + 1)
        elif t == "f":
            p["range"] = min(CAP_RANGE, p["range"] + 1)

    def _check_deaths(self):
        for p in self.p.values():
            if p["alive"]:
                cell = (self._cell_c(p["x"]), self._cell_r(p["y"]))
                if cell in self.flames:
                    p["alive"] = False

    # ---------- Simulation ----------
    def _step(self):
        if self.status != 0:
            return
        self.tleft -= self.tick_ms
        for p in self.p.values():
            if not p["alive"]:
                continue
            m = self.mask(p["id"])
            dx = dy = 0
            if m & LEFT:
                dx = -1
            elif m & RIGHT:
                dx = 1
            elif m & UP:
                dy = -1
            elif m & DOWN:
                dy = 1
            self._move(p, dx, dy)
            self._update_phase(p)
            if self.edge(p["id"]) & (BTN_A | BTN_B):
                self._place_bomb(p)
            self._pickup(p)

        self._tick_bombs()
        self._check_deaths()
        self._decay_flames()

        self._check_end()

    def _check_end(self):
        if self.status != 0:
            return
        alive = [i for i, p in self.p.items() if p["alive"]]
        if len(alive) == 1:
            self.status, self.winner = 1, alive[0]
            self.finish(f"p{alive[0]}")
        elif not alive or self.tleft <= 0:
            self.status, self.winner = 1, 0
            self.finish("draw")

    def remove_player(self, p):
        self.p[p]["alive"] = False
        self._check_end()

    def snapshot(self, view=None):
        grid = "".join(str(self.grid[c][r]) for r in range(ROWS) for c in range(COLS))
        return {
            "g": self.gid,
            "cs": CS, "ox": OX, "oy": OY, "cols": COLS, "rows": ROWS,
            "grid": grid,
            "p": [{"x": round(self.p[i]["x"], 1), "y": round(self.p[i]["y"], 1),
                   "al": self.p[i]["alive"], "b": self.p[i]["max_bombs"],
                   "f": self.p[i]["range"]} for i in range(1, self.n + 1)],
            "bombs": [[b["c"], b["r"], b["t"]] for b in self.bombs],
            "fl": [[c, r] for (c, r) in self.flames],
            "pw": [[c, r, t] for (c, r), t in self.powerups.items()],
            "st": self.status,
            "w": self.winner,
            "t": max(0, math.ceil(self.tleft / 1000)),
        }

    def console_stat(self):
        alive = sum(1 for p in self.p.values() if p["alive"])
        return f"{alive}/{self.n} leben  {max(0, math.ceil(self.tleft/1000))}s"
