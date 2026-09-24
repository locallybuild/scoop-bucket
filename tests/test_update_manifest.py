import json
import sys
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import update_manifest  # noqa: E402


MANIFEST_FIXTURE = textwrap.dedent('''\
    {
        "version": "2026.09",
        "description": "Local Azure environment that runs entirely on your machine",
        "homepage": "https://locally.build/",
        "license": "Proprietary",
        "architecture": {
            "64bit": {
                "url": "https://get.locally.build/v1/cli/2026.09/windows/amd64#/locally.tar.gz",
                "hash": "aaa"
            },
            "arm64": {
                "url": "https://get.locally.build/v1/cli/2026.09/windows/arm64#/locally.tar.gz",
                "hash": "bbb"
            }
        },
        "bin": "locally.exe",
        "checkver": {
            "url": "https://get.locally.build/v1/cli/latest/version",
            "regex": "v?([\\\\d.]+)"
        },
        "autoupdate": {
            "architecture": {
                "64bit": {
                    "url": "https://get.locally.build/v1/cli/$version/windows/amd64#/locally.tar.gz",
                    "hash": {
                        "url": "https://get.locally.build/v1/cli/$version/windows/amd64/archive-sha256"
                    }
                },
                "arm64": {
                    "url": "https://get.locally.build/v1/cli/$version/windows/arm64#/locally.tar.gz",
                    "hash": {
                        "url": "https://get.locally.build/v1/cli/$version/windows/arm64/archive-sha256"
                    }
                }
            }
        }
    }
''')


class TestSmoke(unittest.TestCase):
    def test_module_imports(self):
        self.assertEqual(
            update_manifest.PLATFORMS,
            ("windows/amd64", "windows/arm64"),
        )


class TestParseManifest(unittest.TestCase):
    def test_parses_version(self):
        result = update_manifest.parse_manifest(MANIFEST_FIXTURE)
        self.assertEqual(result["version"], "2026.09")

    def test_parses_all_shas(self):
        result = update_manifest.parse_manifest(MANIFEST_FIXTURE)
        self.assertEqual(
            result["shas"],
            {
                "windows/amd64": "aaa",
                "windows/arm64": "bbb",
            },
        )

    def test_missing_version_raises(self):
        data = json.loads(MANIFEST_FIXTURE)
        del data["version"]
        bad = json.dumps(data)
        with self.assertRaisesRegex(ValueError, "version"):
            update_manifest.parse_manifest(bad)

    def test_missing_arch_hash_raises(self):
        data = json.loads(MANIFEST_FIXTURE)
        del data["architecture"]["64bit"]["hash"]
        bad = json.dumps(data)
        with self.assertRaisesRegex(ValueError, "64bit"):
            update_manifest.parse_manifest(bad)


class TestWriteManifest(unittest.TestCase):
    NEW_SHAS = {
        "windows/amd64": "newAA",
        "windows/arm64": "newBB",
    }

    def test_rewrites_version(self):
        new = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09.01", self.NEW_SHAS
        )
        data = json.loads(new)
        self.assertEqual(data["version"], "2026.09.01")

    def test_rewrites_each_arch_sha(self):
        new = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09", self.NEW_SHAS
        )
        data = json.loads(new)
        self.assertEqual(data["architecture"]["64bit"]["hash"], "newAA")
        self.assertEqual(data["architecture"]["arm64"]["hash"], "newBB")
        self.assertNotIn("aaa", new)
        self.assertNotIn("bbb", new)

    def test_rewrites_each_arch_url(self):
        new = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09.01", self.NEW_SHAS
        )
        data = json.loads(new)
        self.assertEqual(
            data["architecture"]["64bit"]["url"],
            "https://get.locally.build/v1/cli/2026.09.01/windows/amd64#/locally.tar.gz",
        )
        self.assertEqual(
            data["architecture"]["arm64"]["url"],
            "https://get.locally.build/v1/cli/2026.09.01/windows/arm64#/locally.tar.gz",
        )

    def test_autoupdate_template_preserved(self):
        new = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09.01", self.NEW_SHAS
        )
        data = json.loads(new)
        self.assertIn(
            "$version",
            data["autoupdate"]["architecture"]["64bit"]["url"],
        )
        self.assertIn(
            "$version",
            data["autoupdate"]["architecture"]["arm64"]["url"],
        )

    def test_idempotent(self):
        once = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09", self.NEW_SHAS
        )
        twice = update_manifest.write_manifest(once, "2026.09", self.NEW_SHAS)
        self.assertEqual(once, twice)

    def test_round_trip_through_parse(self):
        new = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09.01", self.NEW_SHAS
        )
        parsed = update_manifest.parse_manifest(new)
        self.assertEqual(parsed["version"], "2026.09.01")
        self.assertEqual(parsed["shas"], self.NEW_SHAS)

    def test_missing_target_arch_raises(self):
        data = json.loads(MANIFEST_FIXTURE)
        del data["architecture"]["64bit"]
        bad = json.dumps(data)
        with self.assertRaisesRegex(ValueError, "64bit"):
            update_manifest.write_manifest(bad, "2026.09.01", self.NEW_SHAS)

    def test_missing_autoupdate_template_raises(self):
        data = json.loads(MANIFEST_FIXTURE)
        del data["autoupdate"]["architecture"]["arm64"]
        bad = json.dumps(data)
        with self.assertRaisesRegex(ValueError, "arm64"):
            update_manifest.write_manifest(bad, "2026.09.01", self.NEW_SHAS)

    def test_trailing_newline(self):
        new = update_manifest.write_manifest(
            MANIFEST_FIXTURE, "2026.09", self.NEW_SHAS
        )
        self.assertTrue(new.endswith("\n"))


class TestRealManifest(unittest.TestCase):
    def test_parses_committed_manifest(self):
        content = (REPO_ROOT / "bucket" / "locally.json").read_text()
        parsed = update_manifest.parse_manifest(content)
        self.assertRegex(parsed["version"], r"^\d{4}\.\d{2}(\.\d+)?$")
        self.assertEqual(set(parsed["shas"]), set(update_manifest.PLATFORMS))
        for platform, sha in parsed["shas"].items():
            with self.subTest(platform=platform):
                self.assertRegex(sha, r"^[0-9a-f]{64}$")
        self.assertEqual(
            len(set(parsed["shas"].values())),
            len(update_manifest.PLATFORMS),
            "each platform should have a distinct sha256",
        )


if __name__ == "__main__":
    unittest.main()
