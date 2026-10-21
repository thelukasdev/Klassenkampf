"""Fixed, local avatar catalogue. No uploads or external image URLs."""
AVATARS={'robot':'Roboter','fox':'Fuchs','cat':'Katze','bear':'Bär','owl':'Eule','ghost':'Geist','rocket':'Rakete','bolt':'Blitz'}
DEFAULT='robot'
def safe_avatar(value):
    return value if isinstance(value,str) and value in AVATARS else DEFAULT
