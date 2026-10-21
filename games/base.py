"""Gemeinsame Basis fuer alle serverseitigen Spiel-Engines.

Der Server ist autoritativ: jede Engine simuliert einen 2-Spieler-Match,
bekommt pro Spieler eine Eingabe-Bitmaske und liefert Snapshots fuers Rendern.

Einheitliche Eingabe-Bitmaske (client -> server):
    LEFT=1, RIGHT=2, UP=4, DOWN=8, A=16, B=32

Pro Spieler halten wir:
    mask  -- aktuell gehaltene Tasten (Level)
    edge  -- steigende Flanken seit dem letzten Tick (werden nach tick() geleert)
"""

LEFT = 1
RIGHT = 2
UP = 4
DOWN = 8
BTN_A = 16
BTN_B = 32

# Farbpalette aus dem Original (RGB565 -> RGB888), zentral fuer Client & Referenz.
COL = {
    "BG": "#000000",
    "FRAME": "#181C18",
    "P1": "#73D363",   # gruen
    "P2": "#FFA600",   # orange
    "HEAD": "#FFFFFF",
    "TEXT": "#FFFFFF",
    "DIM": "#7B7D7B",
    "BALL": "#FFFF00",
    "SHOT_P1": "#94EB84",
    "SHOT_P2": "#FFCB00",
    "TRACK": "#424142",
    "GRASS": "#006500",
    "SHOCK": "#CE82FF",
    "SHIELD": "#FFFF00",
}


class Game:
    """Basisklasse. Spieler 1 = Herausforderer (Host), Spieler 2 = Gegner (Guest)."""

    gid = "base"
    name = "Base"
    tick_ms = 33
    # Aufloesung des Original-Displays; Clients skalieren darauf.
    W = 240
    H = 280
    # True: snapshot() haengt von der Perspektive ab (z.B. W'n'R). Sonst wird
    # pro Tick nur EIN Snapshot gebaut und an alle Spieler geschickt.
    per_view = False
    # Hoechstzahl Spieler (Herausforderer + bis zu max_players-1 Gegner)
    min_players = 2
    max_players = 2

    def __init__(self, n=2):
        self.n = n                           # Spieler 1..n
        # inp[p] = {"mask": int, "edge": int}  fuer p in 1..n
        self.inp = {p: {"mask": 0, "edge": 0} for p in range(1, n + 1)}
        self._result = None  # None | "p1" .. "pN" | "draw"
        self.frame = 0

    # ----- Eingabe -----
    def set_input(self, player, mask):
        """Neue gehaltene Maske eines Spielers uebernehmen, Flanken akkumulieren."""
        st = self.inp[player]
        edges = mask & ~st["mask"]
        st["mask"] = mask
        st["edge"] |= edges

    def reset_inputs(self):
        for st in self.inp.values():st["mask"]=st["edge"]=0

    def _clear_edges(self):
        for st in self.inp.values():
            st["edge"] = 0

    def mask(self, p):
        return self.inp[p]["mask"]

    def edge(self, p):
        return self.inp[p]["edge"]

    # ----- Simulation -----
    def tick(self):
        """Einen Simulationsschritt ausfuehren. Unterklassen ueberschreiben _step()."""
        self.frame += 1
        self._step()
        self._clear_edges()

    def _step(self):
        raise NotImplementedError

    def remove_player(self, p):
        """Spieler p hat das Spiel verlassen (nur Mehrspieler-Spiele mit >2
        Spielern): ausscheiden lassen, die anderen spielen weiter."""

    # ----- Ergebnis -----
    @property
    def result(self):
        """None solange laeuft, sonst 'p1' .. 'pN' | 'draw'."""
        return self._result

    def finish(self, who):
        if self._result is None:
            self._result = who

    # ----- Serialisierung -----
    def snapshot(self):
        """Absoluter Zustand fuers Rendern (dict, JSON-serialisierbar)."""
        raise NotImplementedError

    def console_stat(self):
        """Kurzer Text fuer das Konsolen-Dashboard, z.B. '3:2'."""
        return ""
