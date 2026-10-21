"""Server-side Cloudflare Turnstile verification for new registrations."""
import asyncio
import json
from pathlib import Path
import urllib.parse
import urllib.request

class Turnstile:
    ENDPOINT='https://challenges.cloudflare.com/turnstile/v0/siteverify'
    def __init__(self,web):
        path=Path(web.store.path).parent/'turnstile.json'
        self.sitekey='';self.secret='';self.hostname=urllib.parse.urlsplit(web.origin).hostname
        self.slots=asyncio.Semaphore(4)
        if path.exists():
            config=json.loads(path.read_text(encoding='utf-8'))
            self.sitekey=config.get('sitekey','');self.secret=config.get('secret','')
            if not all(isinstance(x,str) and x and len(x)<=256 for x in (self.sitekey,self.secret)):raise ValueError('Turnstile-Konfiguration unvollständig.')

    def request(self,token):
        data=urllib.parse.urlencode({'secret':self.secret,'response':token}).encode()
        request=urllib.request.Request(self.ENDPOINT,data=data,headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with urllib.request.urlopen(request,timeout=8) as response:
            return json.loads(response.read(16384))

    async def verify(self,token):
        if not self.sitekey:return
        if not isinstance(token,str) or not 1<=len(token)<=2048:raise ValueError('Bitte die Sicherheitsprüfung abschließen.')
        if self.slots.locked():raise ValueError('Sicherheitsprüfung ausgelastet. Bitte gleich erneut versuchen.')
        try:
            async with self.slots:result=await asyncio.to_thread(self.request,token)
        except Exception:raise ValueError('Sicherheitsprüfung momentan nicht erreichbar. Bitte erneut versuchen.') from None
        if not isinstance(result,dict) or result.get('success') is not True or result.get('hostname')!=self.hostname or result.get('action')!='register':
            raise ValueError('Sicherheitsprüfung fehlgeschlagen oder abgelaufen. Bitte erneut versuchen.')
