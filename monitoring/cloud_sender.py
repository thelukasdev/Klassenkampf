"""Small, bounded Grafana Cloud metrics sender using the documented Influx API."""
import base64
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def config(path):
    value=json.loads(Path(path).read_text())
    url=urllib.parse.urlsplit(value['endpoint'])
    if url.scheme!='https' or not (url.hostname or '').endswith('.grafana.net') or url.username or url.password or url.port not in (None,443) or url.path!='/api/v1/push/influx/write' or url.query or url.fragment:
        raise ValueError('A direct HTTPS Grafana Cloud Influx write endpoint is required.')
    if not re.fullmatch(r'[0-9]{1,20}',value['instance_id']):raise ValueError('Invalid metrics instance ID.')
    if not isinstance(value['token'],str) or not 10<=len(value['token'])<=4096:raise ValueError('Invalid write token.')
    return value

def line(name,value,tags=None):
    if not re.fullmatch(r'(kk|node)_[a-zA-Z0-9_]+',name) or not math.isfinite(float(value)):raise ValueError('Invalid metric.')
    measurement,field=name.split('_',1)
    def escape(text):return str(text).replace('\\','\\\\').replace(' ','\\ ').replace(',','\\,').replace('=','\\=')
    tagtext=''.join(','+escape(key)+'='+escape(value) for key,value in sorted((tags or {}).items()))
    return measurement+tagtext+' '+field+'='+str(float(value))

METRIC=re.compile(r'^(kk_[a-zA-Z0-9_]+)(?:\{(.*)\})? ([0-9.eE+\-]+)$')
ALLOWED={'kk_uptime_seconds','kk_sessions_active','kk_players_online','kk_matches_active','kk_connections','kk_workers_active','kk_worker_errors','kk_worker_error_last_timestamp_seconds','kk_memory_bytes','kk_http_requests_total','kk_http_errors_total','kk_handler_exceptions_total','kk_websocket_connections_total','kk_websocket_disconnects_total','kk_http_duration_seconds_bucket','kk_http_duration_seconds_sum','kk_http_duration_seconds_count'}

def app_lines(text):
    result=[]
    for raw in text.splitlines():
        if raw.startswith('#'):continue
        match=METRIC.fullmatch(raw)
        if not match or match[1] not in ALLOWED:continue
        tags={'job':'klassenkampf'}
        if match[2]:
            # The source has exactly two fixed, bounded label vocabularies.
            labels=re.fullmatch(r'(kind|le)="([a-z0-9.+]+|\+Inf)"',match[2])
            if not labels:continue
            if labels[1]=='kind' and labels[2] not in {'auth','admin','player','projection','spectator','replay','health','static'}:continue
            if labels[1]=='le' and labels[2] not in {'0.01','0.05','0.1','0.25','0.5','1','2.5','5','+Inf'}:continue
            tags[labels[1]]=labels[2]
        result.append(line(match[1],match[3],tags))
    if not result:raise ValueError('No application metrics received.')
    return result

def host_lines(proc=Path('/proc'),disk='/'):
    memory={key:int(value.split()[0])*1024 for key,value in (row.split(':',1) for row in (proc/'meminfo').read_text().splitlines())}
    result=[line('node_memory_MemTotal_bytes',memory['MemTotal']),line('node_memory_MemAvailable_bytes',memory['MemAvailable'])]
    hz=os.sysconf('SC_CLK_TCK');modes=('user','nice','system','idle','iowait','irq','softirq','steal')
    for row in (proc/'stat').read_text().splitlines():
        fields=row.split()
        if fields and re.fullmatch(r'cpu[0-9]{1,2}',fields[0]):
            for mode,count in zip(modes,fields[1:]):result.append(line('node_cpu_seconds_total',int(count)/hz,{'cpu':fields[0][3:],'mode':mode}))
    usage=shutil.disk_usage(disk)
    result.extend([line('kk_disk_avail_bytes',usage.free),line('kk_disk_size_bytes',usage.total)])
    return result

def collect(status_token,opener):
    rows=[]
    try:
        request=urllib.request.Request('http://app:8080/internal/metrics',headers={'Authorization':'Bearer '+status_token})
        with opener.open(request,timeout=5) as response:text=response.read(65537)
        if len(text)>65536:raise ValueError('Metrics response too large.')
        rows.extend(app_lines(text.decode()));rows.append(line('kk_app_up',1))
    except (OSError,ValueError):rows.append(line('kk_app_up',0))
    try:rows.extend(host_lines());rows.append(line('kk_host_up',1))
    except (OSError,ValueError,KeyError):rows.append(line('kk_host_up',0))
    rows.append(line('kk_collector_heartbeat_timestamp_seconds',time.time()))
    body=('\n'.join(rows)+'\n').encode()
    if len(body)>65536:raise ValueError('Metrics batch too large.')
    return body

def push(value,body,opener):
    auth=base64.b64encode((value['instance_id']+':'+value['token']).encode()).decode()
    request=urllib.request.Request(value['endpoint'],data=body,headers={'Content-Type':'text/plain','Authorization':'Basic '+auth},method='POST')
    with opener.open(request,timeout=8) as response:
        if not 200<=response.status<300:raise ValueError('Metrics write failed.')
        response.read(1024)

def main():
    value=config('/run/secrets/grafana-cloud.json');token=Path('/run/secrets/status-token').read_text().strip()
    stop=threading.Event();opener=urllib.request.build_opener(NoRedirect)
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    while not stop.is_set():
        started=time.monotonic()
        try:push(value,collect(token,opener),opener);print('Cloud metrics sent.',flush=True)
        except Exception:print('Cloud metrics could not be sent; retrying next interval.',flush=True)
        stop.wait(max(1,60-(time.monotonic()-started)))

if __name__=='__main__':main()
