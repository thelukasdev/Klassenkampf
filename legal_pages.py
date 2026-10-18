"""Public legal pages with operator data kept outside the source repository."""
import html
import json
from pathlib import Path
from string import Template

FIELDS=('name','street','postal_code','city','country','email','hosting_provider','hosting_location','updated')


def render(page,data_dir):
    config=json.loads((Path(data_dir)/'legal.json').read_text(encoding='utf-8'))
    if not isinstance(config,dict):raise ValueError('Invalid legal configuration')
    if config.get('published') is not True:raise ValueError('Legal configuration not published')
    if any(not isinstance(config.get(k),str) or not config[k].strip() or len(config[k])>500 for k in FIELDS):
        raise ValueError('Incomplete legal configuration')
    from web_admin import AdminStore
    AdminStore.email(config['email'])
    values={k:html.escape(config[k],quote=True) for k in FIELDS}
    template=Path(__file__).with_name('templates')/('impressum.html' if page=='impressum' else 'datenschutz.html')
    return Template(template.read_text(encoding='utf-8')).substitute(values).encode('utf-8')


async def serve(writer,method,page,data_dir):
    try:body=render(page,data_dir);status='200 OK'
    except (OSError,ValueError,KeyError,TypeError):
        body=b'<!doctype html><html lang="de"><meta charset="utf-8"><title>Rechtliche Angaben</title><p>Rechtliche Angaben sind noch nicht konfiguriert.</p><a href="/">Zum Spiel</a></html>'
        status='503 Service Unavailable'
    headers=(f'HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\n'
             'Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n'
             "Content-Security-Policy: default-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'\r\n"
             'Connection: close\r\n\r\n')
    writer.write(headers.encode()+(b'' if method=='HEAD' else body));await writer.drain();writer.close()
