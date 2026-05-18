import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from app_version import get_version_info
from cloud.client import CloudClient, CloudConfig


class CloudClientMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_client_sends_executor_metadata_headers(self):
        with patch.dict("os.environ", {"DEVICE_ID": "test-device"}):
            client = CloudClient(CloudConfig(license_key="license"))

            http_client = await client._get_client()

            self.assertIn("X-Executor-Version", http_client.headers)
            self.assertIn("X-Executor-Commit", http_client.headers)
            self.assertIn("X-Executor-Auto-Update", http_client.headers)
            self.assertIn("X-Executor-Image", http_client.headers)
            self.assertTrue(http_client.headers["User-Agent"].startswith("JLP-Hedge-Trading/"))

            await client.close()

    async def test_version_info_contains_update_metadata(self):
        info = get_version_info()

        self.assertIn("version", info)
        self.assertIn("commit", info)
        self.assertIn("docker_image", info)
        self.assertIn("auto_update", info)


if __name__ == "__main__":
    unittest.main()
