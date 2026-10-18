"""W'n'R / MERKEN: kompetitives 2-Spieler-Simon.

Beide Spieler teilen sich eine wachsende Richtungs-Sequenz. Der aktive Spieler
schaut die Sequenz, gibt sie fehlerfrei wieder und haengt eine neue Richtung an.
Ein Fehler in der Wiedergabe -> sofort verloren. Laenge 100 erreicht -> Remis.
Nur der aktive Spieler (und Zuschauer) sehen das Abspielen.
"""
from .base import Game, LEFT, RIGHT, UP, DOWN

# Richtungscodes
D_UP, D_DOWN, D_LEFT, D_RIGHT = 0, 1, 2, 3
MAX_SEQ = 100
PRE_DELAY = 600
FLASH_ON = 400
STEP = 600

# Phasen (wie Original)
INTRO, WATCH, REPLAY, EXTEND, P1_WINS, P2_WINS, DRAW = 0, 1, 2, 3, 4, 5, 6


class WnR(Game):
    gid = "wnr"
    name = "W'n'R"
    tick_ms = 33
    per_view = True   # aktives Abspielen nur fuer den aktiven Spieler sichtbar

    def __init__(self):
        super().__init__()
        self.seq = []
        self.active = 1
        self.progress = 0
        self.clock = 0
        self.phase_t = 0
        self.block_until = 0
        self.flash_dir = -1
        self.flash_until = 0
        self.done_at = None
        self.ext_added = False
        self.watch_flash = -1
        self._start_extend()   # P1 legt die erste Richtung fest

    def _edge_dir(self, p):
        e = self.edge(p)
        for bit, d in ((UP, D_UP), (DOWN, D_DOWN), (LEFT, D_LEFT), (RIGHT, D_RIGHT)):
            if e & bit:
                return d
        return None

    def _start_watch(self):
        if len(self.seq) == 0:
            self._start_extend()
            return
        self.phase = WATCH
        self.phase_t = 0
        self.watch_flash = -1

    def _watch(self):
        self.phase_t += self.tick_ms
        el = self.phase_t
        if el < PRE_DELAY:
            self.watch_flash = -1
            return
        step = (el - PRE_DELAY) // STEP
        if step >= len(self.seq):
            self.watch_flash = -1
            self._start_replay()
            return
        local = (el - PRE_DELAY) % STEP
        self.watch_flash = self.seq[step] if local < FLASH_ON else -1

    def _start_replay(self):
        self.phase = REPLAY
        self.progress = 0
        self.block_until = self.clock + 500
        self.done_at = None
        self.flash_until = 0

    def _replay(self):
        if self.done_at is not None:
            if self.clock >= self.done_at:
                self._start_extend()
            return
        if self.clock < self.block_until:
            return
        d = self._edge_dir(self.active)
        if d is None:
            return
        if d == self.seq[self.progress]:
            self.flash_dir = d
            self.flash_until = self.clock + 280
            self.progress += 1
            self.block_until = self.clock + 250
            if self.progress >= len(self.seq):
                self.done_at = self.clock + 350
        else:
            if self.active == 1:
                self.phase = P2_WINS
                self.finish("p2")
            else:
                self.phase = P1_WINS
                self.finish("p1")

    def _start_extend(self):
        self.phase = EXTEND
        self.block_until = self.clock + 600
        self.ext_added = False
        self.done_at = None

    def _extend(self):
        if self.ext_added:
            if self.clock >= self.done_at:
                self._next_turn()
            return
        if self.clock < self.block_until:
            return
        d = self._edge_dir(self.active)
        if d is None:
            return
        self.seq.append(d)
        self.flash_dir = d
        self.flash_until = self.clock + 280
        if len(self.seq) >= MAX_SEQ:
            self.phase = DRAW
            self.finish("draw")
            return
        self.ext_added = True
        self.done_at = self.clock + 380

    def _next_turn(self):
        self.active = 2 if self.active == 1 else 1
        self._start_watch()

    def _step(self):
        self.clock += self.tick_ms
        if self.phase == WATCH:
            self._watch()
        elif self.phase == REPLAY:
            self._replay()
        elif self.phase == EXTEND:
            self._extend()

    def snapshot(self, view=None):
        # Abspielen/Feedback nur fuer aktiven Spieler und Zuschauer sichtbar.
        show = (view != (2 if self.active == 1 else 1))
        flash = -1
        if show:
            if self.phase == WATCH:
                flash = self.watch_flash
            elif self.clock < self.flash_until:
                flash = self.flash_dir
        invite = (show and self.phase == EXTEND and not self.ext_added
                  and self.clock >= self.block_until and (self.clock // 200) % 2 == 0)
        return {
            "g": self.gid,
            "ph": self.phase,
            "len": len(self.seq),
            "prog": self.progress,
            "act": self.active,
            "flash": flash,
            "invite": invite,
            "yourturn": (view == self.active),
        }

    def console_stat(self):
        return f"L{len(self.seq)} P{self.active}"
