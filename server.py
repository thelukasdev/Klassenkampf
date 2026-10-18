#!/usr/bin/env python3
"""Klassenkampf - gemeinsamer Multiplayer-Server fuer die PBC-Spielesammlung.

Ein einziger Python-Prozess:
  * liefert die HTML/JS-Spiele als Webserver aus,
  * betreibt die WebSocket-Kommunikation,
  * simuliert alle Spiele autoritativ,
  * zeigt bunte Live-Stats im Terminal,
  * bietet ein Admin-Textmenue (Enter druecken): Login-Code gross anzeigen,
    sperren/kicken, Credits/Turnier zuruecksetzen u.a.

Anmeldung: EIN gemeinsamer 4-stelliger Login-Code, der bei jedem Start neu
gewuerfelt wird, dazu waehlt jeder einen Nicknamen. Credits haengen am
Nicknamen und werden in state.json gespeichert.

Start:  python3 server.py [--port 8080] [--reset]
"""
import argparse
import asyncio
import builtins
import json
import os
import random
import secrets
import sys
import threading
import time
import logging
import signal
import re
import hashlib
import base64
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit, unquote

import games
import termui
import wsutil
from admin import AdminMenu
from console import Dashboard
from web_admin import WebAdmin

HERE = os.path.dirname(os.path.abspath(__file__))
# Schreibbarer Ort fuer state.json (neben der .exe, wenn "frozen").
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = HERE
STATIC = os.path.join(HERE, "static")
STATE_FILE = os.path.join(APP_DIR, "state.json")
SAVE_DIR = os.path.join(APP_DIR, "saves")   # benannte Sicherungen (Speichern/Laden)
# Im Single-File-Build eingebettete statische Dateien: {name: bytes}
_EMBED = getattr(builtins, "_CLASSWARS_STATIC", None)


class ServiceDashboard:
    """Plain logs for Docker, without terminal rendering or input threads."""
    def log(self, message):
        logging.info(message)


def configure_data_dir(path):
    global APP_DIR, STATE_FILE, SAVE_DIR
    APP_DIR = os.path.abspath(path)
    os.makedirs(APP_DIR, exist_ok=True)
    STATE_FILE = os.path.join(APP_DIR, 'state.json')
    SAVE_DIR = os.path.join(APP_DIR, 'saves')

CREDIT_WIN = 2
CREDIT_LOSS = 0
CREDIT_DRAW = 1

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
}


# ------------------------------------------------------------------ Modelle
class Conn:
    """Eine WebSocket-Verbindung (Sende-Seite mit Lock)."""

    def __init__(self, writer):
        self.writer = writer
        self.lock = asyncio.Lock()
        self.alive = True
        self.authed = False       # Login-Code der Sitzung korrekt eingegeben
        self.login_attempts = 0

    async def send(self, obj):
        if not self.alive:
            return
        data = wsutil.encode_frame(json.dumps(obj).encode())
        try:
            async with self.lock:
                self.writer.write(data)
                await self.writer.drain()
        except (ConnectionError, RuntimeError):
            self.alive = False

    async def send_raw(self, frame):
        if not self.alive:
            return
        try:
            async with self.lock:
                self.writer.write(frame)
                await self.writer.drain()
        except (ConnectionError, RuntimeError):
            self.alive = False


class Player:
    def __init__(self, nick):
        self.nick = nick
        self.pid = None           # oeffentliche ID
        self.tok = None           # geheimer Schluessel fuers Wiederverbinden
        self.token_hash = None
        self.credits = 0
        self.record = {}          # gid -> [wins, losses]
        self.conn = None          # Conn oder None (offline)
        self.match = None         # Match oder None
        self.role = 0             # 1 oder 2 im Match
        self.out_challenge = None  # Challenge oder None (eigene Herausforderung)

    @property
    def key(self):
        return nick_key(self.nick)

    @property
    def online(self):
        return self.conn is not None and self.conn.alive

    @property
    def busy(self):
        return self.match is not None

    def rec(self, gid):
        return self.record.setdefault(gid, [0, 0])

    def to_dict(self):
        return {"credits": self.credits, "record": self.record,
                "token_hash": self.token_hash}


def nick_key(nick):
    return nick.strip().lower()


def new_login_code(old=None):
    """4-stelliger Zahlencode (einfach auf dem Tablet einzutippen)."""
    while True:
        c = "".join(random.choice("0123456789") for _ in range(4))
        if c != old:
            return c


class Challenge:
    """Herausforderung eines Spielers an 1..max-1 Gegner. Das Spiel startet,
    sobald alle geantwortet haben (mindestens einer hat angenommen), oder
    vorher, wenn der Herausforderer auf "Starten" drueckt."""

    def __init__(self, src, gid):
        self.src = src
        self.gid = gid            # None im Zufallsmodus
        self.targets = {}         # pid -> "pending" | "accepted"


class Match:
    _next_id = 1

    def __init__(self, server, gid, players):
        self.server = server
        self.id = Match._next_id
        Match._next_id += 1
        self.gid = gid
        self.players = list(players)      # Rolle = Index + 1, Herausforderer = 1
        self.left = set()                 # Spieler, die vorzeitig gegangen sind
        self.game = games.create(gid, len(players))
        if server.worker:
            from game_worker import RemoteGame
            self.game = RemoteGame(server.worker,self.id,gid,len(players))
        self.paused=False
        self.outcomes={}
        self.initial_credits={p.nick:p.credits for p in players}
        self.end_reason='normal'
        self.recorded=False
        self.name = games.GAMES[gid].name
        self.finished = False
        self.task = None
        self.spectator_token=None
        self.last_frame=None
        self.recorder=None
        try:self.recorder=server.replays.start(self)
        except Exception:logging.error('Replay recording unavailable')
        self.start_t = time.monotonic()   # fuer die (unsichtbare) Dauer-Statistik
        for role, p in enumerate(self.players, 1):
            p.match = self
            p.role = role
            p.out_challenge = None

    @property
    def active(self):
        return [p for p in self.players if p not in self.left]

    async def run(self):
        g = self.game
        dt = g.tick_ms / 1000.0
        names = [p.nick for p in self.players]
        for role, p in enumerate(self.players, 1):
            opp = " / ".join(n for i, n in enumerate(names, 1) if i != role)
            await self._send(p, {"t": "match_start", "game": self.gid, "name": self.name,
                                 "role": role, "opp": opp, "names": names})
        loop = asyncio.get_running_loop()
        next_t = loop.time()
        try:
            while not self.finished:
                if self.paused or self.server.rules['paused']:
                    next_t=loop.time()
                    await asyncio.sleep(.1)
                    continue
                if hasattr(g,'step'):
                    await g.step(self.server.rules['speed'])
                else:
                    for _ in range(self.server.rules['speed']): g.tick()
                await self._broadcast_state()
                if g.result is not None:
                    await self._end_by_result(g.result)
                    break
                next_t += dt
                delay = next_t - loop.time()
                if delay < -0.5:
                    next_t = loop.time()       # bei Ueberlast resynchronisieren
                    delay = 0
                await asyncio.sleep(max(0, delay))
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception('Game worker failed in session %s',self.server.room_id)
            await self.server.control.cancel_match(self,'worker_error')
        finally:
            if hasattr(g,'close'):
                try: await g.close()
                except Exception: pass

    async def _broadcast_state(self):
        views={str(p.role):self.game.snapshot(view=p.role) for p in self.players} if self.game.per_view else {'0':self.game.snapshot()}
        self.last_frame={'t':round(time.monotonic()-self.start_t,3),'views':views}
        if self.recorder:
            try:self.recorder.capture(self.last_frame)
            except Exception:logging.error('Replay frame could not be recorded')
        for p in self.active:
            if p.online:await self._send(p,{'t':'state','s':views[str(p.role) if self.game.per_view else '0']})

    async def _send(self, p, obj):
        if p.conn:
            await p.conn.send(obj)

    async def _end_by_result(self, result):
        if self.finished:
            return
        self.finished = True
        winner = None if result == "draw" else self.players[int(result[1:]) - 1]
        for p in self.active:
            if winner is None:
                out = "draw"
            else:
                out = "win" if p is winner else "loss"
            self._award(p, out)
            await self._send(p, {"t": "match_end", "result": out,
                                 "credits": p.credits,"delta":p.credits-self.initial_credits[p.nick], "reason": "normal"})
        self.server.close_match(self)

    async def abort(self, quitter):
        """Ein Spieler bricht ab / verliert die Verbindung. Zu zweit gewinnt der
        Gegner; zu mehreren scheidet nur der Abbrechende aus."""
        if self.finished or quitter in self.left:
            return
        self.end_reason="leave"
        rest = [p for p in self.active if p is not quitter]
        self._award(quitter, "loss")
        await self._send(quitter, {"t": "match_end", "result": "loss",
                                   "credits": quitter.credits,"delta":quitter.credits-self.initial_credits[quitter.nick], "reason": "you_left"})
        if len(rest) == 1:
            self.finished = True
            winner = rest[0]
            self._award(winner, "win")
            await self._send(winner, {"t": "match_end", "result": "win",
                                      "credits": winner.credits,"delta":winner.credits-self.initial_credits[winner.nick], "reason": "opp_left"})
            self.server.close_match(self)
            return
        self.left.add(quitter)
        quitter.match = None
        quitter.role = 0
        self.game.remove_player(self.players.index(quitter) + 1)
        for p in rest:
            await self._send(p, {"t": "info", "msg": f"{quitter.nick} hat aufgegeben"})
        asyncio.create_task(self.server.push_lobby())

    def _award(self, p, outcome):
        self.outcomes[p.nick]=outcome
        if outcome == "win":
            p.credits += self.server.rules['credits_win']
            p.rec(self.gid)[0] += 1
        elif outcome == "loss":
            p.credits += self.server.rules['credits_loss']
            p.rec(self.gid)[1] += 1
        else:  # draw
            p.credits += self.server.rules['credits_draw']


# ------------------------------------------------------------------ Server
class Server:
    def __init__(self, host, port, reset, mode="choose", *, headless=False,
                 login_code=None, admin_token=None, public_origin=None,
                 admin_port=9090, max_connections=256, sessions=False, room_id=None, hub=None):
        self.started_at=time.monotonic()
        self.host = host
        self.port = port
        self.mode = mode          # "choose" (Spiel selbst waehlen) | "random"
        self.login_code = login_code or secrets.token_urlsafe(12)
        self.headless = headless
        self.admin_token = admin_token
        self.public_origin = public_origin
        self.admin_port = admin_port
        self.max_connections = max_connections
        self.connections = set()
        self.failed_logins = deque(maxlen=120)
        self.session_hub = None
        self.room_id = room_id
        self.hub = hub
        self.save_dir = os.path.join(APP_DIR, 'session-saves', room_id) if room_id else SAVE_DIR
        self.players = {}         # nick_key -> Player
        self.by_pid = {}          # pid -> Player
        self.matches = {}         # id -> Match
        self.banned = set()       # gesperrte nick_keys
        self.loop = None
        # Unsichtbarer Zaehler: gid -> [Summe Dauer (s), Anzahl Partien].
        # Wird nirgends angezeigt, nur beim Beenden ausgewertet.
        self.game_stats = {}
        self.rules={'enabled':list(games.GAMES),'paused':False,'speed':1,
                    'credits_win':CREDIT_WIN,'credits_loss':CREDIT_LOSS,'credits_draw':CREDIT_DRAW}
        self.history=[]
        self.worker=None
        if room_id and os.environ.get('KLASSENKAMPF_WORKERS','1')=='1':
            from game_worker import SessionWorker
            self.worker=SessionWorker()
        from control import ArenaControl
        self.control=ArenaControl(self)
        self.dashboard = ServiceDashboard() if headless else Dashboard(self)
        self.web_admin = hub.server.web_admin if hub else WebAdmin(self, APP_DIR)
        from replays import ReplayLibrary
        self.replays=hub.server.replays if hub else ReplayLibrary(self.web_admin.store,APP_DIR)
        stored = hub.state(room_id) if hub else self.web_admin.store.load_game()
        if stored is not None and not reset:
            self._apply_state(stored)
        elif os.path.exists(STATE_FILE) and not reset:
            with open(STATE_FILE) as f:
                self._apply_state(json.load(f))
        self.save()
        if sessions:
            from game_sessions import GameSessions
            self.session_hub = GameSessions(self)

    def _new_pid(self):
        pid = format(random.getrandbits(32), "08x")
        while pid in self.by_pid:
            pid = format(random.getrandbits(32), "08x")
        return pid

    def _add_player(self, nick):
        p = Player(nick)
        p.pid = self._new_pid()
        self.players[p.key] = p
        self.by_pid[p.pid] = p
        return p

    # ----- Persistenz -----
    def _state_dict(self):
        return {"players": {p.nick: p.to_dict() for p in self.players.values()},
                "banned": sorted(self.banned),
                "mode": self.mode,"rules":self.rules,"history":self.history}

    def save(self):
        if self.hub:
            self.hub.persist(self)
            return
        self.web_admin.store.save_game(self._state_dict())
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._state_dict(), f, indent=1)
        os.replace(tmp, STATE_FILE)

    def _apply_state(self, data):
        """Zustand aus einem dict uebernehmen (Spieler/Credits/Bann/Modus)."""
        self.rules.update(data.get('rules',{}))
        self.history=list(data.get('history',[]))[-2000:]
        self.players.clear()
        self.by_pid.clear()
        entries = dict(data.get("players", {}))
        banned = set(data.get("banned", []))
        # Altes Format (persoenliche Codes): Spieler mit Nick uebernehmen
        old = data.get("codes", {})
        for code, d in old.items():
            if d.get("nick"):
                entries.setdefault(d["nick"], d)
                if code in banned:
                    banned.add(nick_key(d["nick"]))
        if old:
            banned = {b for b in banned if b not in old}
        for nick, d in entries.items():
            if not nick_key(nick) or nick_key(nick) in self.players:
                continue
            p = self._add_player(nick)
            p.credits = d.get("credits", 0)
            p.record = {k: list(v) for k, v in d.get("record", {}).items()}
            p.token_hash = d.get('token_hash')
        self.banned = banned
        self.mode = data.get("mode", self.mode)

    # ----- Lobby -----
    def lobby_view(self, me):
        players = []
        for p in sorted(self.players.values(), key=lambda x: x.key):
            players.append({
                "pid": p.pid,
                "nick": p.nick,
                "credits": p.credits,
                "online": p.online,
                "busy": p.busy,
                "you": p is me,
                "wl": [sum(r[0] for r in p.record.values()),
                       sum(r[1] for r in p.record.values())],
            })
        def gname(gid):
            # Im Zufallsmodus wird das Spiel nicht verraten.
            return games.GAMES[gid].name if (gid and self.mode == "choose") else None
        incoming = []
        for c in self._challenges():
            st = c.targets.get(me.pid)
            if st and c.src.online:
                others = [self.by_pid[q].nick for q in c.targets if q != me.pid and q in self.by_pid]
                incoming.append({"from": c.src.pid, "nick": c.src.nick, "gname": gname(c.gid),
                                 "acc": st == "accepted", "others": others})
        out = None
        c = me.out_challenge
        if c:
            out = {"gname": gname(c.gid), "max": self._max_targets(c.gid),
                   "targets": [{"pid": q, "nick": self.by_pid[q].nick, "acc": st == "accepted"}
                               for q, st in c.targets.items() if q in self.by_pid]}
        return {"t": "lobby", "players": players, "incoming": incoming,
                "session_name":getattr(self,'room_name',None),
                "watch":[{'name':m.name,'players':[p.nick for p in m.players],'url':'/watch#'+m.spectator_token} for m in self.matches.values() if m.spectator_token],
                "outgoing": out, "mode": self.mode,"enabled_games":self.rules['enabled'],"paused":self.rules['paused'],
                "you": {"nick": me.nick, "credits": me.credits,
                        "record": me.record}}

    def _challenges(self):
        return [p.out_challenge for p in self.players.values() if p.out_challenge]

    def _max_targets(self, gid):
        """Wie viele Gegner hoechstens herausgefordert werden koennen."""
        if gid is None:      # Zufallsmodus: Spiel wird passend zur Zahl gewuerfelt
            return max(games.GAMES[g].max_players for g in self.rules['enabled']) - 1
        return games.GAMES[gid].max_players - 1

    def _withdraw(self, player, keep=None):
        """player aus allen fremden Herausforderungen austragen (ausser keep).
        Liefert die betroffenen Herausforderungen."""
        hit = []
        for c in self._challenges():
            if c is not keep and player.pid in c.targets:
                del c.targets[player.pid]
                if not c.targets:
                    c.src.out_challenge = None
                else:
                    hit.append(c)
        return hit

    async def _maybe_start(self, c, force=False):
        """Herausforderung starten, wenn niemand mehr aussteht (oder force)."""
        if self.rules['paused'] or (c.gid and c.gid not in self.rules['enabled']): return
        if c.src.out_challenge is not c or c.src.busy or not c.src.online:
            return
        acc = [self.by_pid[q] for q, st in c.targets.items()
               if st == "accepted" and q in self.by_pid]
        acc = [p for p in acc if p.online and not p.busy]
        pending = any(st == "pending" for st in c.targets.values())
        if not acc or (pending and not force):
            return
        n = 1 + len(acc)
        gid = c.gid
        if gid is None:                       # Zufallsmodus -> jetzt Spiel wuerfeln
            candidates=[g for g, cls in games.GAMES.items() if cls.max_players >= n and g in self.rules['enabled']]
            if not candidates:return
            gid=random.choice(candidates)
        c.src.out_challenge = None
        for q, st in list(c.targets.items()):
            p = self.by_pid.get(q)
            if p and p not in acc and p.online:
                await p.conn.send({"t": "info", "msg": f"Spiel von {c.src.nick} ist ohne dich gestartet"})
        players = [c.src] + acc
        follow = []
        for p in players:
            follow += self._withdraw(p)
        self.start_match(gid, players)
        for oc in follow:
            await self._maybe_start(oc)

    async def push_lobby(self):
        """Lobby an alle online, nicht spielenden Spieler senden."""
        for p in self.players.values():
            if p.online and not p.busy:
                await p.conn.send(self.lobby_view(p))

    # ----- Matches -----
    def start_match(self, gid, players):
        if self.rules['paused'] or gid not in self.rules['enabled']:
            raise ValueError('Dieses Spiel ist pausiert oder nicht freigegeben.')
        if len(self.matches)>=16: raise ValueError('Zu viele gleichzeitige Partien.')
        if self.hub:
            live=sum(bool(r.matches) for r in self.hub.rooms.values())
            if not self.matches and live>=8: raise ValueError('Serverkapazitaet erreicht. Bitte spaeter starten.')
        m = Match(self, gid, players)
        self.matches[m.id] = m
        m.task = asyncio.create_task(m.run())
        return m

    def close_match(self, m):
        m.spectator_token=None
        if m.recorder:m.recorder.finish(m.end_reason)
        if not m.recorded:
            m.recorded=True
            self.history.append({'id':m.id,'game':m.gid,'name':m.name,'players':[p.nick for p in m.players],
                                 'outcomes':m.outcomes,'reason':m.end_reason,'time':int(time.time()),
                                 'duration':round(time.monotonic()-m.start_t,1),'replay':m.recorder.id if m.recorder else None})
            self.history=self.history[-2000:]
        # Dauer der (beendeten) Partie unsichtbar mitzaehlen.
        st = self.game_stats.setdefault(m.gid, [0.0, 0])
        st[0] += time.monotonic() - m.start_t
        st[1] += 1
        for p in m.players:
            if p.match is m:
                p.match = None
                p.role = 0
        self.matches.pop(m.id, None)
        self.save()
        asyncio.create_task(self.push_lobby())

    def duration_report(self):
        """Zeilen mit der durchschnittlichen Partiedauer je Spiel (fuer Shutdown)."""
        lines = ["  Durchschnittliche Spieldauer je Spiel (diese Sitzung):"]
        any_played = False
        for gid, meta in games.GAMES.items():
            st = self.game_stats.get(gid)
            if st and st[1]:
                any_played = True
                avg = st[0] / st[1]
                mm, ss = divmod(int(round(avg)), 60)
                dur = f"{mm}:{ss:02d} min" if mm else f"{ss}s"
                lines.append(f"    {meta.name:<14} {st[1]:>3} Partien   Schnitt {dur}")
            else:
                lines.append(f"    {meta.name:<14}   -  keine Partien")
        if not any_played:
            lines.append("    (in dieser Sitzung wurde keine Partie gespielt)")
        return lines

    # ----- Verbindungen -----
    async def handle(self, reader, writer):
        if len(self.connections) >= self.max_connections:
            writer.close()
            return
        self.connections.add(writer)
        try:
            await self._handle_request(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError, TimeoutError,
                ValueError, UnicodeError):
            pass
        except Exception:
            logging.exception('Connection handler failed')
        finally:
            self.connections.discard(writer)
            writer.close()

    async def _handle_request(self, reader, writer):
        # HTTP-Request-Zeile + Header lesen
        try:
            request_line = await asyncio.wait_for(reader.readline(), 10)
        except ConnectionError:
            writer.close()
            return
        if not request_line:
            writer.close()
            return
        parts = request_line.decode("latin1").split()
        if len(parts) < 2:
            writer.close()
            return
        method, path = parts[0], parts[1]
        headers = {}
        header_size = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), 10)
            header_size += len(line)
            if header_size > 16384 or len(line) > 8192:
                raise ValueError('Headers too large')
            if line in (b"\r\n", b"\n", b""):
                break
            k, _, v = line.decode("latin1").partition(":")
            headers[k.strip().lower()] = v.strip()

        if urlsplit(path).path=='/api/watch':
            token=headers.get('x-spectator-token','')
            match=None
            if method=='GET' and 20<=len(token)<=64 and self.session_hub:
                match=next((m for r in self.session_hub.rooms.values() for m in r.matches.values()
                            if m.spectator_token and secrets.compare_digest(token.encode(),m.spectator_token.encode())),None)
            if not match or match.game.per_view or match.finished:
                await self.web_admin.respond(writer,404,{'error':'Freigabe beendet oder nicht verfügbar.'})
            else:
                await self.web_admin.respond(writer,200,{'game':match.gid,'name':match.name,'players':[p.nick for p in match.players],
                    'paused':match.paused or match.server.rules['paused'],'frame':match.last_frame})
        elif urlsplit(path).path=='/internal/status.json':
            token=os.environ.get('KLASSENKAMPF_STATUS_TOKEN','')
            if method!='GET' or not token or not secrets.compare_digest(headers.get('authorization','').encode(),('Bearer '+token).encode()):
                await self._http_response(writer,404,b'Not found')
                return
            from status_snapshot import snapshot
            try:body=json.dumps(snapshot(self)).encode()
            except Exception:body=json.dumps({'version':1,'database':'down','sessions':[]}).encode()
            await self._http_response(writer,200,body)
        elif urlsplit(path).path.startswith(('/auth/', '/api/admin/', '/api/player/')):
            await self.web_admin.handle(reader, writer, method, path, headers)
        elif headers.get("upgrade", "").lower() == "websocket":
            if method != 'GET' or urlsplit(path).path != '/':
                await self._http_response(writer, 400, b'Invalid WebSocket request')
                return
            origin = headers.get('origin')
            expected = self.public_origin
            if not expected and origin:
                expected = 'http://' + headers.get('host', '')
            if (expected and origin != expected) or headers.get('sec-websocket-version') != '13':
                await self._http_response(writer, 403, b'Origin or version rejected')
                return
            await self._do_websocket(reader, writer, headers)
        else:
            await self._serve_http(writer, method, path)

    async def _serve_http(self, writer, method, path):
        if method not in ('GET', 'HEAD'):
            await self._http_response(writer, 405, b'Method not allowed')
            return
        path = unquote(urlsplit(path).path)
        if path == '/internal/status.json':
            await self._http_response(writer,404,b'Not found')
            return
        if path in ('/account/manage','/account/manage/'):
            path='/admin.html'
        if path in ('/account','/account/'):
            path='/host.html'
        if path in ('/login','/login/'):
            path='/login.html'
        if path in ('/watch','/watch/'):
            path='/watch.html'
        if path in ('/admin', '/admin/'):
            path = '/admin.html'
        if path == '/healthz':
            await self._http_response(writer, 200, b'ok', head=method == 'HEAD')
            return
        if path == "/":
            path = "/index.html"
        safe = path.lstrip('/')
        if '\\' in safe or '..' in Path(safe).parts or '\x00' in safe:
            await self._http_response(writer, 404, b'Not found')
            return
        body = None
        ext = os.path.splitext(safe)[1]
        if _EMBED is not None:                     # Single-File-Build
            body = _EMBED.get(safe)
        else:                                      # Dateien von der Platte
            full = (Path(STATIC) / safe).resolve()
            if full.is_relative_to(Path(STATIC).resolve()) and full.is_file():
                with open(full, "rb") as f:
                    body = f.read()
        if body is None:
            body = b"404 Not Found"
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: %d\r\n"
                         b"Connection: close\r\n\r\n%s" % (len(body), body))
        else:
            ctype = MIME.get(ext, "application/octet-stream")
            header = (f"HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\n"
                      f"Content-Length: {len(body)}\r\n"
                      f"Cache-Control: no-cache, no-store, must-revalidate\r\n"
                      f"Connection: close\r\n\r\n")
            writer.write(header.encode() + (b'' if method == 'HEAD' else body))
        try:
            await writer.drain()
        except ConnectionError:
            pass
        writer.close()

    async def _http_response(self, writer, status, body, *, head=False):
        reason = {200: 'OK', 400: 'Bad Request', 401: 'Unauthorized',
                  403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed'}[status]
        writer.write((f'HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\n'
                      'Content-Type: application/json; charset=utf-8\r\n'
                      'Cache-Control: no-store\r\nConnection: close\r\n\r\n').encode()
                     + (b'' if head else body))
        await writer.drain()

    async def handle_admin(self, reader, writer):
        """Separate loopback-only management port; never reverse-proxied."""
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            if line.split()[:2] != [b'POST', b'/admin']:
                await self._http_response(writer, 404, b'{}')
                return
            headers = {}
            size = 0
            while True:
                line = await asyncio.wait_for(reader.readline(), 5)
                size += len(line)
                if size > 8192:
                    raise ValueError('Headers too large')
                if line in (b'\r\n', b'\n', b''):
                    break
                k, _, v = line.decode('latin1').partition(':')
                headers[k.lower()] = v.strip()
            supplied = headers.get('authorization', '')
            if not self.admin_token or not secrets.compare_digest(
                    supplied.encode(), ('Bearer ' + self.admin_token).encode()):
                await self._http_response(writer, 401, b'{}')
                return
            length = int(headers.get('content-length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid body length')
            obj = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
            result = await self.admin_action(obj)
            await self._http_response(writer, 200, json.dumps({'result': result}).encode())
        except (ValueError, TypeError, KeyError, TimeoutError, asyncio.IncompleteReadError):
            await self._http_response(writer, 400, b'{"error":"Invalid request"}')
        except ConnectionError:
            pass
        except Exception:
            logging.exception('Admin operation failed')
        finally:
            writer.close()

    async def admin_action(self, obj):
        if self.session_hub:
            return await self.session_hub.action(obj)
        action = obj['action']
        if action in ('rules','pause-match','end-match','remove-player','move-player','spectators'):
            return await self.control.action(obj)
        value = str(obj.get('value', ''))
        if action == 'status':
            return {'mode': self.mode, 'players': self.admin_list(),
                    'matches': len(self.matches), 'connections': len(self.connections)}
        if action == 'code':
            return self.login_code
        if action in ('save', 'load'):
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
                raise ValueError('Invalid snapshot name')
            return self.admin_save(value) if action == 'save' else await self.admin_load(value)
        if action == 'saves':
            return self.admin_list_saves()
        if action == 'mode':
            if value not in ('choose', 'random'):
                raise ValueError('Invalid mode')
            return await self.admin_set_mode(value)
        if action in ('kick', 'ban', 'unban', 'reset-credits'):
            if not value:
                raise ValueError('Player required')
            method = {'kick': self.admin_kick, 'ban': self.admin_ban,
                      'unban': self.admin_unban, 'reset-credits': self.admin_reset_credits}[action]
            return await method(nick_key(value))
        raise ValueError('Unknown action')

    async def _do_websocket(self, reader, writer, headers):
        key = headers.get("sec-websocket-key")
        try:
            valid_key = key and len(base64.b64decode(key, validate=True)) == 16
        except ValueError:
            valid_key = False
        if not valid_key:
            writer.close()
            return
        resp = ("HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {wsutil.accept_key(key)}\r\n\r\n")
        writer.write(resp.encode())
        await writer.drain()

        conn = Conn(writer)
        player = None
        recent_messages = deque(maxlen=241)
        await conn.send({"t": "welcome", "games": games.GAME_INFO, "mode": self.mode})
        try:
            while True:
                msg = await asyncio.wait_for(wsutil.read_message(reader), 120)
                if msg is None:
                    break
                opcode, data = msg
                if opcode == 0x8:      # close
                    break
                if opcode == 0x9:      # ping -> pong
                    await conn.send_raw(wsutil.encode_frame(data, 0xA))
                    continue
                if opcode == 0xA:
                    continue
                now = time.monotonic()
                recent_messages.append(now)
                if len(recent_messages) == 241 and now - recent_messages[0] < 1:
                    break
                try:
                    obj = json.loads(data.decode())
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                player = await self._on_message(conn, player, obj)
        finally:
            conn.alive = False
            arena = getattr(conn, 'arena', self)
            if hasattr(arena, 'joined_connections'):
                arena.joined_connections.discard(conn)
                if arena.hub:arena.hub.hosts.observe(arena.room_id)
            if player and player.conn is conn:
                await arena._on_disconnect(player)
            try:
                writer.close()
            except Exception:
                pass

    async def _on_message(self, conn, player, obj):
        if self.session_hub:
            return await self.session_hub.message(conn, player, obj)
        t = obj.get("t")

        if t == "login":
            now = time.monotonic()
            while self.failed_logins and self.failed_logins[0] < now - 60:
                self.failed_logins.popleft()
            if conn.login_attempts >= 5 or len(self.failed_logins) >= 120:
                await conn.send({'t': 'login_err', 'msg': 'Zu viele Versuche. Bitte spaeter erneut versuchen.'})
                return player
            code = str(obj.get("code", "")).strip()
            if not secrets.compare_digest(code.encode(), self.login_code.encode()):
                conn.login_attempts += 1
                self.failed_logins.append(now)
                await conn.send({"t": "login_err", "msg": "Falscher oder abgelaufener Login-Code"})
                return player
            conn.authed = True
            await conn.send({"t": "login_ok", "code": code, "auto": bool(obj.get("nick")),
                             "session":self.room_id,"session_name":getattr(self,'room_name',None),"mode":self.mode})
            if obj.get("nick"):                 # Wiederverbinden nach Neuladen
                return await self._claim(conn, player, obj)
            return player

        if not conn.authed:
            return player  # alle weiteren Befehle brauchen den Login-Code

        if t == "nick":
            return await self._claim(conn, player, obj)

        if player is None:
            return player  # alle weiteren Befehle brauchen einen Namen

        if t == "lobby":
            await conn.send(self.lobby_view(player))

        elif t == "challenge":
            await self._challenge(player, obj)

        elif t == "challenge_cancel":
            player.out_challenge = None
            await self.push_lobby()

        elif t == "start_now":
            if player.out_challenge:
                await self._maybe_start(player.out_challenge, force=True)
            await self.push_lobby()

        elif t == "accept":
            await self._accept(player, obj)

        elif t == "decline":
            src = self.by_pid.get(str(obj.get("from", "")))
            c = src.out_challenge if src else None
            if c and player.pid in c.targets:
                del c.targets[player.pid]
                if src.online:
                    await src.conn.send({"t": "info", "msg": f"{player.nick} hat abgelehnt"})
                if not c.targets:
                    src.out_challenge = None
                else:
                    await self._maybe_start(c)
            await self.push_lobby()

        elif t == "in":
            if player.match and not player.match.finished:
                try:
                    player.match.game.set_input(player.role, int(obj.get("u", 0)) & 0x3F)
                except (ValueError, TypeError):
                    pass

        elif t == "leave":
            if player.match and not player.match.finished:
                await player.match.abort(player)

        return player

    async def _claim(self, conn, player, obj):
        """Nickname waehlen: neuer Spieler oder Rueckkehr zu einem bekannten
        (Credits bleiben). Ein gerade verbundener Name kann nur mit dessen
        Schluessel (gleicher Browser) uebernommen werden."""
        nick = " ".join(str(obj.get("nick", "")).split())[:16]
        if not nick:
            await conn.send({"t": "nick_err", "msg": "Bitte einen Namen eingeben"})
            return player
        key = nick_key(nick)
        if key in self.banned:
            await conn.send({"t": "nick_err", "msg": "Dieser Name ist gesperrt"})
            return player
        p = self.players.get(key)
        tok = obj.get("tok")
        if p and p.token_hash and not secrets.compare_digest(
                hashlib.sha256(str(tok or '').encode()).hexdigest(), p.token_hash):
            await conn.send({'t': 'nick_err', 'msg': 'Name reserviert. Nutze denselben Browser oder einen anderen Namen.'})
            return player
        if p and p.online and p.conn is not conn:
            if not (tok and p.tok and secrets.compare_digest(str(tok), p.tok)):
                await conn.send({"t": "nick_err", "msg": "Name ist gerade online - bitte anderen waehlen"})
                return player
            await p.conn.send({"t": "kicked", "msg": "An anderer Stelle angemeldet"})
            p.conn.alive = False
            p.conn.writer.close()
        if player is not None and player is not p and player.conn is conn:
            await self._on_disconnect(player)   # Namenswechsel in derselben Verbindung
        if p is None:
            p = self._add_player(nick)
            self.save()
            self.dashboard.log(f"Neuer Spieler: {nick}")
        p.conn = conn
        p.tok = secrets.token_hex(12)
        # Keep reconnect credentials stable across reloads and server restarts.
        if p.token_hash:
            p.tok = str(tok)
        p.token_hash = hashlib.sha256(p.tok.encode()).hexdigest()
        self.save()
        await conn.send({"t": "nick_ok", "nick": p.nick, "tok": p.tok})
        await conn.send(self.lobby_view(p))
        await self.push_lobby()
        return p

    async def _challenge(self, player, obj):
        """Gegner herausfordern. Bei Mehrspieler-Spielen kann man nacheinander
        bis zu max_players-1 Gegner zur selben Herausforderung hinzufuegen."""
        if self.rules['paused']:
            await player.conn.send({'t':'err','msg':'Die Sitzung ist pausiert.'}); return
        if player.busy:
            return
        if self.mode=='choose' and str(obj.get('game','')) not in self.rules['enabled']:
            await player.conn.send({'t':'err','msg':'Dieses Spiel ist nicht freigegeben.'}); return
        target = self.by_pid.get(str(obj.get("target", "")))
        if not target or target is player:
            await player.conn.send({"t": "err", "msg": "Ungueltige Herausforderung"})
            return
        if self.mode == "choose":
            gid = str(obj.get("game", ""))
            if gid not in games.GAMES:
                await player.conn.send({"t": "err", "msg": "Ungueltige Herausforderung"})
                return
        else:
            gid = None   # Spiel wird erst beim Start zufaellig festgelegt
        if not target.online or target.busy:
            await player.conn.send({"t": "err", "msg": "Gegner nicht verfuegbar"})
            return
        c = player.out_challenge
        if c and c.gid == gid:
            if target.pid in c.targets:
                return
            if len(c.targets) >= self._max_targets(gid):
                await player.conn.send({"t": "err", "msg":
                                        f"Hoechstens {self._max_targets(gid)} Gegner"})
                return
        else:
            c = player.out_challenge = Challenge(player, gid)
        # Wer selbst herausfordert, nimmt keine fremde Herausforderung mehr an.
        for oc in self._withdraw(player, keep=c):
            await self._maybe_start(oc)
        c.targets[target.pid] = "pending"
        await self.push_lobby()
        msg = {"t": "challenged", "from": player.pid, "nick": player.nick}
        if self.mode == "choose":
            msg["gname"] = games.GAMES[gid].name
        await target.conn.send(msg)

    async def _accept(self, player, obj):
        src = self.by_pid.get(str(obj.get("from", "")))
        c = src.out_challenge if src else None
        if not c or player.pid not in c.targets:
            await player.conn.send({"t": "err", "msg": "Herausforderung nicht mehr gueltig"})
            return
        if player.busy or src.busy or not src.online:
            await player.conn.send({"t": "err", "msg": "Nicht mehr verfuegbar"})
            return
        player.out_challenge = None            # eigene Herausforderung zurueckziehen
        for oc in self._withdraw(player, keep=c):
            await self._maybe_start(oc)
        c.targets[player.pid] = "accepted"
        await self._maybe_start(c)
        await self.push_lobby()

    async def _on_disconnect(self, player):
        player.conn = None
        player.out_challenge = None
        for oc in self._withdraw(player):
            await self._maybe_start(oc)
        if player.match and not player.match.finished:
            await player.match.abort(player)
        await self.push_lobby()

    # ----- Admin (laufen auf dem Loop-Thread via run_coroutine_threadsafe) -----
    async def _kick_conn(self, p, msg):
        if p.match and not p.match.finished:
            await p.match.abort(p)
        if p.conn:
            await p.conn.send({"t": "kicked", "msg": msg})
            p.conn.alive = False
            try:
                p.conn.writer.close()
            except Exception:
                pass
            p.conn = None
        p.out_challenge = None
        for oc in self._withdraw(p):
            await self._maybe_start(oc)

    async def admin_ban(self, key):
        p = self.players.get(key)
        if not p:
            return "Unbekannter Spieler"
        self.banned.add(key)
        self.save()
        if p.online or p.match:
            await self._kick_conn(p, "Du wurdest gesperrt")
        await self.push_lobby()
        self.dashboard.log(f"Gesperrt: {p.nick}")
        return f"{p.nick} gesperrt"

    async def admin_unban(self, key):
        if key in self.banned:
            self.banned.discard(key)
            self.save()
            p = self.players.get(key)
            return f"{p.nick if p else key} entsperrt"
        return f"{key} war nicht gesperrt"

    async def admin_kick(self, key):
        p = self.players.get(key)
        if not p:
            return "Unbekannter Spieler"
        if not (p.online or p.match):
            return f"{p.nick} ist nicht verbunden"
        await self._kick_conn(p, "Verbindung durch Spielleitung getrennt")
        await self.push_lobby()
        return f"{p.nick} getrennt"

    async def admin_reset_credits(self, key=None):
        if key:
            p = self.players.get(key)
            if not p:
                return "Unbekannter Spieler"
            p.credits = 0
            p.record = {}
            self.save()
            await self.push_lobby()
            return f"Credits von {p.nick} zurueckgesetzt"
        for p in self.players.values():
            p.credits = 0
            p.record = {}
        self.save()
        await self.push_lobby()
        self.dashboard.log("Alle Credits zurueckgesetzt")
        return "Alle Credits zurueckgesetzt"

    async def admin_clear_players(self):
        """Turnier-Neustart: alle Spieler (Namen, Credits, Sperren) loeschen."""
        for p in list(self.players.values()):
            if p.online or p.match:
                await self._kick_conn(p, "Turnier wurde neu gestartet")
        self.players.clear()
        self.by_pid.clear()
        self.banned.clear()
        self.save()
        self.dashboard.log("Turnier-Neustart: alle Spieler geloescht")

    def admin_list(self):
        rows = []
        for key, p in sorted(self.players.items()):
            rows.append({"key": key, "nick": p.nick, "credits": p.credits,
                         "online": p.online, "busy": p.busy,
                         "banned": key in self.banned,
                         "wl": (sum(r[0] for r in p.record.values()),
                                sum(r[1] for r in p.record.values()))})
        return rows

    async def admin_set_mode(self, mode):
        self.mode = "random" if mode == "random" else "choose"
        self.save()
        await self.push_lobby()
        self.dashboard.log("Modus: " + ("Zufaelliges Spiel" if self.mode == "random"
                                         else "Spiel selbst waehlen"))
        return self.mode

    # ----- Speichern / Laden (benannte Sicherungen) -----
    def admin_save(self, name):
        os.makedirs(self.save_dir, exist_ok=True)
        path = os.path.join(self.save_dir, name + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._state_dict(), f, indent=1)
        os.replace(tmp, path)
        self.dashboard.log("Stand gespeichert: " + name)
        return path

    def admin_list_saves(self):
        if not os.path.isdir(self.save_dir):
            return []
        return sorted(f[:-5] for f in os.listdir(self.save_dir) if f.endswith(".json"))

    async def admin_load(self, name):
        path = os.path.join(self.save_dir, name + ".json")
        if not os.path.exists(path):
            return f"Sicherung '{name}' nicht gefunden"
        with open(path) as f:
            data = json.load(f)
        for m in list(self.matches.values()):await self.control.cancel_match(m)
        for p in list(self.players.values()):
            if p.online or p.match:
                await self._kick_conn(p, "Spielstand wurde neu geladen")
        self._apply_state(data)
        self.save()
        await self.push_lobby()
        self.dashboard.log("Stand geladen: " + name)
        return f"Geladen: {len(self.players)} Spieler, Modus {self.mode}"

    # ----- Lauf -----
    async def serve(self):
        self.loop = asyncio.get_running_loop()
        if self.headless:
            await self._serve_headless()
            return
        if sys.platform == "win32":
            # Python < 3.13 misst unter Windows mit time.monotonic() nur in
            # 15,6-ms-Schritten -> asyncio-Wartezeiten und damit die Spieltakte
            # ruckeln. Die Ereignisschleife bekommt deshalb die hochaufloesende
            # Uhr (zusammen mit timeBeginPeriod(1) in termui.enable_vt).
            self.loop.time = time.perf_counter
            self.loop._clock_resolution = time.get_clock_info("perf_counter").resolution
        srv = None
        # Port 80 braucht unter Linux/macOS Root-Rechte -> dann (oder wenn der
        # Port belegt ist) automatisch auf 8080, 8081, ... ausweichen.
        for port in [self.port] + [p for p in range(8080, 8100) if p != self.port]:
            try:
                srv = await asyncio.start_server(self.handle, self.host, port)
            except OSError as e:
                print(f"  Port {port} nicht nutzbar ({e.strerror or e}) - versuche naechsten ...")
                continue
            if port != self.port:
                print(f"  -> weiche auf Port {port} aus.")
                self.port = port
                await asyncio.sleep(1.5)       # Hinweis kurz lesbar lassen
            break
        if srv is None:
            print("  Kein freier Port gefunden. Bitte mit --port <nummer> starten.")
            return
        asyncio.create_task(self.dashboard.run())
        addrs = ", ".join(str(s.getsockname()) for s in srv.sockets)
        self.dashboard.log(f"Server laeuft auf {addrs}, Login-Code {self.login_code}")
        threading.Thread(target=AdminMenu(self).run, daemon=True).start()
        async with srv:
            await srv.serve_forever()

    async def _serve_headless(self):
        stop = asyncio.Event()
        installed = []
        async def replay_maintenance():
            while not stop.is_set():
                try:await asyncio.wait_for(stop.wait(),3600)
                except asyncio.TimeoutError:await asyncio.to_thread(self.replays.cleanup)
        async def host_maintenance():
            while not stop.is_set():
                if self.session_hub:
                    try:await self.session_hub.hosts.sweep()
                    except Exception:logging.exception('Host session cleanup failed')
                try:await asyncio.wait_for(stop.wait(),10)
                except asyncio.TimeoutError:pass
        maintenance=asyncio.create_task(replay_maintenance())
        hosts_task=asyncio.create_task(host_maintenance())
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                self.loop.add_signal_handler(sig, stop.set)
                installed.append(sig)
            except NotImplementedError:
                pass  # Windows development; Linux Docker supports signal handlers.
        app = admin = None
        try:
            app = await asyncio.start_server(self.handle, self.host, self.port, limit=16384)
            if self.admin_token:
                admin = await asyncio.start_server(self.handle_admin, '127.0.0.1', self.admin_port, limit=8192)
            logging.info('Klassenkampf listening on %s:%s; headless mode', self.host, self.port)
            await stop.wait()
        finally:
            stop.set()
            await maintenance
            await hosts_task
            for listener in (app, admin):
                if listener:
                    listener.close()
                    await listener.wait_closed()
            arenas = [self] + (list(self.session_hub.rooms.values()) if self.session_hub else [])
            match_tasks = []
            for arena in arenas:
                for match in list(arena.matches.values()):
                    match.finished = True
                    if match.task:
                        match.task.cancel()
                        match_tasks.append(match.task)
                    for player in match.players:
                        player.match = None
                        player.role = 0
                arena.matches.clear()
            if match_tasks:
                await asyncio.gather(*match_tasks, return_exceptions=True)
            for arena in arenas:
                if arena.worker: await arena.worker.stop()
            await self.replays.drain()
            for writer in list(self.connections):
                writer.close()
            self.save()
            if self.session_hub:
                for room in self.session_hub.rooms.values():
                    room.save()
            for sig in installed:
                self.loop.remove_signal_handler(sig)
            logging.info('State saved; server stopped')


def _setup(args):
    """Interaktive Einrichtung mit sinnvollen Defaults (keine Parameter noetig)."""
    tty = sys.stdin.isatty()
    saved = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                saved = json.load(f)
        except (ValueError, OSError):
            saved = {}
    existing = bool(saved.get("players") or saved.get("codes"))

    def ask(text, default):
        if not tty:
            return str(default)
        try:
            v = input(f"  {text} [{default}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return str(default)
        return v or str(default)

    if tty:
        print("\n  \x1b[38;2;120;230;255m\x1b[1m-- Klassenkampf - Einrichtung ----------------------------\x1b[0m")

    port = args.port if args.port is not None else int(ask("Port", 80) or 80)

    reset = args.reset
    if existing and not reset:
        if ask("Vorhandene Spieler & Credits behalten? (j/n)", "j").lower().startswith("n"):
            reset = True

    # Modus wird nicht beim Start abgefragt (im Menue umschaltbar).
    mode = args.mode or saved.get("mode", "choose")

    if tty:
        print("  \x1b[38;2;120;230;255m--------------------------------------------------------\x1b[0m\n")
    return port, reset, mode


def main():
    ap = argparse.ArgumentParser(description="Klassenkampf Multiplayer-Server")
    ap.add_argument("--host", default=os.environ.get('KLASSENKAMPF_HOST', '0.0.0.0'))
    ap.add_argument("--port", type=int, default=int(os.environ.get('KLASSENKAMPF_PORT', '8080')))
    ap.add_argument('--headless', action='store_true', default=os.environ.get('KLASSENKAMPF_HEADLESS') == '1')
    ap.add_argument('--data-dir', default=os.environ.get('KLASSENKAMPF_DATA_DIR', APP_DIR))
    ap.add_argument("--mode", choices=["choose", "random"], default=None)
    ap.add_argument("--reset", action="store_true",
                    help="alle Spieler/Credits verwerfen (state.json ueberschreiben)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    configure_data_dir(args.data_dir)
    if args.headless:
        port, reset, mode = args.port, args.reset, args.mode or 'choose'
    else:
        termui.enable_vt()
        port, reset, mode = _setup(args)
    admin_token = os.environ.get('KLASSENKAMPF_ADMIN_TOKEN')
    login_code = os.environ.get('KLASSENKAMPF_LOGIN_CODE')
    if args.headless and (not admin_token or not re.fullmatch(r'[!-~]{32,256}', admin_token)
                          or not login_code or not re.fullmatch(r'[!-~]{12,128}', login_code)):
        ap.error('Headless mode requires KLASSENKAMPF_ADMIN_TOKEN (32-256 ASCII characters) and KLASSENKAMPF_LOGIN_CODE (12-128 ASCII characters), without spaces')
    origin = os.environ.get('KLASSENKAMPF_PUBLIC_ORIGIN')
    server = Server(args.host, port, reset, mode, headless=args.headless,
                    login_code=login_code, admin_token=admin_token, public_origin=origin, sessions=True)
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        if args.headless:
            return
        # Terminal sauber hinterlassen (Bildschirm loeschen, Cursor zeigen)
        sys.stdout.write("\x1b[2J\x1b[H\x1b[?25h\x1b[0m")
        sys.stdout.flush()
        print("Klassenkampf beendet. (Tipp: im Menue mit 'q' sauber beenden)")
        for line in server.duration_report():
            print(line)


if __name__ == "__main__":
    main()
