"""Bounded static-file cache, conditional requests and negotiated gzip delivery."""
from collections import OrderedDict
import gzip
import hashlib
import threading
from pathlib import Path

class StaticDelivery:
    LIMIT=16*1024*1024
    def __init__(self):
        self.entries=OrderedDict();self.bytes=0;self.lock=threading.RLock()

    def load(self,path,embedded=None):
        with self.lock:return self._load(path,embedded)

    def _load(self,path,embedded=None):
        path=Path(path)
        stamp=(path.stat().st_mtime_ns,path.stat().st_size) if embedded is None else id(embedded)
        key=str(path);cached=self.entries.get(key)
        if cached and cached[0]==stamp:
            self.entries.move_to_end(key);return cached[1:]
        body=path.read_bytes() if embedded is None else embedded
        compressed=None
        if path.suffix in ('.html','.css','.js','.svg','.json') and len(body)>=512:
            candidate=gzip.compress(body,compresslevel=5,mtime=0)
            if len(candidate)<len(body):compressed=candidate
        digest=hashlib.sha256(body).hexdigest()[:32]
        size=len(body)+len(compressed or b'')
        if cached:self.bytes-=len(cached[1])+len(cached[2] or b'');del self.entries[key]
        if size<=self.LIMIT:
            while self.entries and (self.bytes+size>self.LIMIT or len(self.entries)>=128):
                _,old=self.entries.popitem(last=False);self.bytes-=len(old[1])+len(old[2] or b'')
            self.entries[key]=(stamp,body,compressed,digest);self.bytes+=size
        return body,compressed,digest

    @staticmethod
    def gzip_allowed(value):
        encodings={}
        for part in value.lower().split(','):
            bits=part.strip().split(';');quality=1.0
            try:
                for parameter in bits[1:]:
                    if parameter.strip().startswith('q='):quality=float(parameter.strip()[2:])
            except ValueError:quality=0
            encodings[bits[0].strip()]=quality
        return encodings.get('gzip',encodings.get('*',0))>0

    def response(self,path,ctype,method,headers,embedded=None):
        raw,compressed,digest=self.load(path,embedded)
        zipped=compressed is not None and self.gzip_allowed(headers.get('accept-encoding',''))
        body=compressed if zipped else raw
        public=Path(path).suffix in ('.css','.js','.svg','.png','.ico','.webp','.woff2')
        etag='"'+digest+('-gzip' if zipped else '')+'"'
        tags=[v.strip().removeprefix('W/') for v in headers.get('if-none-match','').split(',')]
        unchanged=public and (etag in tags or '*' in tags)
        lines=['HTTP/1.1 '+('304 Not Modified' if unchanged else '200 OK'),
               'Content-Type: '+ctype,'Cache-Control: '+('public, max-age=0, must-revalidate' if public else 'no-store'),
               'Vary: Accept-Encoding','X-Content-Type-Options: nosniff','Connection: close']
        if public:lines.append('ETag: '+etag)
        if zipped:lines.append('Content-Encoding: gzip')
        if not unchanged:lines.append('Content-Length: '+str(len(body)))
        return ('\r\n'.join(lines)+'\r\n\r\n').encode()+(b'' if unchanged or method=='HEAD' else body)

delivery=StaticDelivery()
