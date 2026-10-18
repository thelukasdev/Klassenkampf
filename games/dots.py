"""Punkte & Striche / Dots and Boxes. 6x8 Punkte, Einzelpartie.
A = Orientierung wechseln (naechste senkrechte Linie), B = Linie ziehen.
Box schliessen -> nochmal am Zug."""
import math

from .base import Game, LEFT, RIGHT, UP, DOWN, BTN_A, BTN_B

NX, NY = 6, 8
OX, OY, CW, CH = 20, 44, 40, 31
NUM_H = (NX - 1) * NY   # 40
NUM_V = NX * (NY - 1)   # 42
NUM_LINES = NUM_H + NUM_V  # 82
NUM_BOX = (NX - 1) * (NY - 1)  # 35


def line_coords(idx):
    """-> (orient 'H'/'V', col, row)."""
    if idx < NUM_H:
        return "H", idx % (NX - 1), idx // (NX - 1)
    v = idx - NUM_H
    return "V", v % NX, v // NX


def line_center(idx):
    o, c, r = line_coords(idx)
    if o == "H":
        return OX + (c + 0.5) * CW, OY + r * CH
    return OX + c * CW, OY + (r + 0.5) * CH


class Dots(Game):
    gid = "dots"
    name = "Dots'n'Boxes"
    tick_ms = 50

    def __init__(self):
        super().__init__()
        self.linesH = [[False] * NY for _ in range(NX - 1)]
        self.linesV = [[False] * (NY - 1) for _ in range(NX)]
        self.boxes = [[0] * (NY - 1) for _ in range(NX - 1)]
        self.score1 = 0
        self.score2 = 0
        self.cursor = 0
        self.player = 1
        self.status = 0
        self._centers = [line_center(i) for i in range(NUM_LINES)]

    def _is_drawn(self, idx):
        o, c, r = line_coords(idx)
        return self.linesH[c][r] if o == "H" else self.linesV[c][r]

    def _set_drawn(self, idx):
        o, c, r = line_coords(idx)
        if o == "H":
            self.linesH[c][r] = True
        else:
            self.linesV[c][r] = True

    def _find_next(self, dx, dy):
        ccx, ccy = self._centers[self.cursor]
        best = None
        best_score = None
        for i in range(NUM_LINES):
            if i == self.cursor:
                continue
            ox, oy = self._centers[i]
            if dx != 0:
                if (ox - ccx) * dx <= 0:
                    continue
                major, minor = abs(ox - ccx), abs(oy - ccy)
            else:
                if (oy - ccy) * dy <= 0:
                    continue
                major, minor = abs(oy - ccy), abs(ox - ccx)
            sc = major + 3 * minor
            if best_score is None or sc < best_score:
                best_score = sc
                best = i
        if best is not None:
            self.cursor = best

    def _find_perp(self):
        curo = line_coords(self.cursor)[0]
        ccx, ccy = self._centers[self.cursor]
        best = None
        best_d = None
        for i in range(NUM_LINES):
            if line_coords(i)[0] == curo:
                continue
            ox, oy = self._centers[i]
            d = (ox - ccx) ** 2 + (oy - ccy) ** 2
            if best_d is None or d < best_d:
                best_d = d
                best = i
        if best is not None:
            self.cursor = best

    def _box_closed(self, c, r):
        return (self.linesH[c][r] and self.linesH[c][r + 1]
                and self.linesV[c][r] and self.linesV[c + 1][r])

    def _do_move(self, idx):
        if self._is_drawn(idx):
            return
        self._set_drawn(idx)
        o, c, r = line_coords(idx)
        closed = 0
        cands = []
        if o == "H":
            if r > 0:
                cands.append((c, r - 1))
            if r < NY - 1:
                cands.append((c, r))
        else:
            if c > 0:
                cands.append((c - 1, r))
            if c < NX - 1:
                cands.append((c, r))
        for bc, br in cands:
            if self.boxes[bc][br] == 0 and self._box_closed(bc, br):
                self.boxes[bc][br] = self.player
                closed += 1
        if closed:
            if self.player == 1:
                self.score1 += closed
            else:
                self.score2 += closed
        else:
            self.player = 2 if self.player == 1 else 1
        if self.score1 + self.score2 >= NUM_BOX:
            if self.score1 > self.score2:
                self.status = 1
                self.finish("p1")
            elif self.score2 > self.score1:
                self.status = 2
                self.finish("p2")
            else:
                self.status = 3
                self.finish("draw")

    def _step(self):
        if self.status != 0:
            return
        e = self.edge(self.player)
        if e & UP:
            self._find_next(0, -1)
        if e & DOWN:
            self._find_next(0, 1)
        if e & LEFT:
            self._find_next(-1, 0)
        if e & RIGHT:
            self._find_next(1, 0)
        if e & BTN_A:
            self._find_perp()
        if e & BTN_B:
            self._do_move(self.cursor)

    def snapshot(self, view=None):
        # Linien als flache Bit-Liste (Index==Linienindex).
        lines = [1 if self._is_drawn(i) else 0 for i in range(NUM_LINES)]
        return {
            "g": self.gid,
            "lines": lines,
            "boxes": self.boxes,
            "cur": self.cursor,
            "pl": self.player,
            "s1": self.score1, "s2": self.score2,
            "st": self.status,
            "geo": [NX, NY, OX, OY, CW, CH],
        }

    def console_stat(self):
        return f"{self.score1}:{self.score2} P{self.player}"
