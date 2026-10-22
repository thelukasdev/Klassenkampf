"""Versioned read-only integration API with an independent bearer credential."""
import json
from pathlib import Path
import secrets
import time
from collections import deque


class API:
    def __init__(self, server, keyfile):
        self.server=server;self.keyfile=Path(keyfile)
        self.windows={name:deque() for name in ('public','private','invalid')}

    def allow(self, kind, limit):
        now=time.monotonic();q=self.windows[kind]
        while q and q[0]<=now-60:q.popleft()
        if len(q)>=limit:return False
        q.append(now);return True

    async def respond(self, writer, status, data, method='GET', extra=''):
        body=json.dumps(data,ensure_ascii=False).encode()
        reason={200:'OK',401:'Unauthorized',404:'Not Found',405:'Method Not Allowed',429:'Too Many Requests',503:'Service Unavailable'}[status]
        writer.write((f'HTTP/1.1 {status} {reason}\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Length: {len(body)}\r\nConnection: close\r\n'+extra+'\r\n').encode()+(b'' if method=='HEAD' else body))
        await writer.drain()

    async def handle(self, writer, method, path, headers):
        public=path in ('/api/v1/status','/api/v1/games','/api/openapi.json')
        if not public:
            try:
                with self.keyfile.open('r',encoding='ascii') as stream:key=stream.read(513).strip()
            except (OSError,UnicodeError):key=''
            if not 40<=len(key)<=128:
                await self.respond(writer,503,{'error':'api_not_configured'},method);return
            if not secrets.compare_digest(headers.get('authorization','').encode(),('Bearer '+key).encode()):
                limited=not self.allow('invalid',60)
                await self.respond(writer,429 if limited else 401,{'error':'rate_limited' if limited else 'unauthorized'},method,'Retry-After: 60\r\n' if limited else 'WWW-Authenticate: Bearer\r\n');return
        if not self.allow('public' if public else 'private',600 if public else 120):
            await self.respond(writer,429,{'error':'rate_limited'},method,'Retry-After: 60\r\n');return
        if method!='GET':
            await self.respond(writer,405,{'error':'method_not_allowed'},method,'Allow: GET\r\n');return
        if path=='/api/openapi.json':
            data=json.loads((Path(__file__).parent/'static/openapi.json').read_text(encoding='utf-8'))
        elif path=='/api/v1/status':data={'version':'1','status':'operational'}
        elif path=='/api/v1/games':
            import games
            data={'games':[{'id':g['id'],'name':g['name'],'min_players':g['min'],'max_players':g['max']} for g in games.GAME_INFO]}
        elif path in ('/api/v1/sessions','/api/v1/results'):
            from status_snapshot import snapshot
            if path.endswith('/sessions'):data={'sessions':snapshot(self.server)['sessions'][:200]}
            else:
                rooms=list(self.server.session_hub.rooms.values()) if self.server.session_hub else [self.server]
                counts={}
                for room in rooms:
                    for row in room.history:
                        gid=row.get('game','unknown');counts[gid]=counts.get(gid,0)+1
                data={'completed_matches':sum(counts.values()),'games':[{'id':k,'completed_matches':v} for k,v in sorted(counts.items())],'scope':'currently_loaded_sessions'}
        else:
            await self.respond(writer,404,{'error':'not_found'},method);return
        await self.respond(writer,200,data,method)
