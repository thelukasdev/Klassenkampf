"""Vector Duel. Asteroids-artiges Schiff-gegen-Schiff mit Wrap-around.
Erster mit 5 Abschuessen gewinnt. Zeiten in Ticks (33 ms)."""
import math

from .base import Game, LEFT, RIGHT, UP, DOWN, BTN_A, BTN_B

TY = 32
BAND = 280 - TY  # 248
WIN = 5
TURN = 0.18
THR = 0.10
DRAG = 0.9925
MAXV = 4.375
SHV = 4.5
SHL = 55
SH_MAX = 90
SH_REC = 30
SH_R2 = 14 * 14
RES_TICKS = 36     # ~1200 ms
INV_TICKS = 45     # ~1500 ms
FIRE_CD = 7        # ~220 ms


def _wrap(x, y):
    if x < 0:
        x += 240
    elif x >= 240:
        x -= 240
    if y < TY:
        y += BAND
    elif y >= 280:
        y -= BAND
    return x, y


class Duel(Game):
    gid = "duel"
    name = "Vector Duel"
    tick_ms = 33

    def __init__(self):
        super().__init__()
        self.s1 = 0
        self.s2 = 0
        self.status = 0
        self.shots = []          # {x,y,vx,vy,life,owner}
        self.last_fire = {1: -99, 2: -99}
        self.ship = {1: self._spawn(1), 2: self._spawn(2)}

    def _spawn(self, p):
        return {
            "x": 60.0 if p == 1 else 180.0,
            "y": 140.0,
            "vx": 0.0, "vy": 0.0,
            "ang": 0.0 if p == 1 else math.pi,
            "alive": True,
            "respawn": 0,
            "invuln": INV_TICKS,   # kurze Startinvuln
            "charge": SH_MAX,
            "sactive": False,
            "slocked": False,
            "regen": 0,
        }

    def _apply_in(self, p):
        s = self.ship[p]
        m = self.mask(p)
        if m & LEFT:
            s["ang"] -= TURN
        if m & RIGHT:
            s["ang"] += TURN
        if m & UP:
            s["vx"] += math.cos(s["ang"]) * THR
            s["vy"] += math.sin(s["ang"]) * THR
            spd = math.hypot(s["vx"], s["vy"])
            if spd > MAXV:
                k = MAXV / spd
                s["vx"] *= k
                s["vy"] *= k
        want = bool(m & DOWN)
        s["sactive"] = want and not s["slocked"] and s["charge"] > 0
        if s["slocked"] and s["charge"] >= SH_REC:
            s["slocked"] = False

    def _fire(self, p):
        s = self.ship[p]
        if not s["alive"] or s["sactive"]:
            return
        if (self.edge(p) & (BTN_A | BTN_B)) and self.frame - self.last_fire[p] >= FIRE_CD:
            self.last_fire[p] = self.frame
            a = s["ang"]
            self.shots.append({
                "x": s["x"] + math.cos(a) * 8,
                "y": s["y"] + math.sin(a) * 8,
                "vx": math.cos(a) * SHV + s["vx"] * 0.5,
                "vy": math.sin(a) * SHV + s["vy"] * 0.5,
                "life": SHL, "owner": p,
            })

    def _integ(self, p):
        s = self.ship[p]
        if not s["alive"]:
            if self.frame >= s["respawn"]:
                self.ship[p] = self._spawn(p)
                self.ship[p]["invuln"] = self.frame + INV_TICKS
            return
        s["vx"] *= DRAG
        s["vy"] *= DRAG
        s["x"] += s["vx"]
        s["y"] += s["vy"]
        s["x"], s["y"] = _wrap(s["x"], s["y"])

    def _upd_shield(self, p):
        s = self.ship[p]
        if s["sactive"]:
            s["charge"] = max(0, s["charge"] - 2)
            if s["charge"] == 0:
                s["sactive"] = False
                s["slocked"] = True
        else:
            s["regen"] += 1
            if s["regen"] % 4 == 0 and s["charge"] < SH_MAX:
                s["charge"] += 1

    def _ship_col(self):
        a, b = self.ship[1], self.ship[2]
        if not (a["alive"] and b["alive"]):
            return
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        d = math.hypot(dx, dy)
        if 0 < d < 16:
            nx, ny = dx / d, dy / d
            push = (16 - d) * 0.5 + 0.1
            a["x"] -= nx * push
            a["y"] -= ny * push
            b["x"] += nx * push
            b["y"] += ny * push
            a["x"], a["y"] = _wrap(a["x"], a["y"])
            b["x"], b["y"] = _wrap(b["x"], b["y"])
            rv = (a["vx"] - b["vx"]) * nx + (a["vy"] - b["vy"]) * ny
            if rv > 0:
                imp = rv * 0.95
                a["vx"] -= imp * nx
                a["vy"] -= imp * ny
                b["vx"] += imp * nx
                b["vy"] += imp * ny

    def _shots(self):
        alive = []
        for sh in self.shots:
            sh["x"] += sh["vx"]
            sh["y"] += sh["vy"]
            sh["x"], sh["y"] = _wrap(sh["x"], sh["y"])
            sh["life"] -= 1
            if sh["life"] <= 0:
                continue
            tgt = self.ship[2 if sh["owner"] == 1 else 1]
            if tgt["alive"] and self.frame >= tgt["invuln"]:
                dx = sh["x"] - tgt["x"]
                dy = sh["y"] - tgt["y"]
                r2 = dx * dx + dy * dy
                if tgt["sactive"] and r2 < SH_R2:
                    continue  # geblockt
                if r2 < 64:
                    tgt["alive"] = False
                    tgt["respawn"] = self.frame + RES_TICKS
                    if sh["owner"] == 1:
                        self.s1 += 1
                    else:
                        self.s2 += 1
                    continue
            alive.append(sh)
        self.shots = alive

    def _step(self):
        if self.status != 0:
            return
        for p in (1, 2):
            self._apply_in(p)
            self._fire(p)
        for p in (1, 2):
            self._integ(p)
            self._upd_shield(p)
        self._ship_col()
        self._shots()
        if self.s1 >= WIN:
            self.status = 1
            self.finish("p1")
        elif self.s2 >= WIN:
            self.status = 2
            self.finish("p2")

    def snapshot(self, view=None):
        def ser(s):
            return {
                "x": round(s["x"], 1), "y": round(s["y"], 1),
                "a": round(s["ang"], 3), "al": s["alive"],
                "ch": s["charge"], "sh": s["sactive"],
                "lk": s["slocked"], "iv": self.frame < s["invuln"],
            }
        return {
            "g": self.gid,
            "s": {"1": ser(self.ship[1]), "2": ser(self.ship[2])},
            "sh": [[round(s["x"], 1), round(s["y"], 1), s["owner"]] for s in self.shots],
            "s1": self.s1, "s2": self.s2, "st": self.status,
            "win": WIN, "ty": TY, "shmax": SH_MAX,
        }

    def console_stat(self):
        return f"{self.s1}:{self.s2}"
