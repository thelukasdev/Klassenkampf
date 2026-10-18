"""Asynchronous session worker transport. Never exposes listening ports."""
import asyncio
import os
from pathlib import Path
import sys
import games

class SessionWorker:
    def __init__(self):
        self.process=None
        self.lock=asyncio.Lock()
        self.ids=set()
        self.failures=0
        self.last_error_at=0
    async def request(self,obj):
        # Cancellation must not leave a reply in the shared session pipe.
        task=asyncio.create_task(self._request(obj))
        try:return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:await asyncio.shield(task)
            except Exception:pass
            raise
    async def _request(self, obj):
        import json
        async with self.lock:
            try:
                if self.process is None:
                    if obj['op']!='create': raise RuntimeError('Worker unavailable')
                    self.process=await asyncio.create_subprocess_exec(sys.executable,'-u',str(Path(__file__).with_name('session_worker.py')),
                        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
                        env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','PYTHONDONTWRITEBYTECODE')},limit=1024*1024)
                p=self.process
                if p.returncode is not None: raise RuntimeError('Worker stopped')
                p.stdin.write((json.dumps(obj)+'\n').encode())
                await asyncio.wait_for(p.stdin.drain(),2)
                data=await asyncio.wait_for(p.stdout.readline(),3)
                result=json.loads(data)
                if not result.get('ok'): raise RuntimeError('Worker rejected request')
                if obj['op']=='create': self.ids.add(str(obj['id']))
                if obj['op']=='drop':
                    self.ids.discard(str(obj['id']))
                    if not self.ids: await self._stop()
                return result
            except BaseException:
                import time
                self.last_error_at=time.time()
                self.failures+=1
                await self._stop()
                raise
    async def _stop(self):
        p=self.process; self.process=None; self.ids.clear()
        if p:
            if p.returncode is None:
                try: p.kill()
                except ProcessLookupError: pass
            await p.wait()
    async def stop(self):
        async with self.lock: await self._stop()

class RemoteGame:
    def __init__(self, worker, key, gid, n):
        self.worker=worker; self.key=str(key); self.gid=gid; self.n=n
        self.tick_ms=games.GAMES[gid].tick_ms
        self.per_view=games.GAMES[gid].per_view
        self.result=None; self.commands=[]; self.snapshots={}; self.ready=False
    def set_input(self,p,mask):
        # Accumulate edges while bounding messages from a noisy client.
        if len(self.commands)<256:self.commands.append(['input',p,mask])
    def remove_player(self,p): self.commands.append(['remove',p])
    async def step(self,speed=1):
        if not self.ready:
            self.ready=True
            await self.worker.request({'op':'create','id':self.key,'gid':self.gid,'n':self.n})
        commands,self.commands=self.commands,[]
        out=await self.worker.request({'op':'tick','id':self.key,'commands':commands,'ticks':speed})
        self.result=out['result'];self.snapshots=out['snapshots']
    def snapshot(self,view=0):return self.snapshots[str(view if self.per_view else 0)]
    async def close(self):
        if self.ready and self.key in self.worker.ids:
            await self.worker.request({'op':'drop','id':self.key})
