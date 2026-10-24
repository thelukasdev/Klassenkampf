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
.season-fireworks,.season-christmas,.season-scenery{{display:none}}
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
    if key=='christmas':css+=CHRISTMAS_CSS
    elif key in SCENERY:css+=scenery_css(key,bg,glow)
    return css.encode('utf-8')


# Decorative only: leave the existing page colors, typography and controls intact.
NEWYEAR_CSS = """/* Public template: newyear */
.season-christmas,.season-scenery{display:none}
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


CHRISTMAS_CSS = """
/* Quiet animated scenery, behind public-page content only. */
body:has(#login.active)>.season-christmas,body.public-theme>.season-christmas{display:block}
.season-christmas{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
body:has(#login.active){background:radial-gradient(ellipse at 50% 0,#163c2b,#091511 75%)}
#login{isolation:isolate;background:transparent;z-index:1}
body.public-theme>header,body.public-theme>main,body.public-theme>footer{position:relative;z-index:1}
.season-christmas .snow{position:absolute;inset:-220px -60px 0;opacity:.38;background-image:radial-gradient(circle at 25px 25px,#fff 0 1px,transparent 2px),radial-gradient(circle at 119px 83px,#dcebf0 0 1.5px,transparent 2.5px),radial-gradient(circle at 68px 160px,#fff 0 1px,transparent 2px);background-size:180px 220px;animation:season-snow 16s linear infinite;transition:margin-left 2s ease}
.season-christmas .snow:nth-child(2){opacity:.24;background-size:240px 220px;animation-duration:23s;animation-delay:-10s;filter:blur(.5px)}
.season-christmas .snow:nth-child(3){opacity:.3;background-size:330px 220px;animation-duration:11s;animation-delay:-4s}
.season-christmas.wind-left .snow{margin-left:-35px}.season-christmas.wind-right .snow{margin-left:35px}
.season-christmas .santa{position:absolute;top:9%;left:0;width:clamp(230px,32vw,440px);height:auto;animation:season-sleigh 32s linear infinite;filter:drop-shadow(0 2px 8px #0005)}
@keyframes season-snow{from{transform:translate3d(0,0,0)}to{transform:translate3d(25px,220px,0)}}
@keyframes season-sleigh{0%{transform:translate3d(105vw,5px,0) rotate(-3deg)}45%{transform:translate3d(28vw,-12px,0) rotate(2deg)}82%,100%{transform:translate3d(-470px,8px,0) rotate(-3deg)}}
@media(max-width:600px){.season-christmas .santa{top:12%;animation-duration:26s}}
@media(prefers-reduced-motion:reduce){.season-christmas .snow{display:none}.season-christmas .santa{animation:none;left:auto;right:18px;width:160px;opacity:.55}}
html.season-paused .season-christmas *,html.season-paused .season-fireworks *::before,html.season-paused .season-fireworks *::after{animation-play-state:paused}
"""


SCENERY = {
    'default': ('•', '•', '•', '#a8e7ba', 'season-glimmer', '22s'),
    'halloween': ('🦇', '🦇', '✦', '#c6afdc', 'season-drift', '29s'),
    'easter': ('🥚', '✿', '❀', '#e0c7eb', 'season-float', '33s'),
    'summer': ('☁', '🦋', '☁', '#f0e4c3', 'season-drift', '38s'),
    'autumn': ('🍂', '🍁', '🍃', '#e5b373', 'season-leaves', '24s'),
    'winter': ('❄', '·', '✧', '#d4eafa', 'season-leaves', '31s'),
}

def scenery_css(key,bg,glow):
    first,second,third,color,movement,duration=SCENERY[key]
    css=f"""
/* Scenery: {key}; all decoration stays behind the page controls. */
body:has(#login.active)>.season-scenery,body.public-theme>.season-scenery{{display:block}}
.season-scenery{{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none;color:{color}}}
body:has(#login.active){{background:radial-gradient(ellipse at 50% 0,{glow},{bg} 75%)}}
#login{{background:transparent;isolation:isolate;z-index:1}}
body.public-theme>header,body.public-theme>main,body.public-theme>footer{{position:relative;z-index:1}}
.season-scenery i{{position:absolute;left:var(--x);top:-60px;font-style:normal;font-size:var(--size);opacity:0;animation:{movement} {duration} linear infinite;animation-delay:var(--wait);transition:margin-left 2s ease}}
.season-scenery i::before{{content:'{first}'}}
.season-scenery i:nth-child(3n+2)::before{{content:'{second}'}}
.season-scenery i:nth-child(3n)::before{{content:'{third}'}}
.season-scenery.wind-left i{{margin-left:-24px}}.season-scenery.wind-right i{{margin-left:24px}}
@keyframes season-leaves{{0%{{opacity:0;transform:translate3d(0,-30px,0) rotate(0)}}10%{{opacity:.35}}50%{{transform:translate3d(45px,55vh,0) rotate(160deg)}}90%{{opacity:.3}}100%{{opacity:0;transform:translate3d(-30px,115vh,0) rotate(330deg)}}}}
@keyframes season-float{{0%{{opacity:0;transform:translate3d(0,110vh,0) rotate(-12deg)}}15%,75%{{opacity:.25}}100%{{opacity:0;transform:translate3d(30px,5vh,0) rotate(18deg)}}}}
@keyframes season-drift{{0%{{opacity:0;transform:translate3d(-15vw,30vh,0)}}15%,75%{{opacity:.22}}50%{{transform:translate3d(25vw,22vh,0) rotate(-7deg)}}100%{{opacity:0;transform:translate3d(65vw,32vh,0)}}}}
@keyframes season-glimmer{{0%,100%{{opacity:0;transform:translate3d(0,90vh,0)}}30%,65%{{opacity:.24}}99%{{transform:translate3d(25px,0,0)}}}}
html.season-paused .season-scenery *,html.season-paused .season-scenery::after{{animation-play-state:paused}}
@media(prefers-reduced-motion:reduce){{.season-scenery{{display:none!important}}}}
"""
    for n in range(1,13):
        size=5+(n%3)*3 if key=='default' else 10+(n%4)*6
        css+=f'.season-scenery i:nth-child({n}){{--x:{(n*29)%100}%;--wait:-{n*3.7:.1f}s;--size:{size}px;}}\n'
    if key=='halloween':
        css+=".season-scenery::before{content:'';position:absolute;right:9%;top:12%;width:64px;height:64px;border-radius:50%;background:#d8d0ad;opacity:.13;box-shadow:0 0 70px 20px #c7b69322}.season-scenery::after{content:'';position:absolute;bottom:-15%;left:-20%;width:140%;height:40%;background:radial-gradient(ellipse,#a18aaf15,transparent 65%);animation:season-mist 24s ease-in-out infinite alternate}@keyframes season-mist{to{transform:translate3d(8%, -12px,0)}}"
    elif key=='summer':
        css+=".season-scenery::after{content:'☀';position:absolute;right:8%;top:12%;font-size:70px;line-height:1;color:#f1c36d;opacity:.22;animation:season-sun 80s linear infinite}@keyframes season-sun{to{transform:rotate(360deg)}}"
    elif key=='easter':
        css+=".season-scenery::after{content:'✿　❀　✿';position:absolute;bottom:6%;left:5%;font-size:27px;letter-spacing:12px;opacity:.15}"
    elif key=='winter':
        css+=".season-scenery::after{content:'';position:absolute;bottom:-24px;left:-5%;width:110%;height:70px;border-radius:50% 50% 0 0;background:#c6e3f3;opacity:.05}"
    return css
