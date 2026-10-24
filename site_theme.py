"""Fixed public-page templates; configuration contains only an allowlisted identifier."""
import json
import os
import tempfile
from pathlib import Path

THEMES = {
    'default': ('Standard', '', '', '#0a0d0a', '#14201a', '#121a20', '#73d363', '#9de7df'),
    'halloween': ('Halloween', '🎃', 'HALLOWEEN EDITION', '#100d18', '#352039', '#211a29', '#f2a35e', '#e7b9f5'),
    'christmas': ('Weihnachten', '🎄', 'WEIHNACHTSZEIT', '#091511', '#163c2b', '#14251e', '#f2cf81', '#b5e9d0'),
    'newyear': ('Silvester', '✨', 'BEREIT FÜR DIE NÄCHSTE RUNDE', '#0e1020', '#30244c', '#1a1b31', '#efd282', '#c7beff'),
    'easter': ('Ostern', '🥚', 'FROHE OSTERN', '#12131e', '#313047', '#232333', '#cbb5ff', '#aee4c2'),
    'summer': ('Sommer', '☀️', 'SOMMERZEIT', '#081923', '#124450', '#122b36', '#ffcf78', '#8be6eb'),
    'autumn': ('Herbst', '🍂', 'HERBSTZEIT', '#18110c', '#40301b', '#2b2119', '#eeb775', '#e6ce9b'),
    'winter': ('Winter', '❄️', 'WINTERZEIT', '#0c1520', '#233e55', '#182936', '#a9daff', '#c6ebff'),
}

def current(data_dir):
    try:
        value=json.loads((Path(data_dir)/'site-theme.json').read_text(encoding='utf-8'))
        if isinstance(value,str) and value in THEMES:return value
    except (OSError,ValueError,TypeError):pass
    return 'halloween'

def save(data_dir,value):
    if not isinstance(value,str) or value not in THEMES:raise ValueError('Unbekannte Designvorlage.')
    root=Path(data_dir)
    fd,name=tempfile.mkstemp(prefix='.site-theme-',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f);f.flush();os.fsync(f.fileno())
        os.replace(name,root/'site-theme.json')
    finally:
        if os.path.exists(name):os.unlink(name)

def overview(data_dir):
    return {'selected':current(data_dir),'templates':[{'id':key,'name':v[0],'icon':v[1]} for key,v in THEMES.items()]}

def stylesheet(data_dir):
    key=current(data_dir)
    name,icon,label,bg,glow,panel,accent,link=THEMES[key]
    css = f"""/* Public template: {key} */
#login,body.public-theme{{--theme-bg:{bg};--theme-glow:{glow};--theme-panel:{panel};--theme-accent:{accent};--theme-link:{link};}}
#login{{background:radial-gradient(ellipse at 50% 0,var(--theme-glow),var(--theme-bg) 75%);}}
#login::before,#login::after{{display:none}}
#login .logo{{color:#f3f0f5;text-shadow:none}}#login .logo .w{{color:var(--theme-accent)}}
#login .season-mark{{height:56px;font-size:42px;line-height:56px}}#login .season-mark::before{{content:'{icon}'}}
#login .season-label{{color:var(--theme-link);font-size:11px;letter-spacing:2px}}#login .season-label::before{{content:'{label}'}}
#login .card{{background:var(--theme-panel);border-color:var(--theme-accent);box-shadow:0 20px 65px #0005}}
#login .card h2{{color:#f3f0f5}}#login input:focus{{border-color:var(--theme-accent);box-shadow:0 0 0 2px var(--theme-accent)}}
#login .btn.primary{{background:var(--theme-accent);color:#171923;border-color:var(--theme-accent)}}
#login .demo-launch{{color:var(--theme-link);border-color:var(--theme-glow);background:var(--theme-bg)}}
body:has(#login.active) .account-nav a{{background:{panel};border-color:{accent};color:{link}}}
body.public-theme{{background:radial-gradient(900px 500px at 50% 0,var(--theme-glow),var(--theme-bg));color:#e8ece8;--cyan:var(--theme-link)}}
body.public-theme a,body.public-theme h1,body.public-theme h2{{color:var(--theme-link)}}
body.public-theme main.legal-content,body.public-theme .component,body.public-theme .session{{background:var(--theme-panel)}}
body.public-theme header{{border-bottom:1px solid var(--theme-glow)}}
body.public-theme .brand::after{{content:'{icon}';font-size:24px}}
@media(max-height:620px){{#login .season-mark{{height:34px;line-height:34px;font-size:30px}}}}
"""
    if key=='default':css+='#login .season-mark,#login .season-label{display:none}\n'
    return css.encode('utf-8')
