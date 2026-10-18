import base64
import time
import unittest
from unittest.mock import patch
import test_web_admin as base
from mfa_auth import totp


class TotpVectors(unittest.TestCase):
    def test_rfc6238_sha1_vectors(self):
        secret=base64.b32encode(b'12345678901234567890').decode()
        for timestamp,expected in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),
                                   (1234567890,'89005924'),(2000000000,'69279037'),(20000000000,'65353130')]:
            self.assertEqual(totp(secret,timestamp//30,8),expected)


class MFATests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=base.WebAdminTests.asyncSetUp
    asyncTearDown=base.WebAdminTests.asyncTearDown

    def password(self):
        value=self.auth.encode('test-password-123456')
        self.auth.set_encoded('owner@example.org',value)
        return value

    def enroll(self):
        version=self.password()
        token,setup=self.auth.mfa.begin('owner@example.org',version)
        result=self.auth.mfa.verify(token,totp(setup['secret'],int(time.time())//30))
        self.assertIsNotNone(result)
        return version,setup['secret'],result['recovery_codes']

    async def test_invalid_codes_limit_expiry_and_no_early_enrollment(self):
        version=self.password();token,setup=self.auth.mfa.begin('owner@example.org',version)
        with self.store.connect() as db:self.assertFalse(db.execute('SELECT 1 FROM mfa_factors').fetchone())
        for _ in range(5):self.assertIsNone(self.auth.mfa.verify(token,'not-a-code'))
        self.assertIsNone(self.auth.mfa.verify(token,totp(setup['secret'],int(time.time())//30)))
        token,setup=self.auth.mfa.begin('owner@example.org',version)
        self.assertIsNone(self.auth.mfa.verify(token,totp(setup['secret'],int(time.time())//30)))
        with self.store.connect() as db:db.execute('UPDATE mfa_pending SET expires=0')
        self.assertIsNone(self.auth.mfa.verify(token,totp(setup['secret'],int(time.time())//30)))

    async def test_setup_one_use_recovery_codes_and_totp_replay(self):
        version,secret,recovery=self.enroll()
        token,response=self.auth.mfa.begin('owner@example.org',version)
        self.assertEqual(response,{'stage':'verify'})
        self.assertIsNone(self.auth.mfa.verify(token,totp(secret,int(time.time())//30)))
        self.assertIsNotNone(self.auth.mfa.verify(token,recovery[0]))
        self.assertIsNone(self.auth.mfa.verify(token,recovery[1]))
        token,_=self.auth.mfa.begin('owner@example.org',version)
        self.assertIsNone(self.auth.mfa.verify(token,recovery[0]))
        self.assertIsNotNone(self.auth.mfa.verify(token,recovery[1]))
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM mfa_recovery').fetchone()[0],8)

    async def test_password_reset_preserves_factor_but_invalidates_partial_login(self):
        version,secret,recovery=self.enroll()
        token,_=self.auth.mfa.begin('owner@example.org',version)
        self.auth.set_encoded('owner@example.org',self.auth.encode('replacement-password-1234'))
        self.assertIsNone(self.auth.mfa.verify(token,recovery[0]))
        with self.store.connect() as db:self.assertTrue(db.execute('SELECT 1 FROM mfa_factors').fetchone())

    async def test_ssh_reset_and_backward_sessions_are_revoked(self):
        version,secret,recovery=self.enroll()
        session=self.store.new_session('owner@example.org')
        self.auth.mfa.reset('owner@example.org')
        self.assertIsNone(self.store.session(session))
        token,response=self.auth.mfa.begin('owner@example.org',version)
        self.assertEqual(response['stage'],'setup')
        self.assertNotEqual(response['secret'],secret)
