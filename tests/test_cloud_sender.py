import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('cloud_sender',Path(__file__).resolve().parents[1]/'monitoring/cloud_sender.py')
sender=importlib.util.module_from_spec(spec);spec.loader.exec_module(sender)

class CloudSenderTests(unittest.TestCase):
    def test_fixed_metrics_preserve_names_without_identity_labels(self):
        text='''# TYPE kk_players_online gauge
kk_players_online 4
kk_http_requests_total{kind="auth"} 9
kk_http_duration_seconds_bucket{le="+Inf"} 20
kk_http_requests_total{kind="private@example.org"} 2
kk_secret_token 12345
kk_players_online{player="Private Nick"} 1
'''
        result=sender.app_lines(text)
        self.assertEqual(len(result),3);self.assertIn('kk,job=klassenkampf players_online=4.0',result)
        self.assertIn('kk,job=klassenkampf,kind=auth http_requests_total=9.0',result)
        self.assertIn('kk,job=klassenkampf,le=+Inf http_duration_seconds_bucket=20.0',result)
        for value in ('private@example.org','Private Nick','secret_token'):self.assertNotIn(value,'\n'.join(result))

    def test_only_grafana_https_direct_write_endpoint_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'private.json'
            base={'endpoint':'https://example.grafana.net/api/v1/push/influx/write','instance_id':'12345','token':'test-token-12345'}
            path.write_text(json.dumps(base));self.assertEqual(sender.config(path),base)
            for endpoint in ('http://example.grafana.net/api/v1/push/influx/write','https://example.org/api/v1/push/influx/write','https://user:secret@example.grafana.net/api/v1/push/influx/write','https://example.grafana.net/wrong'):
                path.write_text(json.dumps({**base,'endpoint':endpoint}))
                with self.assertRaises(ValueError):sender.config(path)

    def test_failed_app_scrape_reports_down_and_keeps_host_metrics(self):
        opener=Mock();opener.open.side_effect=OSError('private-error-token')
        with patch.object(sender,'host_lines',return_value=['node memory_MemTotal_bytes=100.0']):body=sender.collect('private-status-token',opener)
        self.assertIn(b'kk app_up=0.0',body);self.assertIn(b'kk host_up=1.0',body)
        self.assertNotIn(b'private-',body);self.assertLess(len(body),65536)
        self.assertEqual(opener.open.call_args.kwargs['timeout'],5)

    def test_push_has_timeout_and_no_redirects(self):
        opener=Mock();response=opener.open.return_value.__enter__.return_value if hasattr(opener.open.return_value,'__enter__') else None
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value.status=204;opener.open.return_value=response
        cfg={'endpoint':'https://example.grafana.net/api/v1/push/influx/write','instance_id':'123','token':'write-test-token'}
        sender.push(cfg,b'kk players_online=1',opener)
        request=opener.open.call_args.args[0];self.assertEqual(request.get_method(),'POST');self.assertTrue(request.headers['Authorization'].startswith('Basic '));self.assertEqual(opener.open.call_args.kwargs['timeout'],8)
        self.assertIsNone(sender.NoRedirect().redirect_request(None,None,None,None,None,None))
