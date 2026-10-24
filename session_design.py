"""Small, validated per-session branding; no user HTML, CSS or asset URLs."""
import re

DEFAULT={'accent':'#73d363','background':'#0a0d0a'}

def validate(value):
    if value is None:return dict(DEFAULT)
    if not isinstance(value,dict) or set(value)-set(DEFAULT):raise ValueError('Ungültiges Sitzungsdesign.')
    result={**DEFAULT,**value}
    for color in result.values():
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Bitte gültige Farben wählen.')
    rgb=[int(result['background'][i:i+2],16)/255 for i in (1,3,5)]
    linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
    if sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))>.12:raise ValueError('Bitte einen dunklen Hintergrund wählen, damit Texte lesbar bleiben.')
    return {k:v.lower() for k,v in result.items()}

def name(value):
    if not isinstance(value,str):raise ValueError('Bitte einen Veranstaltungsnamen eingeben.')
    value=' '.join(value.split())
    if not 1<=len(value)<=80 or any(ord(c)<32 for c in value):raise ValueError('Der Veranstaltungsname muss 1 bis 80 Zeichen lang sein.')
    return value
