import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.asterdex_client import AsterDexClient
from utils.signer import AsterDexSigner


class FakeSigner:
    def __init__(self):
        self.calls = 0

    def sign_simple(self, params):
        self.calls += 1
        signed = dict(params)
        signed["timestamp"] = str(1000 + self.calls)
        signed["recvWindow"] = "5000"
        signed["signature"] = f"sig-{self.calls}"
        return signed

    def get_headers(self):
        return {}


class FakeResponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True}


class RetryAsyncClient:
    calls = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None, headers=None):
        self.calls.append(dict(params or {}))
        if len(self.calls) == 1:
            raise httpx.TimeoutException("timeout")
        return FakeResponse()


async def no_sleep(_seconds):
    return None


class AsterDexClientRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_signed_request_refreshes_signature_for_each_retry(self):
        RetryAsyncClient.calls = []
        client = AsterDexClient(
            user_address="wallet",
            api_key="key",
            api_secret="secret",
            chain="solana",
            max_retries=2,
        )
        fake_signer = FakeSigner()
        client.signer = fake_signer

        with patch("clients.asterdex_client.httpx.AsyncClient", RetryAsyncClient), patch(
            "clients.asterdex_client.asyncio.sleep", no_sleep
        ):
            data = await client._request("GET", "/fapi/v1/balance", {})

        self.assertEqual(data, {"ok": True})
        self.assertEqual(fake_signer.calls, 2)
        self.assertEqual(RetryAsyncClient.calls[0]["timestamp"], "1001")
        self.assertEqual(RetryAsyncClient.calls[1]["timestamp"], "1002")
        self.assertEqual(RetryAsyncClient.calls[0]["signature"], "sig-1")
        self.assertEqual(RetryAsyncClient.calls[1]["signature"], "sig-2")

    async def test_hmac_signing_uses_extended_recv_window(self):
        signer = AsterDexSigner(api_key="key", api_secret="secret", chain="solana")

        signed = signer.sign_simple({"symbol": "SOLUSDT"})

        self.assertEqual(signed["recvWindow"], "50000")


if __name__ == "__main__":
    unittest.main()
