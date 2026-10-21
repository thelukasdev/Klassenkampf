"""Small bounded Prometheus exporter; never label player identities or arbitrary URLs."""
import time
from pathlib import Path
from urllib.parse import urlsplit

BUCKETS=(.01,.05,.1,.25,.5,1,2.5,5)

class Metrics:
    def __init__(self,server):
        self.server=server;self.requests={};self.buckets=[0]*len(BUCKETS)
        self.count=0;self.seconds=0.;self.errors=0;self.exceptions=0;self.websocket_connections=0;self.websocket_disconnects=0

    @staticmethod
    def kind(path):
        path=urlsplit(path).path
        for prefix,label in [('/auth/','auth'),('/api/admin/','admin'),('/api/player/','player'),('/api/beamer','projection'),('/api/watch','spectator'),('/api/replay','replay'),('/healthz','health')]:
            if path.startswith(prefix):return label
        return 'static'

    def observe(self,path,seconds):
        label=self.kind(path);self.requests[label]=self.requests.get(label,0)+1
        self.count+=1;self.seconds+=seconds
        for index,bound in enumerate(BUCKETS):
            if seconds<=bound:self.buckets[index]+=1

    def render(self):
        s=self.server;rooms=list(s.session_hub.rooms.values()) if s.session_hub else [s]
        workers=[r.worker for r in rooms if r.worker]
        lines=[]
        def gauge(name,help,value):
            lines.extend([f'# HELP kk_{name} {help}',f'# TYPE kk_{name} gauge',f'kk_{name} {value}'])
        gauge('uptime_seconds','Application uptime in seconds.',round(time.monotonic()-s.started_at,3))
        gauge('sessions_active','Active sessions, without session identifiers.',sum(getattr(r,'room_active',True) for r in rooms))
        gauge('players_online','Online players across sessions.',sum(sum(p.online for p in r.players.values()) for r in rooms))
        gauge('matches_active','Active games across sessions.',sum(len(r.matches) for r in rooms))
        gauge('connections','Current application connections.',len(s.connections))
        gauge('workers_active','Active game worker processes.',sum(bool(w.process and w.process.returncode is None) for w in workers))
        gauge('worker_errors','Worker failures across currently loaded sessions.',sum(w.failures for w in workers))
        gauge('worker_error_last_timestamp_seconds','Most recent worker failure timestamp.',max((w.last_error_at for w in workers),default=0))
        try:
            used=int(Path('/sys/fs/cgroup/memory.current').read_text())
            gauge('memory_bytes','Application container memory usage in bytes.',used)
        except (OSError,ValueError):pass
        lines.extend(['# HELP kk_http_requests_total Completed HTTP requests by fixed route group.','# TYPE kk_http_requests_total counter'])
        for kind in ('auth','admin','player','projection','spectator','replay','health','static'):
            lines.append(f'kk_http_requests_total{{kind="{kind}"}} {self.requests.get(kind,0)}')
        for name,value in [('http_errors_total',self.errors),('handler_exceptions_total',self.exceptions),('websocket_connections_total',self.websocket_connections),('websocket_disconnects_total',self.websocket_disconnects)]:
            lines.extend([f'# HELP kk_{name} Cumulative count since application startup.',f'# TYPE kk_{name} counter',f'kk_{name} {value}'])
        lines.extend(['# HELP kk_http_duration_seconds HTTP processing time, excluding WebSocket lifetimes.','# TYPE kk_http_duration_seconds histogram'])
        for bound,value in zip(BUCKETS,self.buckets):lines.append(f'kk_http_duration_seconds_bucket{{le="{bound}"}} {value}')
        lines.extend([f'kk_http_duration_seconds_bucket{{le="+Inf"}} {self.count}',f'kk_http_duration_seconds_sum {self.seconds}',f'kk_http_duration_seconds_count {self.count}'])
        return ('\n'.join(lines)+'\n').encode()


def dashboard_url():
    import os
    url=os.environ.get('KLASSENKAMPF_MONITORING_URL','')
    parts=urlsplit(url)
    if parts.scheme=='https' and (parts.hostname or '').endswith('.grafana.net') and not parts.username and not parts.password and not parts.query and not parts.fragment and parts.port in (None,443):return url
    return ''
