"""Emergency reset via trusted SSH; never exposed as a web endpoint."""
import argparse
import os
from pathlib import Path
from web_admin import AdminStore
from mfa_auth import MFAAuth

parser=argparse.ArgumentParser(description='Authenticator eines Verwaltungskontos zuruecksetzen')
parser.add_argument('--email',default=os.environ.get('KLASSENKAMPF_OWNER_EMAIL',''))
args=parser.parse_args()
email=AdminStore.email(args.email)
if input('2FA und Verwaltungssitzungen fuer '+email+' zuruecksetzen? Tippe RESET: ')!='RESET':
    raise SystemExit('Abgebrochen')
class Web:pass
web=Web();web.store=AdminStore(Path(os.environ.get('KLASSENKAMPF_DATA_DIR','/data'))/'admin.sqlite3')
MFAAuth(web).reset(email)
web.store.log(email,'mfa-reset','SSH-Konsole')
print('2FA zurueckgesetzt. Bei der naechsten Passwortanmeldung neuen QR-Code scannen.')
