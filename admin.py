"""Interaktives Admin-Textmenue fuer den Klassenkampf-Server.

Navigation mit den Pfeiltasten (hoch/runter), Enter bestaetigt, ESC/0 zurueck,
q beendet. Zusaetzlich funktionieren die Ziffern als Schnellwahl.

Laeuft in einem eigenen Thread, damit der asyncio-Server und laufende Spiele
nicht blockieren. Aktionen werden thread-sicher auf dem Event-Loop ausgefuehrt
(run_coroutine_threadsafe). Waehrend das Menue offen ist, pausiert das
Live-Dashboard. Einzeltasten werden im cbreak-Modus gelesen; fuer Texteingaben
(Name der Sicherung) wird kurz auf den normalen Zeilenmodus umgeschaltet.

Alle Ausgaben verwenden nur normale Textzeichen (keine Grafiksymbole).
"""
import asyncio
import atexit
import os
import shutil
import sys
import time

import termui
from console import BOLD, C, RESET, big_digits, fg

_POSIX = termui._POSIX
_WIN = termui._WIN
if _POSIX:
    import termios
    import tty

CLEAR = "\x1b[2J\x1b[H"
HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"


def acc(s):
    return fg(C["ACCENT"]) + s + RESET


def head(s):
    return fg(C["HEAD"]) + BOLD + s + RESET


def dim(s):
    return fg(C["DIM"]) + s + RESET


class AdminMenu:
    def __init__(self, server):
        self.server = server
        self.fd = None
        self.old = None
        self._raw = False
        # (Label, Handler, Sonderaktion) - Sonderaktion 'back'/'quit' oder None
        self.items = [
            ("Login-Code gross anzeigen", self._show_code, "code"),
            ("Spielerliste anzeigen", self._list, None),
            ("Spieler sperren (bannen)", self._ban, None),
            ("Sperre aufheben", self._unban, None),
            ("Spieler kicken (trennen, ohne Sperre)", self._kick, None),
            ("Credits zuruecksetzen (einzeln / alle)", self._reset, None),
            ("Stand speichern", self._save, None),
            ("Stand laden", self._load_state, None),
            ("Herausforderungs-Modus umschalten", self._mode, None),
            ("Turnier-Neustart (alle Spieler loeschen)", self._regen, None),
            ("Zurueck zum Live-Dashboard", None, "back"),
            ("Server beenden", None, "quit"),
        ]
        # Schnellwahl: Ziffern 1-9 fuer die ersten Punkte, q zum Beenden.
        self.hotkeys = {}
        for i, (_lbl, _fn, sp) in enumerate(self.items):
            if sp == "quit":
                self.hotkeys["q"] = i
        for i in range(min(9, len(self.items))):
            self.hotkeys[str(i + 1)] = i

    # ---- Bruecke zum Event-Loop ----
    def call(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self.server.loop)
        return fut.result(timeout=20)

    def ask(self, prompt):
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    # ---- Terminal-Modus ----
    def _cbreak(self):
        if _POSIX and not self._raw:
            tty.setcbreak(self.fd)
            self._raw = True
        sys.stdout.write(HIDE)
        sys.stdout.flush()

    def _cooked(self):
        if _POSIX and self._raw and self.old is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            self._raw = False
        sys.stdout.write(SHOW)
        sys.stdout.flush()

    def _restore(self):
        if _POSIX and self.old is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            except (termios.error, ValueError):
                pass
            self._raw = False
        sys.stdout.write(SHOW + RESET)
        sys.stdout.flush()

    def _read_key(self):
        """Einzeltaste lesen -> 'up'/'down'/'left'/'right'/'enter'/'esc' oder Zeichen.
        None bei EOF."""
        return termui.read_key(self.fd)

    # ---- Lebenszyklus ----
    def run(self):
        time.sleep(0.5)
        if not termui.supported():
            return                      # kein interaktives Terminal (Hintergrund)
        termui.enable_vt()
        if _POSIX:
            self.fd = sys.stdin.fileno()
            try:
                self.old = termios.tcgetattr(self.fd)
            except (termios.error, ValueError):
                return
            atexit.register(self._restore)
        try:
            self._cbreak()
            while True:
                key = self._read_key()   # im Dashboard: beliebige Taste oeffnet Menue
                if key is None:
                    return
                if key in ("q", "Q"):
                    self._quit_flow(in_menu=False)
                self._menu_loop()
        finally:
            self._restore()

    def _menu_loop(self):
        self.server.dashboard.paused = True
        time.sleep(0.35)
        sel = 0
        try:
            while True:
                self._draw_menu(sel)
                key = self._read_key()
                if key is None or key == "esc":
                    return
                if key == "up":
                    sel = (sel - 1) % len(self.items)
                elif key == "down":
                    sel = (sel + 1) % len(self.items)
                elif key == "enter":
                    if self._activate(sel):
                        return
                elif key in self.hotkeys:
                    sel = self.hotkeys[key]
                    if self._activate(sel):
                        return
        finally:
            self._cbreak()
            self.server.dashboard.paused = False

    def _activate(self, i):
        """True -> Menue verlassen (zurueck zum Dashboard)."""
        label, fn, special = self.items[i]
        if special == "back":
            return True
        if special == "quit":
            self._quit_flow(in_menu=True)
            return True
        if special == "code":
            fn()
            return False
        # Moduswechsel: sofort zurueck ins Menue (keine [Enter]-Bestaetigung)
        self._run_action(fn, pause=(fn != self._mode))
        return False

    def _run_action(self, fn, pause=True):
        self._cooked()
        sys.stdout.write(CLEAR)
        sys.stdout.flush()
        try:
            fn()
        except Exception as e:               # Menue soll nie abstuerzen
            print(fg(C["P2"]) + f"  Fehler: {e}" + RESET)
        if pause:
            self.ask(dim("\n  [Enter] weiter ..."))
        self._cbreak()

    def _draw_menu(self, sel):
        n = len(self.server.players)
        online = sum(1 for p in self.server.players.values() if p.online)
        banned = len(self.server.banned)
        out = [CLEAR]
        out.append(head("  == Klassenkampf - Admin-Menue ============================"))
        out.append(dim(f"     {n} Spieler - {online} online - {banned} gesperrt"))
        mode_txt = "Zufaelliges Spiel" if self.server.mode == "random" else "Spiel selbst waehlen"
        out.append(dim(f"     Modus: {mode_txt}   Login-Code: ") + fg(C["HEAD"]) + BOLD
                   + self.server.login_code + RESET)
        out.append("")
        for i, (label, _fn, _sp) in enumerate(self.items):
            num = f"{i + 1:02d}."
            if i == sel:
                out.append("   " + fg(C["ACCENT"]) + BOLD + "> " + num + " " + label + RESET)
            else:
                out.append("     " + dim(num) + " " + fg(C["TEXT"]) + label + RESET)
        out.append("")
        out.append(dim("   Pfeiltasten waehlen - Enter bestaetigen - 1-9 Schnellwahl - ESC zurueck - q beenden"))
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()

    # ---- Aktionen ----
    def _show_code(self):
        """Login-Code so gross wie moeglich anzeigen (z.B. fuer den Beamer)."""
        code = self.server.login_code
        size = shutil.get_terminal_size((100, 30))
        sx, sy = 1, 1
        for cx, cy in ((6, 3), (5, 2), (4, 2), (3, 1), (2, 1)):
            if len(code) * 7 * cx <= size.columns - 4 and 7 * cy + 8 <= size.lines:
                sx, sy = cx, cy
                break
        rows = big_digits(code, sx, sy)
        width = max(len(r) for r in rows)
        pad = " " * max(2, (size.columns - width) // 2)
        out = [CLEAR, "", head("  LOGIN-CODE"), ""]
        out += [fg(C["HEAD"]) + BOLD + pad + r + RESET for r in rows]
        out += ["", "  " + fg(C["TEXT"]) + "Im Browser oeffnen: " + fg(C["OK"]) + BOLD
                + self.server.dashboard.url() + RESET,
                "  " + fg(C["TEXT"]) + "Code eingeben, dann Namen waehlen." + RESET,
                "", dim("  (beliebige Taste: zurueck zum Menue)")]
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()
        self._read_key()

    def _pick(self, prompt, rows, empty_msg):
        """Spieler aus einer Liste waehlen -> nick_key oder None."""
        if not rows:
            print(dim("  " + empty_msg))
            return None
        opts = [r["nick"] for r in rows] + ["(Abbrechen)"]
        idx = termui.radio_select(prompt, opts, 0)
        if idx >= len(rows):
            print(dim("  Abgebrochen."))
            return None
        return rows[idx]["key"]

    def _ban(self):
        rows = [r for r in self.server.admin_list() if not r["banned"]]
        key = self._pick("Spieler sperren (Pfeiltasten, Enter):", rows, "Keine Spieler vorhanden.")
        if key:
            print("  " + self.call(self.server.admin_ban(key)))

    def _unban(self):
        rows = [r for r in self.server.admin_list() if r["banned"]]
        key = self._pick("Sperre aufheben (Pfeiltasten, Enter):", rows, "Keine gesperrten Spieler.")
        if key:
            print("  " + self.call(self.server.admin_unban(key)))

    def _kick(self):
        rows = [r for r in self.server.admin_list() if r["online"] or r["busy"]]
        key = self._pick("Spieler trennen (Pfeiltasten, Enter):", rows, "Niemand ist verbunden.")
        if key:
            print("  " + self.call(self.server.admin_kick(key)))

    def _reset(self):
        rows = self.server.admin_list()
        if not rows:
            print(dim("  Keine Spieler vorhanden."))
            return
        opts = ["ALLE Spieler"] + [r["nick"] for r in rows] + ["(Abbrechen)"]
        idx = termui.radio_select("Credits zuruecksetzen (Pfeiltasten, Enter):", opts, len(opts) - 1)
        if idx == len(opts) - 1:
            print(dim("  Abgebrochen."))
            return
        if idx == 0:
            if self.ask(fg(C["P2"]) + "  Wirklich ALLE Credits auf 0? (ja/nein): " + RESET).lower() not in ("ja", "j", "y"):
                print(dim("  Abgebrochen."))
                return
            print("  " + self.call(self.server.admin_reset_credits(None)))
        else:
            print("  " + self.call(self.server.admin_reset_credits(rows[idx - 1]["key"])))

    def _list(self):
        rows = self.server.admin_list()
        if not rows:
            print(dim("  Noch keine Spieler angemeldet."))
            return
        print(head(f"   {'Name':<18}{'Cred':>6}{'S/N':>8}  Status"))
        for r in rows:
            if r["banned"]:
                st = fg(C["P2"]) + "GESPERRT" + RESET
            elif r["busy"]:
                st = fg(C["P2"]) + "im Spiel" + RESET
            elif r["online"]:
                st = fg(C["P1"]) + "online" + RESET
            else:
                st = dim("offline")
            wl = f"{r['wl'][0]}/{r['wl'][1]}"
            print(f"   {r['nick'][:16]:<18}{r['credits']:>+6}{wl:>8}  {st}")

    def _regen(self):
        if self.ask(fg(C["P2"]) + "  ACHTUNG: loescht ALLE Spieler & Credits. Fortfahren? (ja/nein): " + RESET).lower() not in ("ja", "j", "y"):
            print(dim("  Abgebrochen."))
            return
        self.call(self.server.admin_clear_players())
        print(fg(C["P1"]) + "  Alle Spieler geloescht. Der Login-Code bleibt gleich." + RESET)

    def _mode(self):
        cur = self.server.mode
        idx = termui.radio_select(
            "Herausforderungs-Modus (Pfeiltasten, Enter):",
            ["Spiel selbst waehlen", "Zufaelliges Spiel (Auswahl verborgen)"],
            1 if cur == "random" else 0)
        new = "random" if idx == 1 else "choose"
        self.call(self.server.admin_set_mode(new))
        txt = "Zufaelliges Spiel (Auswahl verborgen)" if new == "random" else "Spiel selbst waehlen"
        print(fg(C["P1"]) + f"  Modus gesetzt: {txt}" + RESET)

    def _clean_name(self, s):
        keep = "".join(ch for ch in s if ch.isalnum() or ch in " -_")
        return keep.strip().replace(" ", "_")[:40]

    def _save(self):
        default = "stand-" + time.strftime("%Y%m%d-%H%M")
        name = self._clean_name(self.ask(f"  Name der Sicherung [{default}]: ")) or default
        path = self.server.admin_save(name)
        print(fg(C["P1"]) + f"  Gespeichert: {path}" + RESET)

    def _load_state(self):
        saves = self.server.admin_list_saves()
        if not saves:
            print(dim("  Keine Sicherungen vorhanden. Erst mit 'Stand speichern' anlegen."))
            return
        idx = termui.radio_select("Sicherung laden (Pfeiltasten, Enter):",
                                  saves + ["(Abbrechen)"], 0)
        if idx >= len(saves):
            print(dim("  Abgebrochen."))
            return
        print(fg(C["P2"]) + "  Hinweis: ersetzt den aktuellen Stand und trennt verbundene Spieler." + RESET)
        msg = self.call(self.server.admin_load(saves[idx]))
        print(fg(C["P1"]) + "  " + msg + RESET)

    def _quit_flow(self, in_menu):
        """Beim Beenden fragen, ob der aktuelle Stand gesichert werden soll."""
        if not in_menu:
            self.server.dashboard.paused = True
            time.sleep(0.35)
        self._cooked()
        sys.stdout.write(CLEAR)
        sys.stdout.flush()
        ans = self.ask(fg(C["OK"]) + "  Aktuellen Stand speichern? (j/n) [n]: " + RESET).lower()
        if ans in ("j", "ja", "y", "yes"):
            self._save()
        self._shutdown_clean()

    def _shutdown_clean(self):
        self._restore()
        sys.stdout.write("\x1b[2J\x1b[H" + SHOW + RESET)
        sys.stdout.write("  Klassenkampf beendet.\n\n")
        for line in self.server.duration_report():
            sys.stdout.write(line + "\n")
        sys.stdout.write("\n")
        sys.stdout.flush()
        os._exit(0)
