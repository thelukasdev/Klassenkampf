import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import wsutil


def masked_frame(data, opcode=1, fin=True):
    mask = b'abcd'
    length = len(data)
    head = bytes([(128 if fin else 0) | opcode])
    head += bytes([128 | length]) if length < 126 else bytes([128 | 126]) + length.to_bytes(2, 'big')
    return head + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(data))


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.configure_data_dir(self.tmp.name)
        self.app = server.Server('127.0.0.1', 0, False, headless=True,
                                 login_code='test-login-secret', admin_token='a' * 40,
                                 public_origin='https://games.example.org')
        self.listener = await asyncio.start_server(self.app.handle, '127.0.0.1', 0)
        self.port = self.listener.sockets[0].getsockname()[1]
        self.admin = await asyncio.start_server(self.app.handle_admin, '127.0.0.1', 0)
        self.admin_port = self.admin.sockets[0].getsockname()[1]
        self.writers = []

    async def asyncTearDown(self):
        for writer in self.writers + list(self.app.connections):
            writer.close()
        for listener in (self.listener, self.admin):
            listener.close()
            await listener.wait_closed()
        await asyncio.sleep(0.05)
        await self.app.replays.drain()
        self.tmp.cleanup()

    async def http(self, path, *, port=None, method='GET', data=None, token=None, extra_headers=None):
        reader, writer = await asyncio.open_connection('127.0.0.1', port or self.port)
        self.writers.append(writer)
        payload = json.dumps(data).encode() if data is not None else b''
        headers = f'{method} {path} HTTP/1.1\r\nHost: games.example.org\r\n'
        if token:
            headers += f'Authorization: Bearer {token}\r\n'
        for key,value in (extra_headers or {}).items():
            headers += f'{key}: {value}\r\n'
        writer.write((headers + f'Content-Length: {len(payload)}\r\n\r\n').encode() + payload)
        await writer.drain()
        return await asyncio.wait_for(reader.read(), 3)

    async def websocket(self, origin='https://games.example.org'):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        self.writers.append(writer)
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(('GET / HTTP/1.1\r\nHost: games.example.org\r\nUpgrade: websocket\r\n'
                      f'Origin: {origin}\r\nSec-WebSocket-Version: 13\r\n'
                      f'Sec-WebSocket-Key: {key}\r\n\r\n').encode())
        await writer.drain()
        headers = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 3)
        return reader, writer, headers

    async def receive(self, reader):
        a, b = await asyncio.wait_for(reader.readexactly(2), 3)
        length = b & 127
        if length == 126:
            length = int.from_bytes(await reader.readexactly(2), 'big')
        elif length == 127:
            length = int.from_bytes(await reader.readexactly(8), 'big')
        return json.loads(await reader.readexactly(length))

    async def until(self, reader, kind):
        for _ in range(30):
            message = await self.receive(reader)
            if message['t'] == kind:
                return message
        self.fail(f'Missing message: {kind}')

    async def send(self, writer, obj):
        writer.write(masked_frame(json.dumps(obj).encode()))
        await writer.drain()

    async def login(self, nick, tok=None):
        reader, writer, headers = await self.websocket()
        self.assertIn(b'101 Switching Protocols', headers)
        await self.until(reader, 'welcome')
        await self.send(writer, {'t': 'login', 'code': 'test-login-secret', 'nick': nick, 'tok': tok})
        result = await self.until(reader, 'nick_ok')
        return reader, writer, result['tok']

    async def test_http_assets_health_and_traversal(self):
        self.assertIn(b'200 OK', await self.http('/healthz'))
        self.assertIn(b'KLASSEN', await self.http('/?v=1'))
        self.assertIn(b'200 OK', await self.http('/app.js'))
        self.assertIn(b'404', await self.http('/../server.py'))
        self.assertIn(b'404', await self.http('/%2e%2e/server.py'))
        self.assertIn(b'405', await self.http('/', method='POST'))
        self.assertIn(b'200 OK', await self.http('/admin'))
        self.assertIn(b'401', await self.http('/api/admin/overview'))

    async def test_admin_auth_snapshot_and_mode(self):
        request = dict(port=self.admin_port, method='POST', data={'action': 'status'})
        self.assertIn(b'401', await self.http('/admin', **request))
        response = await self.http('/admin', token='a' * 40, **request)
        self.assertIn(b'200 OK', response)
        self.assertIn(b'players', response)
        await self.app.admin_action({'action': 'mode', 'value': 'random'})
        await self.app.admin_action({'action': 'save', 'value': 'round-1'})
        await self.app.admin_action({'action': 'mode', 'value': 'choose'})
        await self.app.admin_action({'action': 'load', 'value': 'round-1'})
        self.assertEqual(self.app.mode, 'random')
        with self.assertRaises(ValueError):
            await self.app.admin_action({'action': 'save', 'value': '../escape'})

    async def test_headless_lifecycle_and_fixed_port(self):
        instance = server.Server('127.0.0.1', 0, False, headless=True,
                                  admin_token='a' * 40, admin_port=0)
        task = asyncio.create_task(instance.serve())
        await asyncio.sleep(0.1)
        self.assertFalse(task.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(Path(server.STATE_FILE).exists())
        occupied = server.Server('127.0.0.1', self.port, False, headless=True)
        with self.assertRaises(OSError):
            await occupied.serve()

    async def test_cross_origin_rejected(self):
        reader, writer, headers = await self.websocket('https://evil.example.org')
        self.assertIn(b'403', headers)

    async def test_profile_persistence_and_offline_theft_blocked(self):
        reader, writer, token = await self.login('Alice')
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)
        reader2, writer2, headers = await self.websocket()
        await self.until(reader2, 'welcome')
        await self.send(writer2, {'t': 'login', 'code': 'test-login-secret', 'nick': 'Alice'})
        self.assertIn('reserviert', (await self.until(reader2, 'nick_err'))['msg'])
        reader3, writer3, token3 = await self.login('Alice', token)
        self.assertEqual(token, token3)
        reloaded = server.Server('127.0.0.1', 0, False, headless=True)
        self.assertEqual(reloaded.players['alice'].token_hash, self.app.players['alice'].token_hash)
        self.assertNotIn(token, Path(server.STATE_FILE).read_text())

    async def test_two_players_can_start_match(self):
        ra, wa, _ = await self.login('Alice')
        rb, wb, _ = await self.login('Bob')
        alice, bob = self.app.players['alice'], self.app.players['bob']
        await self.send(wa, {'t': 'challenge', 'target': bob.pid, 'game': 'pong'})
        await self.until(rb, 'challenged')
        await self.send(wb, {'t': 'accept', 'from': alice.pid})
        self.assertEqual((await self.until(ra, 'match_start'))['t'], 'match_start')
        self.assertEqual((await self.until(rb, 'state'))['t'], 'state')
        await self.send(wa, {'t': 'leave'})
        await self.until(rb, 'match_end')

    async def test_login_throttling_and_invalid_json_shape(self):
        reader, writer, _ = await self.websocket()
        await self.until(reader, 'welcome')
        await self.send(writer, [])  # must not crash the handler
        for _ in range(6):
            await self.send(writer, {'t': 'login', 'code': 'wrong'})
            result = await self.until(reader, 'login_err')
        self.assertIn('Zu viele', result['msg'])


class FrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_unmasked_and_fragmented_messages(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b'\x81\xff' + (65537).to_bytes(8, 'big'))
        with self.assertRaises(ValueError):
            await wsutil.read_message(reader)
        reader = asyncio.StreamReader()
        reader.feed_data(b'\x81\x01x')
        with self.assertRaises(ValueError):
            await wsutil.read_message(reader)
        reader = asyncio.StreamReader()
        reader.feed_data(masked_frame(b'hel', fin=False) + masked_frame(b'p', opcode=9)
                         + masked_frame(b'lo', opcode=0))
        self.assertEqual(await wsutil.read_message(reader), (9, b'p'))
        self.assertEqual(await wsutil.read_message(reader), (1, b'hello'))


class ConfigurationTests(unittest.TestCase):
    def test_configuration_generation_and_no_secret_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'configure.py'
            shutil.copyfile(Path(server.__file__).with_name('configure.py'), script)
            result = subprocess.run([sys.executable, str(script), 'games.example.org'], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            env_file = Path(tmp) / '.env'
            original = env_file.read_bytes()
            values = dict(line.split('=', 1) for line in original.decode().splitlines())
            self.assertGreaterEqual(len(values['KLASSENKAMPF_LOGIN_CODE']), 12)
            self.assertGreaterEqual(len(values['KLASSENKAMPF_ADMIN_TOKEN']), 32)
            result = subprocess.run([sys.executable, str(script), 'games.example.org'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(env_file.read_bytes(), original)

    def test_headless_refuses_missing_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if not k.startswith('KLASSENKAMPF_')}
            result = subprocess.run([sys.executable, server.__file__, '--headless', '--data-dir', tmp],
                                    env=env, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'KLASSENKAMPF_ADMIN_TOKEN', result.stderr)
            self.assertFalse((Path(tmp) / 'state.json').exists())


if __name__ == '__main__':
    unittest.main()
