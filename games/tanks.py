"""Tiny Tanks. Rundenbasierte Artillerie, best of 3 (3 Rundensiege).

Terrain wie in der PBC-Version: destruktibles Pixel-Gitter `solid[ROWS][W]`.
Krater = ausgestanzte Kreisscheibe (Grundgestein ab y=240 bleibt stehen),
danach SETTLE-Phase mit senkrechtem Nachrieseln (gravityPass), bis nichts mehr
rutscht. An den Client wird pro Frame die Oberflaechen-Hoehenkarte geschickt,
sodass das Nachrieseln als absinkende Saeulen sichtbar wird.
"""
import base64
import math
import random

from .base import Game, LEFT, RIGHT, UP, DOWN, BTN_A, BTN_B

W, H = 240, 280
TER_TOP = 100
ROWS = H - TER_TOP        # 180
BEDROCK = 240             # y >= 240 unzerstoerbar
REPOSE = 4
MAX_HP = 50
WINS_NEEDED = 1   # nur eine Runde -> erster Abschuss entscheidet

AIM_READY = 24
AIM_REPEAT = 2
EXP_GROW = 18
EXP_TOTAL = 38
ROUNDWAIT_TICKS = 45

# Waffen: (name, kraterradius, blastradius, schaden, farbe, startmunition)
WEAPONS = [
    ("Basic Shell", 18, 14, 30, "P1", None),
    ("Inferno Blast", 36, 28, 30, "P1", 2),
    ("Shock Charge", 18, 14, 60, "SHOCK", 2),
    ("Golden Dome", 0, 0, 0, "SHIELD", 1),
]
WP_BASIC, WP_INFERNO, WP_SHOCK, WP_DOME = 0, 1, 2, 3
AIM, FLY, EXPLODE, SETTLE, ROUNDWAIT, MATCH = 0, 1, 2, 3, 4, 5


class Tanks(Game):
    gid = "tanks"
    name = "Tiny Tanks"
    tick_ms = 33

    def __init__(self):
        super().__init__()
        self.wins1 = 0
        self.wins2 = 0
        self.angleP = {1: 45, 2: 45}
        self.powerP = {1: 50, 2: 50}
        self.tvers = 0
        self._grid_snap_tvers = -1   # Versionsstand des zuletzt gesendeten Gitters
        self._init_round()

    # ---------------- Terrain (Pixel-Gitter) ----------------
    def _is_solid(self, x, y):
        if x < 0 or x >= W or y >= H:
            return True
        if y < TER_TOP:
            return False
        return self.solid[y - TER_TOP][x]

    def _set_solid(self, x, y, v):
        if 0 <= x < W and TER_TOP <= y < H:
            self.solid[y - TER_TOP][x] = 1 if v else 0

    def _gen_terrain(self):
        a, b, c, d = (random.uniform(0, 10) for _ in range(4))
        self.terr = [0] * W   # Stapelhoehe von unten
        for x in range(W):
            t = x * 0.045
            h = 110 + 28 * math.sin(t + a) + 18 * math.sin(2 * t + b) \
                + 10 * math.sin(0.6 * t + c) + 6 * math.sin(4 * t + d)
            self.terr[x] = int(max(50, min(170, h)))
        # Boeschung (angle of repose) einebnen
        rev = False
        for _ in range(600):
            if not self._slump(rev):
                break
            rev = not rev

    def _slump(self, rev):
        moved = False
        rng = range(W - 2, -1, -1) if rev else range(W - 1)
        for x in rng:
            diff = self.terr[x] - self.terr[x + 1]
            if diff > REPOSE:
                self.terr[x] -= 1
                self.terr[x + 1] += 1
                moved = True
            elif diff < -REPOSE:
                self.terr[x] += 1
                self.terr[x + 1] -= 1
                moved = True
        return moved

    def _place_tanks(self):
        for cx, key in ((25, "h1"), (215, "h2")):
            hmax = 0
            for x in range(max(0, cx - 10), min(W, cx + 11)):
                hmax = max(hmax, self.terr[x])
            for x in range(max(0, cx - 8), min(W, cx + 9)):
                self.terr[x] = hmax

    def _build_grid(self):
        self.solid = [bytearray(W) for _ in range(ROWS)]
        for x in range(W):
            top = H - self.terr[x]
            for gy in range(ROWS):
                if gy + TER_TOP >= top:
                    self.solid[gy][x] = 1

    def _grid_to_heightmap(self):
        for x in range(W):
            top = H
            for gy in range(ROWS):
                if self.solid[gy][x]:
                    top = gy + TER_TOP
                    break
            self.terr[x] = H - top

    def _ground_top(self, x):
        x = max(0, min(W - 1, x))
        for gy in range(ROWS):
            if self.solid[gy][x]:
                return gy + TER_TOP
        return H

    def _surface(self):
        """Oberflaechen-Hoehenkarte (y je Spalte) fuer den Client."""
        return [self._ground_top(x) for x in range(W)]

    def _encode_grid(self):
        """Volles Pixel-Gitter bit-gepackt (Bit-Index = x*ROWS + gy), base64.
        Bildet auch Hohlraeume/Ueberhaenge ab -> Client zeigt Einsturz."""
        buf = bytearray((W * ROWS + 7) // 8)
        solid = self.solid
        idx = 0
        for x in range(W):
            for gy in range(ROWS):
                if solid[gy][x]:
                    buf[idx >> 3] |= 1 << (idx & 7)
                idx += 1
        return base64.b64encode(buf).decode()

    def _carve(self, cx, cy, r):
        cx, cy, r = int(cx), int(cy), int(r)
        for y in range(cy - r, cy + r + 1):
            if y >= BEDROCK:
                continue
            dy = y - cy
            for x in range(cx - r, cx + r + 1):
                dx = x - cx
                if dx * dx + dy * dy <= r * r:
                    self._set_solid(x, y, False)
        self.tvers += 1

    def _gravity_pass(self):
        moved = False
        solid = self.solid
        for gy in range(ROWS - 2, -1, -1):
            cur = solid[gy]
            nxt = solid[gy + 1]
            for x in range(W):
                if cur[x] and not nxt[x]:
                    cur[x] = 0
                    nxt[x] = 1
                    moved = True
        return moved

    # ---------------- Runde ----------------
    def _init_round(self):
        self._gen_terrain()
        self._place_tanks()
        self._build_grid()
        self.tvers += 1
        self.tx = {1: 25, 2: 215}
        self.hp = {1: MAX_HP, 2: MAX_HP}
        self.ammo = {1: {}, 2: {}}
        for p in (1, 2):
            for i, wp in enumerate(WEAPONS):
                if wp[5] is not None:
                    self.ammo[p][i] = wp[5]
        self.sel = {1: WP_BASIC, 2: WP_BASIC}
        self.shield = {1: None, 2: None}
        self.active = 1 if (self.wins1 + self.wins2) % 2 == 0 else 2
        self.phase = AIM
        self.wind = random.randint(-8, 8)
        self.aim_ready = self.frame + AIM_READY
        self.last_aim = 0
        self.prj = None
        self.exp = None
        self.round_winner = 0
        self._wait = 0

    def _tank_y(self, p):
        return self._ground_top(self.tx[p])

    # ---------------- Eingabe / Aim ----------------
    def _cur_ammo(self, p):
        return self.ammo[p].get(self.sel[p], -1)

    def _cycle(self, p):
        for _ in range(4):
            self.sel[p] = (self.sel[p] + 1) % 4
            if self.sel[p] == WP_BASIC or self.ammo[p].get(self.sel[p], 0) > 0:
                return

    def _handle_aim(self, p):
        m = self.mask(p)
        e = self.edge(p)
        asign = 1 if p == 1 else -1
        if self.frame - self.last_aim >= AIM_REPEAT:
            moved = False
            if m & LEFT:
                self.angleP[p] += 2 * asign; moved = True
            if m & RIGHT:
                self.angleP[p] -= 2 * asign; moved = True
            if m & UP:
                self.powerP[p] += 2; moved = True
            if m & DOWN:
                self.powerP[p] -= 2; moved = True
            if moved:
                self.last_aim = self.frame
                self.angleP[p] = max(5, min(175, self.angleP[p]))
                self.powerP[p] = max(10, min(100, self.powerP[p]))
        if e & BTN_A:
            self._cycle(p)
        if (e & BTN_B) and self.frame >= self.aim_ready:
            self._fire(p)

    def _fire(self, p):
        w = self.sel[p]
        if w == WP_DOME:
            if self.ammo[p].get(WP_DOME, 0) > 0:
                self.ammo[p][WP_DOME] -= 1
                self.shield[p] = set(range(32))
            self._cycle(p)
            self._switch()
            return
        if w != WP_BASIC:
            if self.ammo[p].get(w, 0) <= 0:
                return
            self.ammo[p][w] -= 1
        rad = self.angleP[p] * 0.0174533
        dirx = math.cos(rad)
        diry = -math.sin(rad)
        if p == 2:
            dirx = -dirx
        speed = self.powerP[p] * 0.08
        sx = self.tx[p]
        sy = self._tank_y(p) - 6
        self.prj = {"x": sx + dirx * 10, "y": sy + diry * 10,
                    "vx": dirx * speed, "vy": diry * speed, "owner": p, "w": w}
        self.phase = FLY
        if self.sel[p] != WP_BASIC and self.ammo[p].get(self.sel[p], 0) <= 0:
            self._cycle(p)

    def _switch(self):
        if self.hp[1] <= 0 or self.hp[2] <= 0:
            if self.hp[1] <= 0 and self.hp[2] <= 0:
                self.round_winner = 0
            elif self.hp[1] <= 0:
                self.round_winner = 2
                self.wins2 += 1
            else:
                self.round_winner = 1
                self.wins1 += 1
            if self.wins1 >= WINS_NEEDED:
                self.phase = MATCH
                self.finish("p1")
            elif self.wins2 >= WINS_NEEDED:
                self.phase = MATCH
                self.finish("p2")
            elif self.round_winner == 0 and WINS_NEEDED == 1:
                # gleichzeitiger Abschuss in der Einzelrunde -> Unentschieden
                self.phase = MATCH
                self.finish("draw")
            else:
                self.phase = ROUNDWAIT
                self._wait = 0
            return
        self.active = 2 if self.active == 1 else 1
        self.phase = AIM
        self.wind = random.randint(-8, 8)
        self.aim_ready = self.frame + AIM_READY

    # ---------------- Physik ----------------
    def _apply_damage(self, cx, cy, r, dmg):
        for p in (1, 2):
            tx = self.tx[p]
            ty = self._tank_y(p)
            d = math.hypot(tx - cx, ty - cy)
            if d < r:
                self.hp[p] = max(0, self.hp[p] - dmg * (1 - d / r))

    def _detonate(self, cx, cy, w):
        _, _, blastR, dmg, col, _ = WEAPONS[w]
        cx, cy = int(cx), int(cy)
        self._apply_damage(cx, cy, blastR + 8, dmg)
        self.exp = {"x": cx, "y": cy, "w": w, "frame": 0, "col": col}
        self.prj = None
        self.phase = EXPLODE

    def _tick_fly(self):
        for _ in range(2):
            pr = self.prj
            if pr is None:
                return
            pr["x"] += pr["vx"]
            pr["y"] += pr["vy"]
            pr["vy"] += 0.12
            pr["vx"] += self.wind * 0.002
            ix, iy = int(pr["x"]), int(pr["y"])
            if pr["x"] < 0 or pr["x"] >= W:
                self.prj = None
                self._switch()
                return
            if pr["y"] < 0:
                continue
            foe = 2 if pr["owner"] == 1 else 1
            if self.shield[foe]:
                fx, fy = self.tx[foe], self._tank_y(foe)
                d = math.hypot(pr["x"] - fx, pr["y"] - fy)
                if d < 22:
                    seg = int((math.atan2(pr["y"] - fy, pr["x"] - fx) / (2 * math.pi)) * 32) % 32
                    if seg in self.shield[foe]:
                        self.shield[foe].discard(seg)
                        if not self.shield[foe]:
                            self.shield[foe] = None
                        self._detonate(pr["x"], pr["y"], pr["w"])
                        return
            for p in (1, 2):
                if math.hypot(pr["x"] - self.tx[p], pr["y"] - self._tank_y(p)) < 8:
                    self._detonate(pr["x"], pr["y"], pr["w"])
                    return
            if self._is_solid(ix, iy):
                self._detonate(pr["x"], pr["y"], pr["w"])
                return

    def _tick_explode(self):
        if self.exp["frame"] == EXP_GROW:
            holeR = WEAPONS[self.exp["w"]][1]
            self._carve(self.exp["x"], self.exp["y"], holeR)
            # Schildsegmente im Kraterradius fallen weg
            for p in (1, 2):
                if self.shield[p]:
                    fx, fy = self.tx[p], self._tank_y(p)
                    if math.hypot(fx - self.exp["x"], fy - self.exp["y"]) <= holeR + 22:
                        self.shield[p] = None
        self.exp["frame"] += 1
        if self.exp["frame"] >= EXP_TOTAL:
            self.exp = None
            self.phase = SETTLE
            self._settle_frames = 0

    def _tick_settle(self):
        moved = self._gravity_pass()
        moved = self._gravity_pass() or moved
        self._settle_frames += 1
        self.tvers += 1
        if not moved or self._settle_frames > 200:
            self._grid_to_heightmap()
            self._build_grid()
            self._switch()

    def _step(self):
        if self.phase == AIM:
            self._handle_aim(self.active)
        elif self.phase == FLY:
            self._tick_fly()
        elif self.phase == EXPLODE:
            self._tick_explode()
        elif self.phase == SETTLE:
            self._tick_settle()
        elif self.phase == ROUNDWAIT:
            self._wait += 1
            if self._wait >= ROUNDWAIT_TICKS:
                self._init_round()

    def snapshot(self, view=None):
        holeR = WEAPONS[self.exp["w"]][1] if self.exp else 0
        snap = {
            "g": self.gid,
            "tv": self.tvers,
            "tx": [self.tx[1], self.tx[2]],
            "ty": [self._tank_y(1), self._tank_y(2)],
            "hp": [round(self.hp[1]), round(self.hp[2])],
            "wins": [self.wins1, self.wins2],
            "act": self.active, "ph": self.phase, "wind": self.wind,
            "ang": [self.angleP[1], self.angleP[2]],
            "pow": [self.powerP[1], self.powerP[2]],
            "sel": [self.sel[1], self.sel[2]],
            "ammo": [self._cur_ammo(1), self._cur_ammo(2)],
            "wn": [WEAPONS[self.sel[1]][0], WEAPONS[self.sel[2]][0]],
            "prj": None if not self.prj else [round(self.prj["x"], 1), round(self.prj["y"], 1), self.prj["owner"]],
            "exp": None if not self.exp else [self.exp["x"], self.exp["y"], holeR, self.exp["frame"], self.exp["col"]],
            "sh": [sorted(self.shield[1]) if self.shield[1] else None,
                   sorted(self.shield[2]) if self.shield[2] else None],
            "rw": self.round_winner if self.phase == ROUNDWAIT else -1,
            "maxhp": MAX_HP, "need": WINS_NEEDED,
        }
        # Gitter nur senden, wenn es sich geaendert hat (Client cached per tv).
        if self.tvers != self._grid_snap_tvers:
            snap["grid"] = self._encode_grid()
            self._grid_snap_tvers = self.tvers
        return snap

    def console_stat(self):
        return f"HP {round(self.hp[1])}/{round(self.hp[2])} W{self.wins1}:{self.wins2}"
