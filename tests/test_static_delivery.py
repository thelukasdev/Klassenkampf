import gzip
from pathlib import Path
import tempfile
import unittest
from static_delivery import StaticDelivery

class StaticDeliveryTests(unittest.TestCase):
    def test_negotiation_revalidation_and_update_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.js';body=b'const value="repeated text";\n'*200;path.write_bytes(body)
            cache=StaticDelivery()
            raw=cache.response(path,'application/javascript','GET',{})
            zipped=cache.response(path,'application/javascript','GET',{'accept-encoding':'gzip'})
            self.assertEqual(gzip.decompress(zipped.split(b'\r\n\r\n',1)[1]),body)
            self.assertLess(len(zipped),len(raw));self.assertIn(b'Vary: Accept-Encoding',zipped)
            etag=next(v[6:] for v in raw.split(b'\r\n') if v.startswith(b'ETag: ')).decode()
            same=cache.response(path,'application/javascript','GET',{'if-none-match':'W/'+etag})
            self.assertIn(b'304 Not Modified',same);self.assertTrue(same.endswith(b'\r\n\r\n'))
            self.assertIn(b'200 OK',cache.response(path,'application/javascript','GET',{'if-none-match':etag,'accept-encoding':'gzip'}))
            path.write_bytes(body+b'// changed')
            self.assertIn(b'200 OK',cache.response(path,'application/javascript','GET',{'if-none-match':etag}))
            head=cache.response(path,'application/javascript','HEAD',{'accept-encoding':'gzip;q=0'})
            self.assertNotIn(b'Content-Encoding:',head);self.assertTrue(head.endswith(b'\r\n\r\n'))

    def test_private_html_and_cache_memory_bound(self):
        cache=StaticDelivery();cache.LIMIT=20
        for n in range(4):cache.load(f'{n}.png',embedded=b'x'*12)
        self.assertLessEqual(cache.bytes,20);self.assertEqual(len(cache.entries),1)
        response=cache.response('login.html','text/html','GET',{'if-none-match':'*'},embedded=b'private')
        self.assertIn(b'200 OK',response);self.assertIn(b'Cache-Control: no-store',response);self.assertNotIn(b'ETag:',response)

    def test_encoding_quality(self):
        for value in ('gzip;q=0','br','gzip;q=broken','gzip;q=0,*;q=1'):
            self.assertFalse(StaticDelivery.gzip_allowed(value))
        for value in ('gzip','br, gzip;q=0.5','*;q=1'):
            self.assertTrue(StaticDelivery.gzip_allowed(value))
