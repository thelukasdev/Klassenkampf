"""Jump'n'Bump. Wer den anderen von oben zerquetscht, bekommt einen
Punkt; erster mit 5 Punkten gewinnt.

Mechanik 1:1 aus der PicoBoy-Duo-Fassung (pbusb/jumpnbump/src/game.cpp), die
sie wiederum aus main.c des Originals hat: Festkomma 16.16, 60-Hz-Takt, Eis,
Wasser mit Auftrieb, Sprungfeder, Zerquetschen, seitliches Abprallen, Fell und
Fleisch mit Blutspur und dauerhaften Blutflecken, Fliegenschwarm, Falter.
Der Server rechnet alles (auch das Schmueckende) und schickt pro Netz-Tick
zwei 60-Hz-Schritte.

Jump 'n Bump (c) 1998 Brainchild Design, GPL2+.
"""
import math
import random

from .base import Game, LEFT, RIGHT, UP, BTN_A, BTN_B

WIN = 5
SUBSTEPS = 2            # 60-Hz-Schritte je Netz-Tick (33 ms)
END_DELAY = 100         # Schritte (~1,7 s) Ergebnisanzeige vor Match-Ende
NUM_OBJECTS = 200
NUM_FLIES = 20
MAX_STAINS = 400

BAN_VOID, BAN_SOLID, BAN_WATER, BAN_ICE, BAN_SPRING = 0, 1, 2, 3, 4

OBJ_SPRING, OBJ_SPLASH, OBJ_SMOKE, OBJ_YEL_BUTFLY, OBJ_PINK_BUTFLY = 0, 1, 2, 3, 4
OBJ_FUR, OBJ_FLESH, OBJ_FLESH_TRACE = 5, 6, 7

OBJ_ANIM_SPRING, OBJ_ANIM_SPLASH, OBJ_ANIM_SMOKE = 0, 1, 2
OBJ_ANIM_YEL_BUTFLY_RIGHT, OBJ_ANIM_YEL_BUTFLY_LEFT = 3, 4
OBJ_ANIM_PINK_BUTFLY_RIGHT, OBJ_ANIM_PINK_BUTFLY_LEFT = 5, 6
OBJ_ANIM_FLESH_TRACE = 7

# Kachelkarte (levelmap.txt des Originals), Kachel = 16x16 Pixel.
# Zeile 16 liegt unter dem sichtbaren Level (fester Boden).
BAN_MAP = [
    [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0],
    [1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1],
    [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
    [1, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
    [2, 2, 2, 2, 2, 2, 2, 2, 1, 4, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]

# Animationen der Hasen: stehen, laufen, springen, fallen, ins Wasser,
# schwimmen, sterben. [num_frames, restart, (image, ticks) * n]
PLAYER_ANIM = [
    [1, 0, 0, 0x7fff, 0, 0, 0, 0, 0, 0],
    [4, 0, 0, 4, 1, 4, 2, 4, 3, 4],
    [1, 0, 4, 0x7fff, 0, 0, 0, 0, 0, 0],
    [4, 2, 5, 8, 6, 10, 7, 3, 6, 3],
    [1, 0, 6, 0x7fff, 0, 0, 0, 0, 0, 0],
    [2, 1, 5, 8, 4, 0x7fff, 0, 0, 0, 0],
    [1, 0, 8, 5, 0, 0, 0, 0, 0, 0],
]

# Objektanimationen: (num_frames, restart_frame, [(image, ticks), ...])
OBJ_ANIMS = [
    (6, 0, [(0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3)]),
    (9, 0, [(6, 2), (7, 2), (8, 2), (9, 2), (10, 2), (11, 2), (12, 2), (13, 2), (14, 2)]),
    (5, 0, [(15, 3), (16, 3), (16, 3), (17, 3), (18, 3), (19, 3)]),
    (10, 0, [(20, 2), (21, 2), (22, 2), (23, 2), (24, 2), (25, 2), (24, 2), (23, 2), (22, 2), (21, 2)]),
    (10, 0, [(26, 2), (27, 2), (28, 2), (29, 2), (30, 2), (31, 2), (30, 2), (29, 2), (28, 2), (27, 2)]),
    (10, 0, [(32, 2), (33, 2), (34, 2), (35, 2), (36, 2), (37, 2), (36, 2), (35, 2), (34, 2), (33, 2)]),
    (10, 0, [(38, 2), (39, 2), (40, 2), (41, 2), (42, 2), (43, 2), (42, 2), (41, 2), (40, 2), (39, 2)]),
    (4, 0, [(76, 4), (77, 4), (78, 4), (79, 4)]),
]


def ban(x, y):
    """GET_BAN_MAP_XY mit Bereichsschutz (oben Himmel, unten fester Boden)."""
    tx, ty = x >> 4, y >> 4
    if ty < 0:
        return BAN_VOID
    if ty > 16:
        ty = 16
    if tx < 0:
        tx = 0
    if tx > 21:
        tx = 21
    return BAN_MAP[ty][tx]


def in_water(s1, s2):
    return ((ban(s1, s2 + 7) == BAN_VOID or ban(s1 + 15, s2 + 7) == BAN_VOID) and
            (ban(s1, s2 + 8) == BAN_WATER or ban(s1 + 15, s2 + 8) == BAN_WATER))


def rnd(n):
    return random.randrange(n) if n > 0 else 0


class _Player:
    __slots__ = ("action_left", "action_up", "action_right", "enabled", "dead_flag",
                 "bumps", "x", "y", "x_add", "y_add", "direction", "jump_ready",
                 "jump_abort", "in_water", "anim", "frame", "frame_tick", "image")

    def __init__(self):
        for k in self.__slots__:
            setattr(self, k, 0)


class _Obj:
    __slots__ = ("used", "type", "x", "y", "x_add", "y_add", "x_acc", "y_acc",
                 "anim", "frame", "ticks", "image")

    def __init__(self):
        self.used = 0


SOLIDISH3 = (BAN_SOLID, BAN_ICE, BAN_SPRING)


class JumpNBump(Game):
    gid = "jnb"
    name = "Jump'n'Bump"
    tick_ms = 33
    max_players = 4

    def __init__(self, n=2):
        super().__init__(n)
        self.pl = [_Player() for _ in range(n)]
        self.objects = [_Obj() for _ in range(NUM_OBJECTS)]
        self.flies = [[0, 0] for _ in range(NUM_FLIES)]
        self.stains = []          # dauerhafte Blutflecken (Levelpixel)
        self.status = 0           # 0 laeuft, sonst Sieger 1..n
        self._end = 0
        self._init_level()

    # ------------------------------------------------------------ Hilfen
    def _set_anim(self, p, a):
        p.anim = a
        p.frame = 0
        p.frame_tick = 0
        p.image = PLAYER_ANIM[a][2] + p.direction * 9

    def add_object(self, typ, x, y, x_add, y_add, anim, frame):
        for o in self.objects:
            if not o.used:
                o.used = 1
                o.type = typ
                o.x = x << 16
                o.y = y << 16
                o.x_add = x_add
                o.y_add = y_add
                o.x_acc = 0
                o.y_acc = 0
                o.anim = anim
                o.frame = frame
                n, _r, fr = OBJ_ANIMS[anim]
                if frame < n:
                    o.image, o.ticks = fr[frame]
                else:              # Fell/Fleisch: Bildnummer steht in frame
                    o.ticks = 1
                    o.image = frame
                return

    def _smoke(self, p):
        self.add_object(OBJ_SMOKE, (p.x >> 16) + 2 + rnd(9), (p.y >> 16) + 13 + rnd(5),
                        0, -16384 - rnd(8192), OBJ_ANIM_SMOKE, 0)

    # ------------------------------------------------------------ Laufen
    def _action_left(self, p):
        s1, s2 = p.x >> 16, p.y >> 16
        below_left = ban(s1, s2 + 16)
        below = ban(s1 + 8, s2 + 16)
        below_right = ban(s1 + 15, s2 + 16)
        if below == BAN_ICE:
            p.x_add -= 1024 if p.x_add > 0 else 768
        elif ((below_left != BAN_SOLID and below_right == BAN_ICE) or
              (below_left == BAN_ICE and below_right != BAN_SOLID)):
            p.x_add -= 1024 if p.x_add > 0 else 768
        else:
            if p.x_add > 0:
                p.x_add -= 16384
                if p.x_add > -98304 and p.in_water == 0 and below == BAN_SOLID:
                    self._smoke(p)
            else:
                p.x_add -= 12288
        if p.x_add < -98304:
            p.x_add = -98304
        p.direction = 1
        if p.anim == 0:
            self._set_anim(p, 1)

    def _action_right(self, p):
        s1, s2 = p.x >> 16, p.y >> 16
        below_left = ban(s1, s2 + 16)
        below = ban(s1 + 8, s2 + 16)
        below_right = ban(s1 + 15, s2 + 16)
        if below == BAN_ICE:
            p.x_add += 1024 if p.x_add < 0 else 768
        elif ((below_left != BAN_SOLID and below_right == BAN_ICE) or
              (below_left == BAN_ICE and below_right != BAN_SOLID)):
            p.x_add += 1024 if p.x_add > 0 else 768
        else:
            if p.x_add < 0:
                p.x_add += 16384
                if p.x_add < 98304 and p.in_water == 0 and below == BAN_SOLID:
                    self._smoke(p)
            else:
                p.x_add += 12288
        if p.x_add > 98304:
            p.x_add = 98304
        p.direction = 0
        if p.anim == 0:
            self._set_anim(p, 1)

    # ------------------------------------------------------------ Spieler
    def _steer(self):
        for idx, p in enumerate(self.pl):
            if p.enabled != 1:
                continue
            if p.dead_flag == 0:
                if p.action_left and p.action_right:
                    if p.direction == 0:
                        self._action_right(p)
                    else:
                        self._action_left(p)
                elif p.action_left:
                    self._action_left(p)
                elif p.action_right:
                    self._action_right(p)
                else:
                    s1, s2 = p.x >> 16, p.y >> 16
                    below_left = ban(s1, s2 + 16)
                    below = ban(s1 + 8, s2 + 16)
                    below_right = ban(s1 + 15, s2 + 16)
                    if (below in (BAN_SOLID, BAN_SPRING) or
                            ((below_left in (BAN_SOLID, BAN_SPRING) and below_right != BAN_ICE) or
                             (below_left != BAN_ICE and below_right in (BAN_SOLID, BAN_SPRING)))):
                        if p.x_add < 0:
                            p.x_add += 16384
                            if p.x_add > 0:
                                p.x_add = 0
                        else:
                            p.x_add -= 16384
                            if p.x_add < 0:
                                p.x_add = 0
                        if p.x_add != 0 and ban(s1 + 8, s2 + 16) == BAN_SOLID:
                            self._smoke(p)
                    if p.anim == 1:
                        self._set_anim(p, 0)

                # Springen
                if p.jump_ready == 1 and p.action_up:
                    s1, s2 = p.x >> 16, p.y >> 16
                    if s2 < -16:
                        s2 = -16
                    if (ban(s1, s2 + 16) in (BAN_SOLID, BAN_ICE) or
                            ban(s1 + 15, s2 + 16) in (BAN_SOLID, BAN_ICE)):
                        p.y_add = -280000
                        self._set_anim(p, 2)
                        p.jump_ready = 0
                        p.jump_abort = 1
                    if in_water(s1, s2):          # Sprung aus dem Wasser
                        p.y_add = -196608
                        p.in_water = 0
                        self._set_anim(p, 2)
                        p.jump_ready = 0
                        p.jump_abort = 1
                # Sprungtaste losgelassen -> Sprung abbrechen
                if not p.action_up:
                    p.jump_ready = 1
                    if p.in_water == 0 and p.y_add < 0 and p.jump_abort == 1:
                        p.y_add += 32768
                        if p.y_add > 0:
                            p.y_add = 0

                p.x += p.x_add
                if (p.x >> 16) < 0:
                    p.x = 0
                    p.x_add = 0
                if (p.x >> 16) + 15 > 351:
                    p.x = 336 << 16
                    p.x_add = 0
                s2 = (p.y >> 16) if p.y > 0 else 0
                s1 = p.x >> 16
                if ban(s1, s2) in SOLIDISH3 or ban(s1, s2 + 15) in SOLIDISH3:
                    p.x = ((s1 + 16) & 0xfff0) << 16
                    p.x_add = 0
                s1 = p.x >> 16
                if ban(s1 + 15, s2) in SOLIDISH3 or ban(s1 + 15, s2 + 15) in SOLIDISH3:
                    p.x = (((s1 + 16) & 0xfff0) - 16) << 16
                    p.x_add = 0

                p.y += p.y_add

                # Sprungfeder
                s1, s2 = p.x >> 16, max(0, p.y >> 16)
                if (ban(s1 + 8, s2 + 15) == BAN_SPRING or
                        ((ban(s1, s2 + 15) == BAN_SPRING and ban(s1 + 15, s2 + 15) != BAN_SOLID) or
                         (ban(s1, s2 + 15) != BAN_SOLID and ban(s1 + 15, s2 + 15) == BAN_SPRING))):
                    p.y = ((p.y >> 16) & 0xfff0) << 16
                    p.y_add = -400000
                    self._set_anim(p, 2)
                    p.jump_ready = 0
                    p.jump_abort = 0
                    for o in self.objects:
                        if o.used and o.type == OBJ_SPRING:
                            if ban(s1 + 8, s2 + 15) == BAN_SPRING:
                                hit = (o.x >> 20) == ((s1 + 8) >> 4) and (o.y >> 20) == ((s2 + 15) >> 4)
                            elif ban(s1, s2 + 15) == BAN_SPRING:
                                hit = (o.x >> 20) == (s1 >> 4) and (o.y >> 20) == ((s2 + 15) >> 4)
                            elif ban(s1 + 15, s2 + 15) == BAN_SPRING:
                                hit = (o.x >> 20) == ((s1 + 15) >> 4) and (o.y >> 20) == ((s2 + 15) >> 4)
                            else:
                                hit = False
                            if hit:
                                o.frame = 0
                                o.image, o.ticks = OBJ_ANIMS[o.anim][2][0]
                                break

                # Decke
                s1, s2 = p.x >> 16, max(0, p.y >> 16)
                if ban(s1, s2) in SOLIDISH3 or ban(s1 + 15, s2) in SOLIDISH3:
                    p.y = ((s2 + 16) & 0xfff0) << 16
                    p.y_add = 0
                    self._set_anim(p, 0)

                # Wasser / Boden / freier Fall
                s1, s2 = p.x >> 16, max(0, p.y >> 16)
                if ban(s1 + 8, s2 + 8) == BAN_WATER:
                    if p.in_water == 0:
                        p.in_water = 1
                        self._set_anim(p, 4)
                        if p.y_add >= 32768:
                            self.add_object(OBJ_SPLASH, (p.x >> 16) + 8,
                                            ((p.y >> 16) & 0xfff0) + 15, 0, 0, OBJ_ANIM_SPLASH, 0)
                    p.y_add -= 1536           # langsam nach oben treiben
                    if p.y_add < 0 and p.anim != 5:
                        self._set_anim(p, 5)
                    if p.y_add < -65536:
                        p.y_add = -65536
                    if p.y_add > 65535:
                        p.y_add = 65535
                    if (ban(s1, s2 + 15) in (BAN_SOLID, BAN_ICE) or
                            ban(s1 + 15, s2 + 15) in (BAN_SOLID, BAN_ICE)):
                        p.y = (((s2 + 16) & 0xfff0) - 16) << 16
                        p.y_add = 0
                elif ban(s1, s2 + 15) in SOLIDISH3 or ban(s1 + 15, s2 + 15) in SOLIDISH3:
                    p.in_water = 0
                    p.y = (((s2 + 16) & 0xfff0) - 16) << 16
                    p.y_add = 0
                    if p.anim not in (0, 1):
                        self._set_anim(p, 0)
                else:
                    if p.in_water == 0:
                        p.y_add += 12288
                        if p.y_add > 327680:
                            p.y_add = 327680
                    else:
                        p.y = (p.y & ~0xFFFF) + 0x10000
                        p.y_add = 0
                    p.in_water = 0
                if p.y_add > 36864 and p.anim != 3 and p.in_water == 0:
                    self._set_anim(p, 3)

            # Animation weiterschalten
            a = PLAYER_ANIM[p.anim]
            p.frame_tick += 1
            if p.frame_tick >= a[p.frame * 2 + 3]:
                p.frame += 1
                if p.frame >= a[0]:
                    if p.anim != 6:
                        p.frame = a[1]
                    else:
                        self._position_player(idx)
                p.frame_tick = 0
            a = PLAYER_ANIM[p.anim]
            p.image = a[p.frame * 2 + 2] + p.direction * 9

    def _position_player(self, num):
        while True:
            while True:
                s1, s2 = rnd(22), rnd(16)
                if BAN_MAP[s2][s1] == BAN_VOID and BAN_MAP[s2 + 1][s1] in (BAN_SOLID, BAN_ICE):
                    break
            free = True
            for i, o in enumerate(self.pl):
                if i != num and o.enabled == 1:
                    if abs((s1 << 4) - (o.x >> 16)) < 32 and abs((s2 << 4) - (o.y >> 16)) < 32:
                        free = False
                        break
            if free:
                p = self.pl[num]
                p.x = s1 << 20
                p.y = s2 << 20
                p.x_add = p.y_add = 0
                p.direction = 0
                p.jump_ready = 1
                p.in_water = 0
                p.anim = 0
                p.frame = 0
                p.frame_tick = 0
                p.image = PLAYER_ANIM[0][2]
                p.dead_flag = 0
                return

    def _spawn_gore(self, victim, x, y):
        def piece(typ, frame):
            self.add_object(typ, (x >> 16) + 6 + rnd(5), (y >> 16) + 6 + rnd(5),
                            (rnd(65535) - 32768) * 3, (rnd(65535) - 32768) * 3, 0, frame)
        for _ in range(6):
            piece(OBJ_FUR, 44 + victim * 8)
        for frame, n in ((76, 6), (77, 6), (78, 8), (79, 10)):
            for _ in range(n):
                piece(OBJ_FLESH, frame)

    def _kill(self, c1, c2):
        a, b = self.pl[c1], self.pl[c2]
        a.y_add = -a.y_add
        if a.y_add > -262144:
            a.y_add = -262144
        a.jump_abort = 1
        b.dead_flag = 1
        if b.anim != 6:
            self._set_anim(b, 6)
            self._spawn_gore(c2, b.x, b.y)
            a.bumps += 1

    def _collision(self):
        # wie im Original: jedes Paar aktiver Hasen
        for c1 in range(self.n):
            for c2 in range(c1 + 1, self.n):
                if self.pl[c1].enabled == 1 and self.pl[c2].enabled == 1:
                    self._collide(c1, c2)

    def _collide(self, c1, c2):
        p1, p2 = self.pl[c1], self.pl[c2]
        if abs(p1.x - p2.x) < (12 << 16) and abs(p1.y - p2.y) < (12 << 16):
            if (abs(p1.y - p2.y) >> 16) > 5:
                # Der obere zerquetscht den unteren.
                if p1.y < p2.y:
                    if p1.y_add >= 0:
                        self._kill(c1, c2)
                    elif p2.y_add < 0:
                        p2.y_add = 0
                else:
                    if p2.y_add >= 0:
                        self._kill(c2, c1)
                    elif p1.y_add < 0:
                        p1.y_add = 0
            else:
                # Seitlicher Zusammenstoss: Impulstausch.
                if p1.x < p2.x:
                    if p1.x_add > 0:
                        p1.x = p2.x - (12 << 16)
                    elif p2.x_add < 0:
                        p2.x = p1.x + (12 << 16)
                    else:
                        p1.x -= p1.x_add
                        p2.x -= p2.x_add
                    p1.x_add, p2.x_add = p2.x_add, p1.x_add
                    if p1.x_add > 0:
                        p1.x_add = -p1.x_add
                    if p2.x_add < 0:
                        p2.x_add = -p2.x_add
                else:
                    if p1.x_add > 0:
                        p2.x = p1.x - (12 << 16)
                    elif p2.x_add < 0:
                        p1.x = p2.x + (12 << 16)
                    else:
                        p1.x -= p1.x_add
                        p2.x -= p2.x_add
                    p1.x_add, p2.x_add = p2.x_add, p1.x_add
                    if p1.x_add < 0:
                        p1.x_add = -p1.x_add
                    if p2.x_add > 0:
                        p2.x_add = -p2.x_add

    # ------------------------------------------------------------ Objekte
    def _anim_next(self, o, remove_at_end):
        o.ticks -= 1
        if o.ticks <= 0:
            o.frame += 1
            n, _r, fr = OBJ_ANIMS[o.anim]
            if o.frame >= n:
                if remove_at_end:
                    o.used = 0
                else:
                    o.frame -= 1
                    o.ticks = fr[o.frame][1]
            else:
                o.image, o.ticks = fr[o.frame]

    def _update_objects(self):
        for o in self.objects:
            if not o.used:
                continue
            t = o.type
            if t == OBJ_SPRING:
                self._anim_next(o, False)
            elif t in (OBJ_SPLASH, OBJ_FLESH_TRACE):
                self._anim_next(o, True)
            elif t == OBJ_SMOKE:
                o.x += o.x_add
                o.y += o.y_add
                self._anim_next(o, True)
            elif t in (OBJ_YEL_BUTFLY, OBJ_PINK_BUTFLY):
                self._butterfly(o)
            else:
                self._gore(o)

    def _butterfly(self, o):
        o.x_acc = max(-1024, min(1024, o.x_acc + rnd(128) - 64))
        o.x_add = max(-32768, min(32768, o.x_add + o.x_acc))
        o.x += o.x_add
        if (o.x >> 16) < 16:
            o.x = 16 << 16
            o.x_add = -o.x_add >> 2
            o.x_acc = 0
        elif (o.x >> 16) > 350:
            o.x = 350 << 16
            o.x_add = -o.x_add >> 2
            o.x_acc = 0
        if ban(o.x >> 16, o.y >> 16) != 0:
            if o.x_add < 0:
                o.x = (((o.x >> 16) + 16) & 0xfff0) << 16
            else:
                o.x = ((((o.x >> 16) - 16) & 0xfff0) + 15) << 16
            o.x_add = -o.x_add >> 2
            o.x_acc = 0
        o.y_acc = max(-1024, min(1024, o.y_acc + rnd(64) - 32))
        o.y_add = max(-32768, min(32768, o.y_add + o.y_acc))
        o.y += o.y_add
        if (o.y >> 16) < 0:
            o.y = 0
            o.y_add = -o.y_add >> 2
            o.y_acc = 0
        elif (o.y >> 16) > 255:
            o.y = 255 << 16
            o.y_add = -o.y_add >> 2
            o.y_acc = 0
        if ban(o.x >> 16, o.y >> 16) != 0:
            if o.y_add < 0:
                o.y = (((o.y >> 16) + 16) & 0xfff0) << 16
            else:
                o.y = ((((o.y >> 16) - 16) & 0xfff0) + 15) << 16
            o.y_add = -o.y_add >> 2
            o.y_acc = 0
        yel = o.type == OBJ_YEL_BUTFLY
        want_l = OBJ_ANIM_YEL_BUTFLY_LEFT if yel else OBJ_ANIM_PINK_BUTFLY_LEFT
        want_r = OBJ_ANIM_YEL_BUTFLY_RIGHT if yel else OBJ_ANIM_PINK_BUTFLY_RIGHT
        if (o.x_add < 0 and o.anim != want_l) or (o.x_add > 0 and o.anim != want_r):
            o.anim = want_l if o.x_add < 0 else want_r
            o.frame = 0
            o.image, o.ticks = OBJ_ANIMS[o.anim][2][0]
        o.ticks -= 1
        if o.ticks <= 0:
            o.frame += 1
            n, restart, fr = OBJ_ANIMS[o.anim]
            if o.frame >= n:
                o.frame = restart
            else:
                o.image, o.ticks = fr[o.frame]

    def _gore(self, o):
        is_flesh = o.type == OBJ_FLESH
        if rnd(100) < 30:                    # Blutspur
            if not is_flesh:
                self.add_object(OBJ_FLESH_TRACE, o.x >> 16, o.y >> 16, 0, 0, OBJ_ANIM_FLESH_TRACE, 0)
            elif 76 <= o.frame <= 78:
                self.add_object(OBJ_FLESH_TRACE, o.x >> 16, o.y >> 16, 0, 0,
                                OBJ_ANIM_FLESH_TRACE, o.frame - 75)
        tile = ban(o.x >> 16, o.y >> 16)
        if tile == 0:
            o.y_add += 3072
            if o.y_add > 196608:
                o.y_add = 196608
        elif tile == 2:                      # im Wasser abbremsen und absinken
            if o.x_add < 0:
                if o.x_add < -65536:
                    o.x_add = -65536
                o.x_add += 1024
                if o.x_add > 0:
                    o.x_add = 0
            else:
                if o.x_add > 65536:
                    o.x_add = 65536
                o.x_add -= 1024
                if o.x_add < 0:
                    o.x_add = 0
            o.y_add += 1024
            o.y_add = max(-65536, min(65536, o.y_add))
        o.x += o.x_add
        tile = ban(o.x >> 16, o.y >> 16)
        if (o.y >> 16) > 0 and tile in (1, 3):
            if o.x_add < 0:
                o.x = (((o.x >> 16) + 16) & 0xfff0) << 16
            else:
                o.x = ((((o.x >> 16) - 16) & 0xfff0) + 15) << 16
            o.x_add = -o.x_add >> 2
        o.y += o.y_add
        if (o.x >> 16) < -5 or (o.x >> 16) > 405 or (o.y >> 16) > 260:
            o.used = 0
        tile = ban(o.x >> 16, o.y >> 16)
        if o.used and (o.y >> 16) > 0 and tile != 0:
            if o.y_add < 0:
                if tile != 2:
                    o.y = (((o.y >> 16) + 16) & 0xfff0) << 16
                    o.x_add >>= 2
                    o.y_add = -o.y_add >> 2
            else:
                if tile == 1:
                    if o.y_add > 131072:
                        o.y = ((((o.y >> 16) - 16) & 0xfff0) + 15) << 16
                        o.x_add >>= 2
                        o.y_add = -o.y_add >> 2
                    else:
                        # Liegengebliebenes Fleisch wird zum dauerhaften Blutfleck.
                        if is_flesh and rnd(100) < 10 and len(self.stains) < MAX_STAINS:
                            s1 = rnd(4) - 2
                            self.stains.append((o.x >> 16, (o.y >> 16) + s1, o.frame))
                        o.used = 0
                elif tile == 3:
                    o.y = ((((o.y >> 16) - 16) & 0xfff0) + 15) << 16
                    o.y_add = (-o.y_add >> 2) if o.y_add > 131072 else 0
        if -16384 < o.x_add < 0:
            o.x_add = -16384
        if 0 < o.x_add < 16384:
            o.x_add = 16384

    # ------------------------------------------------------------ Fliegen
    def _update_flies(self):
        n = NUM_FLIES
        s1 = sum(f[0] for f in self.flies) // n
        s2 = sum(f[1] for f in self.flies) // n
        for f in self.flies:
            dist, cp = 0x7fff, self.pl[0]
            for p in self.pl:
                if p.enabled != 1:
                    continue
                dx = f[0] - ((p.x >> 16) + 8)
                dy = f[1] - ((p.y >> 16) + 8)
                cur = int(math.sqrt(dx * dx + dy * dy))
                if cur < dist:
                    dist, cp = cur, p
            s3 = 0
            if s1 - f[0] > 30:
                s3 += 1
            elif s1 - f[0] < -30:
                s3 -= 1
            if dist < 30:
                s3 += -1 if ((cp.x >> 16) + 8) > f[0] else 1
            s4 = rnd(3) - 1 + s3
            if f[0] + s4 < 16 or f[0] + s4 > 351 or ban(f[0] + s4, f[1]) != BAN_VOID:
                s4 = 0
            f[0] += s4
            s3 = 0
            if s2 - f[1] > 30:
                s3 += 1
            elif s2 - f[1] < -30:
                s3 -= 1
            if dist < 30:
                s3 += -1 if ((cp.y >> 16) + 8) > f[1] else 1
            s4 = rnd(3) - 1 + s3
            if f[1] + s4 < 0 or f[1] + s4 > 239 or ban(f[0], f[1] + s4) != BAN_VOID:
                s4 = 0
            f[1] += s4

    # ------------------------------------------------------------ Level
    def _init_level(self):
        for p in self.pl:
            p.enabled = 1
            p.jump_ready = 1
        for i in range(self.n):
            self._position_player(i)
        for ty in range(16):
            for tx in range(22):
                if BAN_MAP[ty][tx] == BAN_SPRING:
                    self.add_object(OBJ_SPRING, tx << 4, ty << 4, 0, 0, OBJ_ANIM_SPRING, 5)
        for n in range(4):
            typ = OBJ_YEL_BUTFLY if n < 2 else OBJ_PINK_BUTFLY
            while True:
                s1, s2 = rnd(22), rnd(16)
                if BAN_MAP[s2][s1] == BAN_VOID:
                    self.add_object(typ, (s1 << 4) + 8, (s2 << 4) + 8,
                                    (rnd(65535) - 32768) * 2, (rnd(65535) - 32768) * 2, 0, 0)
                    break
        s1, s2 = rnd(250) + 50, rnd(150) + 50
        for f in self.flies:
            while True:
                f[0] = s1 + rnd(101) - 50
                f[1] = s2 + rnd(101) - 50
                if 16 <= f[0] <= 351 and 0 <= f[1] <= 239 and ban(f[0], f[1]) == BAN_VOID:
                    break

    # ------------------------------------------------------------ Takt
    def _step(self):
        for k in range(SUBSTEPS):
            if self.status == 0:
                for i, p in enumerate(self.pl):
                    m = self.mask(i + 1)
                    p.action_left = 1 if m & LEFT else 0
                    p.action_right = 1 if m & RIGHT else 0
                    p.action_up = 1 if m & (UP | BTN_A | BTN_B) else 0
                self._steer()
                self._collision()
                for i, p in enumerate(self.pl):
                    if p.bumps >= WIN:
                        self.status = i + 1
                        break
            else:
                self._end += 1
                if self._end >= END_DELAY:
                    self.finish(f"p{self.status}")
            self._update_objects()
            self._update_flies()

    def snapshot(self, view=None):
        # Objekte als [typ, x, y, bildnummer] (Bild aus objects.pcx). Fell dreht
        # sich in Flugrichtung (8 Stufen) und kodiert das Opfer: 44 + opfer*8 + dreh.
        objs = []
        for o in self.objects:
            if not o.used:
                continue
            if o.type == OBJ_FUR:
                rot = int(math.atan2(o.y_add, o.x_add) * 4 / math.pi)
                if rot < 0:
                    rot += 8
                img = o.frame + max(0, min(7, rot))
            elif o.type == OBJ_FLESH:
                img = o.frame
            else:
                img = o.image
            objs += (o.type, o.x >> 16, o.y >> 16, img)
        flies = []
        for f in self.flies:
            flies += f
        stains = []
        for s in self.stains:
            stains += s
        return {
            "g": self.gid,
            "st": self.status,
            "b": [p.bumps for p in self.pl],
            "win": WIN,
            "p": [[p.x >> 16, p.y >> 16, p.image, p.enabled] for p in self.pl],
            "o": objs,
            "f": flies,
            "sx": stains,
        }

    def remove_player(self, p):
        self.pl[p - 1].enabled = 0
        left = [i for i, q in enumerate(self.pl) if q.enabled == 1]
        if len(left) == 1 and self.status == 0:
            self.finish(f"p{left[0] + 1}")

    def console_stat(self):
        return ":".join(str(p.bumps) for p in self.pl)
