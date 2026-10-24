"""Registry aller Spiele (Iso Invaders bewusst ausgelassen)."""
from .tron import Tron
from .pong import Pong
from .duel import Duel
from .tanks import Tanks
from .wnr import WnR
from .connect4 import Connect4
from .dots import Dots
from .bomber import Bomber
from .jnb import JumpNBump
from .sketch import Sketch

# Reihenfolge = Anzeigereihenfolge in der Lobby
GAME_CLASSES = [Tron, Pong, Duel, Tanks, WnR, Connect4, Dots, Bomber, JumpNBump, Sketch]
GAMES = {cls.gid: cls for cls in GAME_CLASSES}

DURATION = {'tron':'0,5–2 Min.','pong':'1–3 Min.','duel':'1–3 Min.','tanks':'2–5 Min.','wnr':'1–3 Min.','c4':'2–5 Min.','dots':'3–8 Min.','bomber':'1–3 Min.','jnb':'2–5 Min.','sketch':'4–9 Min.'}

GAME_INFO = [
    {"id": cls.gid, "name": cls.name, "tick_ms": cls.tick_ms, "max": cls.max_players, "min": cls.min_players, "preview": "/previews/"+cls.gid+".svg", "duration": DURATION[cls.gid]}
    for cls in GAME_CLASSES
]


def create(gid, n=2):
    cls = GAMES[gid]
    return cls(n) if cls.max_players > 2 else cls()
