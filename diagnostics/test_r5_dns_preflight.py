"""Focused offline regression for the R5 fail-closed DNS preflight."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import socket
import unittest


SCRIPT = Path(__file__).with_name("run_adaptive_campaign_r5.py")
SPEC = importlib.util.spec_from_file_location("adaptive_campaign_r5", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EndpointDnsPreflightTests(unittest.TestCase):
    def test_reports_only_endpoint_and_count_on_success(self):
        seen = []

        def resolver(host, port, *, type):
            seen.append((host, port, type))
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.10", port))]

        result = MODULE.endpoint_dns_preflight(resolver)
        self.assertEqual(result, {"host": MODULE.HOST, "port": 443, "resolved_address_count": 1})
        self.assertEqual(seen, [(MODULE.HOST, 443, socket.SOCK_STREAM)])

    def test_fails_closed_on_resolution_error_with_cause(self):
        def resolver(*args, **kwargs):
            raise socket.gaierror("synthetic DNS failure")

        with self.assertRaises(MODULE.SafetyError) as caught:
            MODULE.endpoint_dns_preflight(resolver)
        self.assertEqual(str(caught.exception), "ENDPOINT_DNS_UNAVAILABLE:gaierror")
        self.assertIsInstance(caught.exception.__cause__, socket.gaierror)

    def test_fails_closed_on_empty_resolution(self):
        with self.assertRaisesRegex(MODULE.SafetyError, "ENDPOINT_DNS_EMPTY"):
            MODULE.endpoint_dns_preflight(lambda *args, **kwargs: [])

    def test_preflight_precedes_session_and_grant_creation(self):
        source = inspect.getsource(MODULE.main)
        self.assertLess(source.index("endpoint_dns_preflight()"), source.index("out.mkdir("))
        self.assertLess(source.index("endpoint_dns_preflight()"), source.index('write_new(out / "GRANT.json"'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
