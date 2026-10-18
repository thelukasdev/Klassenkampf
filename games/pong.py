"""Tennis42 / PONG. Erster mit 7 Punkten gewinnt.

Sim-Koordinaten: P1 = oberes Paddle (y=38), P2 = unteres Paddle (y=262).
Der Client spiegelt je nach Perspektive (eigenes Paddle unten).
"""
import math
import random

from .base import Game, LEFT, RIGHT

PW, PH, BR = 44, 6, 4
TY, BY = 30, 276
P1Y, P2Y = 38, 262
WIN = 5
START, MAXV, DEFL = 4.0, 9.0, 2.4
XMIN, XMAX = 4, 240 - 4 - PW  # [4, 192]
COUNTDOWN_TICKS = 72  # ~1.8 s bei 25 ms/Tick
COUNTDOWN_PER = 24    # Ticks je Ziffer -> zeigt 3, 2, 1


class Pong(Game):
    gid = "pong"
    name = "Tennis42"
    tick_ms = 25

    def __init__(self):
        super().__init__()
        self.s1 = 0
        self.s2 = 0
        self.status = 4        # 0 im Spiel, 4 Countdown, 1 P1 Sieg, 2 P2 Sieg
        self.last_scorer = 1
        self._cd = COUNTDOWN_TICKS
        self._center_paddles()
        self._reset_ball(1 if random.random() < 0.5 else -1)

    def _center_paddles(self):
        self.p1x = (240 - PW) // 2
        self.p2x = self.p1x

    def _serve(self, direction):
        """Neuer Aufschlag: Countdown starten, Paddles mittig, Ball zentriert."""
        self.status = 4
        self._cd = COUNTDOWN_TICKS
        self._center_paddles()
        self._reset_ball(direction)

    def _reset_ball(self, direction):
        self.bx = 120.0
        self.by = (TY + BY) / 2.0
        a = random.randint(-30, 30) * 0.0174533
        self.bvx = math.sin(a) * START
        self.bvy = (1 if direction >= 0 else -1) * math.cos(a) * START

    def _paddle(self, p):
        m = self.mask(p)
        x = self.p1x if p == 1 else self.p2x
        if m & LEFT:
            x -= 4
        if m & RIGHT:
            x += 4
        x = max(XMIN, min(XMAX, x))
        if p == 1:
            self.p1x = x
        else:
            self.p2x = x

    def _bounce(self, px):
        r = ((self.bx - px) - PW / 2) / (PW / 2)
        self.bvx = r * DEFL
        spd = math.hypot(self.bvx, self.bvy)
        if spd > 0:
            ns = min(spd * 1.05, MAXV)
            k = ns / spd
            self.bvx *= k
            self.bvy *= k

    def _step(self):
        self._paddle(1)
        self._paddle(2)

        if self.status == 4:            # Countdown vor dem Aufschlag
            self._cd -= 1
            if self._cd <= 0:
                self.status = 0
            return

        if self.status != 0:
            return

        for _ in range(4):
            self.bx += self.bvx / 4
            self.by += self.bvy / 4
            if self.bx < 5:
                self.bx = 5
                self.bvx = -self.bvx
            elif self.bx > 235:
                self.bx = 235
                self.bvx = -self.bvx

            # Oberes Paddle (P1)
            if self.bvy < 0 and 34 <= (self.by - BR) <= 44 and self.p1x <= self.bx <= self.p1x + PW:
                self.by = 49
                self.bvy = -self.bvy
                self._bounce(self.p1x)
            # Unteres Paddle (P2)
            elif self.bvy > 0 and 262 <= (self.by + BR) <= 272 and self.p2x <= self.bx <= self.p2x + PW:
                self.by = 257
                self.bvy = -self.bvy
                self._bounce(self.p2x)

            if self.by < TY:            # Ball oben raus -> P2 punktet
                self.s2 += 1
                self.last_scorer = 2
                if self.s2 >= WIN:
                    self.status = 2
                    self.finish("p2")
                else:
                    self._serve(-1)     # Aufschlag zum Verlierer (P1, oben)
                break
            if self.by > BY:            # Ball unten raus -> P1 punktet
                self.s1 += 1
                self.last_scorer = 1
                if self.s1 >= WIN:
                    self.status = 1
                    self.finish("p1")
                else:
                    self._serve(1)      # Aufschlag zum Verlierer (P2, unten)
                break

    def snapshot(self, view=None):
        cd = (self._cd - 1) // COUNTDOWN_PER + 1 if self.status == 4 else 0
        return {
            "g": self.gid,
            "p1x": round(self.p1x), "p2x": round(self.p2x),
            "bx": round(self.bx, 1), "by": round(self.by, 1),
            "s1": self.s1, "s2": self.s2, "st": self.status,
            "cd": cd,
            "pw": PW, "ph": PH, "br": BR,
            "p1y": P1Y, "p2y": P2Y, "win": WIN,
        }

    def console_stat(self):
        return f"{self.s1}:{self.s2}"
