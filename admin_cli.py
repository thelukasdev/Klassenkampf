"""Container-local management. The admin token is read from the environment."""
import argparse
import json
import os
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description='Klassenkampf server administration')
    parser.add_argument('action', choices=['status', 'code', 'kick', 'ban', 'unban',
                                          'reset-credits', 'mode', 'save', 'load', 'saves',
                                          'sessions','create-session','end-session'])
    parser.add_argument('value', nargs='?', default='')
    parser.add_argument('--session', default='', help='ID der Spielsitzung')
    args = parser.parse_args()
    token = os.environ.get('KLASSENKAMPF_ADMIN_TOKEN')
    if not token:
        parser.error('KLASSENKAMPF_ADMIN_TOKEN is missing')
    request = urllib.request.Request(
        'http://127.0.0.1:9090/admin',
        data=json.dumps({'action': args.action, 'value': args.value,'session':args.session}).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(json.dumps(json.load(response)['result'], indent=2, ensure_ascii=False))
    except (urllib.error.URLError, KeyError) as exc:
        parser.exit(1, f'Administration failed: {exc}\n')


if __name__ == '__main__':
    main()
