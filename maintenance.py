"""Persistent maintenance switch with automatic expiry and a minimal public page."""
import html
import json
import os
import tempfile
import time
from pathlib import Path

DEFAULT={'enabled':False,'message':'Wir führen gerade Wartungsarbeiten durch. Bitte versuche es später erneut.','ends_at':None}

def read(root):
    try:
        obj=json.loads((Path(root)/'maintenance.json').read_text(encoding='utf-8'))
        if not isinstance(obj,dict) or type(obj.get('enabled')) is not bool:raise ValueError()
        if not isinstance(obj.get('message'),str) or len(obj['message'])>500:raise ValueError()
        end=obj.get('ends_at')
        if end is not None and (type(end) is not int or end<0):raise ValueError()
        return {**obj,'enabled':obj['enabled'] and (end is None or end>time.time())}
    except (OSError,ValueError,TypeError):return dict(DEFAULT)

def save(root,obj):
    if not isinstance(obj,dict) or type(obj.get('enabled')) is not bool:raise ValueError('Wartungsmodus ungültig.')
    msg=obj.get('message','')
    if not isinstance(msg,str) or not 1<=len(msg.strip())<=500:raise ValueError('Bitte eine Meldung mit 1 bis 500 Zeichen eingeben.')
    end=obj.get('ends_at')
    if end is not None and (type(end) is not int or end<=time.time() or end>time.time()+366*86400):raise ValueError('Das geplante Ende muss in der Zukunft liegen (maximal ein Jahr).')
    data={'enabled':obj['enabled'],'message':msg.strip(),'ends_at':end}
    fd,name=tempfile.mkstemp(prefix='.maintenance-',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
        os.replace(name,Path(root)/'maintenance.json')
    finally:
        if os.path.exists(name):os.unlink(name)
    return data

async def respond(writer,method,state):
    from datetime import datetime,timezone
    end=''
    if state.get('ends_at'):
        stamp=datetime.fromtimestamp(state['ends_at'],timezone.utc)
        end='<p>Geplantes Ende: <time datetime="'+stamp.isoformat()+'">'+stamp.strftime('%d.%m.%Y, %H:%M')+' Uhr UTC</time></p>'
    body=('<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wartungsarbeiten · Klassenkampf</title><link rel="icon" href="/lp-icon.png"><link rel="stylesheet" href="/maintenance.css"><script src="/maintenance-time.js" defer></script></head><body><main><img src="/lp-logo-small.webp" alt="LP" width="88" height="88"><h1>Wartungsarbeiten</h1><p>'+html.escape(state['message'])+'</p>'+end+'<a href="/status">Netzwerkstatus ansehen</a></main></body></html>').encode()
    retry=max(30,min(86400,int(state['ends_at']-time.time()))) if state.get('ends_at') else 300
    headers=(f'HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\nRetry-After: {retry}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n'
             "Content-Security-Policy: default-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'\r\nConnection: close\r\n\r\n")
    writer.write(headers.encode()+(b'' if method=='HEAD' else body));await writer.drain()
