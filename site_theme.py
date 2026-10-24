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
    if key=='newyear':return NEWYEAR_CSS.encode('utf-8')
    css = f"""/* Public template: {key} */
.season-fireworks{{display:none}}
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


# Decorative only: leave the existing page colors, typography and controls intact.
NEWYEAR_CSS = """/* Public template: newyear */
.season-fireworks{display:none;position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:0}
body:has(#login.active)>.season-fireworks,body.public-theme>.season-fireworks{display:block}
#login{isolation:isolate;background:transparent}
#login .season-mark,#login .season-label{display:none}
body:has(#login.active) #login{z-index:1}
body.public-theme>header,body.public-theme>main,body.public-theme>footer{position:relative;z-index:1}
.season-fireworks span{position:absolute;left:12%;top:22%;width:1px;height:1px;--delay:0s;--spark:#eccd82}
.season-fireworks span:nth-child(2){left:86%;top:36%;--delay:-2.7s;--spark:#a9d9ef}
.season-fireworks span:nth-child(3){left:64%;top:15%;--delay:-5.3s;--spark:#c5afe8}
.season-fireworks span::before{content:'';position:absolute;width:3px;height:42px;border-radius:50%;background:linear-gradient(transparent,var(--spark));box-shadow:0 4px 9px var(--spark);animation:season-launch 8s linear infinite;animation-delay:var(--delay)}
.season-fireworks span::after{content:'';position:absolute;left:-65px;top:-65px;width:130px;height:130px;background:radial-gradient(circle at 50% 4%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 73% 10%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 90% 27%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 96% 50%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 90% 73%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 73% 90%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 50% 96%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 27% 90%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 10% 73%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 4% 50%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 10% 27%,var(--spark) 0 2px,transparent 3px),radial-gradient(circle at 27% 10%,var(--spark) 0 2px,transparent 3px);animation:season-burst 8s ease-out infinite;animation-delay:var(--delay)}
@keyframes season-launch{0%{opacity:0;transform:translateY(90vh)}3%{opacity:.5}18%{opacity:.65;transform:translateY(0)}19%,100%{opacity:0;transform:translateY(0)}}
@keyframes season-burst{0%,18%{opacity:0;transform:scale(.08)}20%{opacity:.55;transform:scale(.15)}36%{opacity:.35;transform:scale(1.25) translateY(8px)}48%,100%{opacity:0;transform:scale(1.6) translateY(20px)}}
@media(prefers-reduced-motion:reduce){.season-fireworks{display:none!important}}
"""
