import tempfile
import unittest
from pathlib import Path
from site_theme import THEMES,current,save,stylesheet
import test_player_accounts
Base=test_player_accounts.PlayerAccountTests

class ThemeStorageTests(unittest.TestCase):
    def test_all_templates_persist_and_reject_arbitrary_css(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(current(root),'halloween')
            for key in THEMES:
                save(root,key)
                self.assertEqual(current(root),key)
                css=stylesheet(root).decode()
                self.assertIn('Public template: '+key,css)
                self.assertNotIn('@import',css)
                self.assertNotIn('#lobby',css)
            for bad in ('../bad','body{}',None,{},''):
                with self.assertRaises(ValueError):save(root,bad)
            self.assertEqual(current(root),'winter')
            (Path(root)/'site-theme.json').write_text('broken')
            self.assertEqual(current(root),'halloween')

    def test_newyear_is_decoration_only_and_respects_reduced_motion(self):
        with tempfile.TemporaryDirectory() as root:
            save(root,'newyear');css=stylesheet(root).decode()
            self.assertIn('season-launch',css)
            self.assertIn('season-burst',css)
            self.assertIn('prefers-reduced-motion',css)
            self.assertIn('pointer-events:none',css)
            self.assertNotIn('--theme-accent',css)
            self.assertNotIn('.btn',css)
            self.assertNotIn('.card',css)

class ThemeAccessTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=Base.asyncSetUp
    asyncTearDown=Base.asyncTearDown
    http=Base.http
    body=Base.body
    cookie=Base.cookie
    preauth=Base.preauth
    signup=Base.signup
    admin_headers=Base.admin_headers
    async def test_admin_save_csrf_and_public_css(self):
        h,_=self.admin_headers()
        self.assertIn(b'200',await self.http('/api/admin/site-theme',extra_headers=h))
        r=await self.http('/api/admin/action',method='POST',extra_headers=h,data={'action':'site-theme','value':'summer'})
        self.assertIn(b'200',r)
        css=await self.http('/site-theme.css')
        self.assertIn(b'text/css',css);self.assertIn(b'Public template: summer',css)
        self.assertIn(b'no-store',css)
        r=await self.http('/api/admin/action',method='POST',extra_headers={**h,'X-CSRF-Token':'wrong'},data={'action':'site-theme','value':'winter'})
        self.assertIn(b'403',r)
        self.assertIn(b'Public template: summer',await self.http('/site-theme.css'))
        self.assertIn(b'400',await self.http('/api/admin/action',method='POST',extra_headers=h,data={'action':'site-theme','value':'injected{}'}))
    async def test_players_and_guides_cannot_change_site_theme(self):
        player,*_=await self.signup()
        guide,_=self.admin_headers('guide')
        for headers,prefix in ((player,'player'),(guide,'admin')):
            self.assertIn(b'403',await self.http('/api/'+prefix+'/site-theme',extra_headers=headers))
            self.assertIn(b'403',await self.http('/api/'+prefix+'/action',method='POST',extra_headers=headers,data={'action':'site-theme','value':'summer'}))

# Do not expose the imported TestCase to unittest discovery.
del Base
