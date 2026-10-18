import json
from pathlib import Path
import unittest
import test_server as base
from legal_pages import render


class LegalPagesTests(unittest.IsolatedAsyncioTestCase):
    http=base.ServerTests.http
    asyncTearDown=base.ServerTests.asyncTearDown

    async def asyncSetUp(self):
        await base.ServerTests.asyncSetUp(self)
        self.path=Path(self.tmp.name)/'legal.json'
        self.config={'published':True,'name':'Testperson <script>alert(1)</script>',
                     'street':'Musterstraße 1','postal_code':'12345','city':'Musterstadt',
                     'country':'Deutschland','email':'kontakt@example.org',
                     'hosting_provider':'Testhost','hosting_location':'Teststadt, Deutschland',
                     'updated':'18.10.2026'}

    def save(self):self.path.write_text(json.dumps(self.config),encoding='utf-8')

    async def test_no_fake_details_when_unconfigured_or_incomplete(self):
        self.assertIn(b'503',await self.http('/impressum'))
        self.config['published']=False;self.save()
        self.assertIn(b'503',await self.http('/datenschutz'))
        self.config['published']=True;self.config.pop('street');self.save()
        self.assertIn(b'503',await self.http('/impressum'))

    async def test_guest_can_read_both_pages_with_escaped_operator_and_without_cookies(self):
        self.save()
        for route in ('/impressum','/datenschutz','/impressum/','/datenschutz/'):
            r=await self.http(route)
            self.assertIn(b'200 OK',r);self.assertIn(b'text/html; charset=utf-8',r)
            self.assertIn(b'&lt;script&gt;',r);self.assertNotIn(b'<script>alert(1)</script>',r)
            self.assertNotIn(b'Set-Cookie:',r);self.assertIn(b'Content-Security-Policy:',r)
        self.assertIn(b'Local Storage',await self.http('/datenschutz'))
        self.assertIn(b'/impressum',await self.http('/login'))
        self.assertIn(b'/datenschutz',await self.http('/'))
        self.assertIn(b'404',await self.http('/legal.json'))
        self.assertIn(b'404',await self.http('/templates/impressum.html'))

    async def test_config_updates_are_visible_and_head_returns_no_body(self):
        self.save();self.assertIn(b'Musterstadt',render('impressum',self.tmp.name))
        self.config['city']='Andere Stadt';self.save()
        self.assertIn(b'Andere Stadt',await self.http('/impressum'))
        r=await self.http('/impressum',method='HEAD')
        self.assertEqual(r.split(b'\r\n\r\n',1)[1],b'')
