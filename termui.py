"""Kleine Terminal-Helfer: Radiobutton-Auswahl mit Pfeiltasten ([X]/[ ]).
Plattformuebergreifend: Unix (termios) und Windows (msvcrt)."""
import sys

try:
    import os
    import select
    import termios
    import tty
    _POSIX = True
except ImportError:
    _POSIX = False
try:
    import msvcrt
    _WIN = True
except ImportError:
    _WIN = False

_ACC = "\x1b[38;2;206;130;255m"
_DIM = "\x1b[38;2;123;125;123m"
_TXT = "\x1b[38;2;235;235;235m"
_R = "\x1b[0m"
_HIDE = "\x1b[?25l"
_SHOW = "\x1b[?25h"


def enable_vt():
    """Aktiviert ANSI-/VT-Sequenzen + UTF-8 in der Windows-Konsole (Win10+),
    damit Farben und Umlaute korrekt dargestellt werden."""
    if not _WIN:
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        for handle in (-11, -12):  # STDOUT, STDERR
            h = k.GetStdHandle(handle)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        k.SetConsoleOutputCP(65001)   # UTF-8
        k.SetConsoleCP(65001)
        # Markiermodus (QuickEdit) aus: sonst haelt ein Mausklick ins Fenster
        # jede Ausgabe an, bis jemand Esc drueckt.
        h = k.GetStdHandle(-10)       # STDIN
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080)   # -QUICK_EDIT, +EXTENDED_FLAGS
        # Windows-Timer auf 1 ms stellen (Standard 15,6 ms -> ruckelige Spieltakte)
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
    except Exception:
        pass
    # stdout/stderr auf UTF-8 stellen (sonst cp1252-Kodierfehler bei Umlauten)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def supported():
    return sys.stdin.isatty() and (_POSIX or _WIN)


def _read_key_posix(fd):
    try:
        b = os.read(fd, 1)
    except OSError:
        return None
    if not b:
        return None
    if b == b"\x1b":
        if select.select([fd], [], [], 0.05)[0]:
            b2 = os.read(fd, 1)
            if b2 == b"[" and select.select([fd], [], [], 0.05)[0]:
                b3 = os.read(fd, 1)
                return {b"A": "up", b"B": "down", b"C": "right", b"D": "left"}.get(b3, "esc")
        return "esc"
    if b in (b"\r", b"\n"):
        return "enter"
    try:
        return b.decode("utf-8", "ignore")
    except Exception:
        return ""


def _read_key_win():
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        ch2 = msvcrt.getwch()
        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(ch2, "esc")
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x1b":
        return "esc"
    if ch == "\x03":            # Strg-C
        raise KeyboardInterrupt
    return ch


def read_key(fd=None):
    """Eine Taste lesen -> 'up'/'down'/'left'/'right'/'enter'/'esc' oder Zeichen."""
    if _WIN:
        return _read_key_win()
    return _read_key_posix(fd)


def radio_select(prompt, options, default=0):
    """Radiobutton-Liste; Navigation mit Pfeiltasten/Ziffern, Auswahl Enter/Space.
    Liefert Index. Fallback (kein TTY): default."""
    if not supported():
        return default
    enable_vt()
    fd = None
    old = None
    if _POSIX:
        fd = sys.stdin.fileno()
        try:
            old = termios.tcgetattr(fd)
        except (termios.error, ValueError):
            return default
    sel = default
    n = len(options)

    def draw():
        for i, o in enumerate(options):
            box = "[X]" if i == sel else "[ ]"
            if i == sel:
                sys.stdout.write("\x1b[K   " + _ACC + box + " " + o + _R + "\n")
            else:
                sys.stdout.write("\x1b[K   " + _DIM + box + _R + " " + _TXT + o + _R + "\n")
        sys.stdout.flush()

    sys.stdout.write("  " + prompt + "\n")
    try:
        if _POSIX:
            tty.setcbreak(fd)
        sys.stdout.write(_HIDE)
        draw()
        while True:
            k = read_key(fd)
            if k is None or k == "esc":
                break
            if k == "up":
                sel = (sel - 1) % n
            elif k == "down":
                sel = (sel + 1) % n
            elif k in ("enter", " "):
                break
            elif k.isdigit() and 1 <= int(k) <= n:
                sel = int(k) - 1
                sys.stdout.write(f"\x1b[{n}A")
                draw()
                break
            else:
                continue
            sys.stdout.write(f"\x1b[{n}A")
            draw()
    finally:
        if _POSIX and old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(_SHOW)
        sys.stdout.flush()
    return sel
