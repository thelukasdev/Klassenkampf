"""Buntes Terminal-Dashboard mit Live-Stats aller laufenden Spiele."""
import asyncio
import shutil
import socket
import sys
import threading
import time

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
CLEAR = "\x1b[2J\x1b[H"
HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"

# Palette (RGB) passend zu den Spielen
C = {
    "P1": (115, 211, 99),
    "P2": (255, 166, 0),
    "TEXT": (235, 235, 235),
    "DIM": (123, 125, 123),
    "HEAD": (120, 230, 255),
    "OK": (115, 211, 99),
    "OFF": (90, 90, 90),
    "BUSY": (255, 166, 0),
    "ACCENT": (206, 130, 255),
    "BALL": (255, 235, 60),
    "P3": (79, 195, 255),
    "P4": (255, 95, 210),
}
PCOL = ["P1", "P2", "P3", "P4"]     # Spielerfarben nach Rolle


def fg(rgb):
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m"


def col(text, key):
    return f"{fg(C[key])}{text}{RESET}"


# Nur normale Textzeichen (keine Block-/Rahmengrafik): '#' als Pixel.
_FONT = {
    "K": ["#  #", "# # ", "##  ", "# # ", "#  #"],
    "L": ["#   ", "#   ", "#   ", "#   ", "####"],
    "A": [" ## ", "#  #", "####", "#  #", "#  #"],
    "S": [" ###", "#   ", " ## ", "   #", "### "],
    "E": ["####", "#   ", "### ", "#   ", "####"],
    "N": ["#  #", "## #", "# ##", "#  #", "#  #"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #"],
    "P": ["### ", "#  #", "### ", "#   ", "#   "],
    "F": ["####", "#   ", "### ", "#   ", "#   "],
}


def _make_banner(text):
    rows = ["", "", "", "", ""]
    for ch in text:
        g = _FONT[ch]
        for i in range(5):
            rows[i] += g[i] + " "
    return [" " + r for r in rows]


# 5x7-Ziffern fuer die Grossanzeige des Login-Codes
_DIGITS = {
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "# #  ", "  #  ", "  #  ", "  #  ", "#####"],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
}


def big_digits(text, sx, sy):
    """Ziffern als grosse '#'-Schrift: jedes Pixel sx Zeichen breit, sy Zeilen hoch."""
    rows = []
    for r in range(7):
        line = ""
        for ch in text:
            g = _DIGITS.get(ch, ["     "] * 7)
            line += "".join(("#" if c == "#" else " ") * sx for c in g[r]) + " " * (2 * sx)
        rows.extend([line.rstrip()] * sy)
    return rows


BANNER = _make_banner("KLASSENKAMPF")


class Dashboard:
    def __init__(self, server):
        self.server = server
        self.logs = []
        self.start = time.monotonic()
        self.paused = False   # waehrend das Admin-Menue aktiv ist
        self._url_cache = None

    def url(self):
        """Verbindungs-URL (LAN-IP + Port), einmalig ermittelt und gecached."""
        if self._url_cache is None:
            ip = "127.0.0.1"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
            except OSError:
                pass
            self._url_cache = f"http://{ip}:{self.server.port}/"
        return self._url_cache

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"{ts}  {msg}")
        self.logs = self.logs[-8:]

    async def run(self):
        # Das Bild wird hier gebaut, geschrieben wird es von einem eigenen
        # Thread: Haengt die Konsole (unter Windows langsam, oder angehalten
        # durch einen Klick ins Fenster), laufen die Spiele trotzdem weiter.
        self._frame = None
        self._wake = threading.Event()
        threading.Thread(target=self._writer, daemon=True).start()
        sys.stdout.write(HIDE)
        try:
            while True:
                if not self.paused:
                    self._frame = self.render()
                    self._wake.set()
                await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            sys.stdout.write(SHOW + RESET)
            raise

    def _writer(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            frame, self._frame = self._frame, None
            if frame and not self.paused:
                try:
                    sys.stdout.write(frame)
                    sys.stdout.flush()
                except (OSError, ValueError):
                    pass

    def render(self):
        """Ganzes Dashboard als ein String (geschrieben wird in _writer)."""
        w = max(72, shutil.get_terminal_size((100, 40)).columns)
        out = [CLEAR]

        # Banner
        for line in BANNER:
            out.append(fg(C["HEAD"]) + BOLD + line[:w] + RESET)
        online = sum(1 for p in self.server.players.values() if p.online)
        act = len(self.server.matches)
        up = int(time.monotonic() - self.start)
        # Verbindungs-Adresse prominent (mit Leerzeile darueber und darunter)
        out.append("")
        out.append("  " + fg(C["OK"]) + BOLD + "> Verbinden im Browser:  "
                   + fg(C["HEAD"]) + self.url() + RESET
                   + fg(C["DIM"]) + "   (Geraete im selben LAN, Login-Code im Menue)" + RESET)
        out.append("")
        sub = (f"  {col(str(online), 'OK')} online   "
               f"{col(str(len(self.server.players)), 'TEXT')} Spieler   "
               f"{col(str(act), 'BUSY')} aktive Spiele   "
               f"Uptime {up//3600:02d}:{(up%3600)//60:02d}:{up%60:02d}")
        out.append(sub)
        out.append(fg(C["DIM"]) + "-" * w + RESET)

        # Aktive Spiele (Live-Stats)
        out.append(col(" > LIVE-SPIELE", "ACCENT") + fg(C["DIM"]) + "  (Abbruch = Niederlage)" + RESET)
        if not self.server.matches:
            out.append(fg(C["DIM"]) + "   - keine laufenden Partien -" + RESET)
        else:
            for m in sorted(self.server.matches.values(), key=lambda x: x.id):
                names = []
                for i, p in enumerate(m.players):
                    n = (p.nick or "Spieler")[:12]
                    names.append(fg(C["OFF"]) + n + RESET if p in m.left else col(n, PCOL[i]))
                stat = m.game.console_stat()
                bar = self._match_stat_visual(m)
                line = (f"   {fg(C['HEAD'])}{m.name:<14}{RESET} "
                        + (fg(C['DIM']) + " vs " + RESET).join(names)
                        + f"   {fg(C['TEXT'])}{stat}{RESET}   {bar}")
                out.append(line)
        out.append(fg(C["DIM"]) + "-" * w + RESET)

        # Rangliste (beamer-tauglich)
        claimed = list(self.server.players.values())
        out.append(col(" > RANGLISTE (Credits)", "ACCENT")
                   + fg(C["DIM"]) + f"   {len(claimed)} Spieler" + RESET)
        if not claimed:
            out.append(fg(C["DIM"]) + "   - noch keine Spieler angemeldet (Login-Code: Menue -> Login-Code anzeigen) -" + RESET)
        else:
            header = f"   {'#':<4}{'Spieler':<18}{'Credits':>8}  {'S/N':>9}  Status"
            out.append(fg(C["DIM"]) + header + RESET)
            ranked = sorted(claimed, key=lambda p: (-p.credits, p.key))
            for i, p in enumerate(ranked, 1):
                wl = self._winloss(p)
                if p.busy:
                    st = col("im Spiel", "BUSY")
                elif p.online:
                    st = col("online", "OK")
                else:
                    st = fg(C["OFF"]) + "offline" + RESET
                cred = p.credits
                creds = (fg(C["P1"]) if cred > 0 else fg(C["P2"]) if cred < 0 else fg(C["DIM"]))
                rank = f"{i}."
                rc = C["P1"] if i == 1 and p.credits > 0 else C["DIM"]
                line = (f"   {fg(rc)}{rank:<4}{RESET}"
                        f"{fg(C['TEXT'])}{p.nick[:16]:<18}{RESET}"
                        f"{creds}{cred:>+8}{RESET}  "
                        f"{fg(C['DIM'])}{wl:>9}{RESET}  {st}")
                out.append(line)
        out.append(fg(C["DIM"]) + "-" * w + RESET)

        # Fusszeile: Menue-Hinweis
        out.append("")
        out.append(fg(C["ACCENT"]) + " [Enter]" + fg(C["DIM"]) + " Admin-Menue   "
                   + fg(C["ACCENT"]) + "[q]" + fg(C["DIM"]) + " Beenden" + RESET)

        return "\n".join(out) + "\n"

    def _winloss(self, p):
        w = sum(r[0] for r in p.record.values())
        l = sum(r[1] for r in p.record.values())
        return f"{w}/{l}"

    def _match_stat_visual(self, m):
        """Kleiner farbiger Balken je nach Spiel-Fortschritt."""
        g = m.game
        gid = m.gid
        try:
            if gid in ("pong", "duel"):
                from games import pong, duel
                win = {"pong": pong.WIN, "duel": duel.WIN}[gid]
                return self._score_bar(g.s1, g.s2, win)
            if gid == "tron":
                from games import tron
                return self._multi_bar(g.score, tron.MATCH_WINS)
            if gid == "jnb":
                from games import jnb
                return self._multi_bar([p.bumps for p in g.pl], jnb.WIN)
            if gid == "tanks":
                return (fg(C["P1"]) + "=" * (g.hp[1] // 5) + RESET
                        + fg(C["DIM"]) + "|" + RESET
                        + fg(C["P2"]) + "=" * (g.hp[2] // 5) + RESET)
            if gid == "c4":
                filled = sum(1 for c in range(7) for r in range(6) if g.board[c][r])
                return fg(C["DIM"]) + f"[{'#'*(filled)}{'.'*(42-filled)}]"[:44] + RESET
            if gid == "dots":
                return self._score_bar(g.score1, g.score2, 18)
            if gid == "wnr":
                return fg(C["BALL"]) + "*" * min(len(g.seq), 30) + RESET
        except Exception:
            return ""
        return ""

    def _multi_bar(self, scores, win):
        parts = []
        for i, sc in enumerate(scores):
            sc = min(sc, win)
            parts.append(fg(C[PCOL[i]]) + "o" * sc + fg(C["DIM"]) + "." * (win - sc) + RESET)
        return (fg(C["DIM"]) + " : " + RESET).join(parts)

    def _score_bar(self, s1, s2, win):
        s1, s2 = min(s1, win), min(s2, win)
        a = fg(C["P1"]) + "o" * s1 + fg(C["DIM"]) + "." * (win - s1) + RESET
        b = fg(C["P2"]) + "o" * s2 + fg(C["DIM"]) + "." * (win - s2) + RESET
        return a + fg(C["DIM"]) + " : " + RESET + b
