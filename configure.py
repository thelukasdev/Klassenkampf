"""Generate deployment settings locally; never starts the server."""
import argparse
import pathlib
import re
import secrets


def main():
    parser = argparse.ArgumentParser(description='Docker-Konfiguration erstellen')
    parser.add_argument('domain', help='z.B. spiele.deine-domain.de (ohne https://)')
    args = parser.parse_args()
    domain = args.domain.lower()
    if len(domain) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        parser.error('Bitte einen oeffentlichen DNS-Namen ohne Pfad angeben')
    target = pathlib.Path(__file__).resolve().with_name('.env')
    try:
        with target.open('x', encoding='utf8') as stream:
            stream.write(f'DOMAIN={domain}\nKLASSENKAMPF_LOGIN_CODE={secrets.token_urlsafe(12)}\n'
                         f'KLASSENKAMPF_ADMIN_TOKEN={secrets.token_urlsafe(36)}\n'
                         f'KLASSENKAMPF_STATUS_TOKEN={secrets.token_urlsafe(36)}\n')
        target.chmod(0o600)
    except FileExistsError:
        parser.error('.env existiert bereits; bestehende Zugangsdaten werden nicht ueberschrieben')
    print('.env erstellt. Login-Code nach dem Start: docker compose exec app python admin_cli.py code')


if __name__ == '__main__':
    main()
