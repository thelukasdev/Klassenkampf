"""Run with docker compose exec app python set_admin_password.py."""
import argparse
import getpass
import os
from pathlib import Path
from web_admin import AdminStore
from password_auth import PasswordAuth

def main():
    parser=argparse.ArgumentParser(description='Verwaltungspasswort sicher setzen')
    parser.add_argument('--email',default=os.environ.get('KLASSENKAMPF_OWNER_EMAIL',''))
    args=parser.parse_args()
    email=AdminStore.email(args.email or input('E-Mail-Adresse: '))
    first=getpass.getpass('Neues Verwaltungspasswort (mindestens 12 Zeichen): ')
    if first!=getpass.getpass('Passwort wiederholen: '):
        parser.error('Die Passwoerter stimmen nicht ueberein.')
    store=AdminStore(Path(os.environ.get('KLASSENKAMPF_DATA_DIR','/data'))/'admin.sqlite3')
    class Web: pass
    web=Web();web.store=store
    try:
        auth=PasswordAuth(web)
        auth.set_encoded(email,auth.encode(first))
        store.log(email,'password-reset','Konsole')
    except ValueError as exc:
        parser.error(str(exc))
    print('Verwaltungspasswort gespeichert. Anmeldung ist sofort moeglich; kein Neustart erforderlich.')

if __name__=='__main__':main()
