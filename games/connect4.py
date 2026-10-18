"""Quadlink / Vier gewinnt. 7x6, Einzelpartie."""
from .base import Game, LEFT, RIGHT, BTN_A, BTN_B

NX, NY = 7, 6
OX, OY, CW, CH, PR = 13, 50, 30, 35, 12


class Connect4(Game):
    gid = "c4"
    name = "Quadlink"
    tick_ms = 50

    def __init__(self):
        super().__init__()
        self.board = [[0] * NY for _ in range(NX)]
        self.cur = 3
        self.player = 1
        self.status = 0
        self.last = [-1, -1]

    def _move_cursor(self, d):
        c = self.cur
        for _ in range(NX):
            c = (c + d) % NX
            if self.board[c][0] == 0:
                self.cur = c
                return

    def _drop(self, col):
        if self.board[col][0] != 0:
            return
        row = NY - 1
        while row >= 0 and self.board[col][row] != 0:
            row -= 1
        if row < 0:
            return
        self.board[col][row] = self.player
        self.last = [col, row]
        if self._win_at(col, row):
            self.status = self.player
            self.finish("p1" if self.player == 1 else "p2")
        elif all(self.board[c][0] != 0 for c in range(NX)):
            self.status = 3
            self.finish("draw")
        else:
            self.player = 2 if self.player == 1 else 1

    def _win_at(self, col, row):
        p = self.board[col][row]
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            cnt = 1
            for s in (1, -1):
                for k in range(1, 4):
                    c = col + dx * k * s
                    r = row + dy * k * s
                    if 0 <= c < NX and 0 <= r < NY and self.board[c][r] == p:
                        cnt += 1
                    else:
                        break
            if cnt >= 4:
                return True
        return False

    def _step(self):
        if self.status != 0:
            return
        e = self.edge(self.player)
        if e & LEFT:
            self._move_cursor(-1)
        if e & RIGHT:
            self._move_cursor(1)
        if e & (BTN_A | BTN_B):
            self._drop(self.cur)

    def snapshot(self, view=None):
        return {
            "g": self.gid,
            "board": self.board,
            "cur": self.cur,
            "pl": self.player,
            "st": self.status,
            "last": self.last,
            "geo": [NX, NY, OX, OY, CW, CH, PR],
        }

    def console_stat(self):
        filled = sum(1 for c in range(NX) for r in range(NY) if self.board[c][r])
        return f"P{self.player} {filled}/42"
