import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.repo_dump import GitHubClient, attachment_name, attachment_urls, export_repository, parse_repository


class FakeClient(GitHubClient):
    def __init__(self, responses):
        super().__init__(token=None, api_root="https://api.example.test")
        self.responses = responses
        self.calls = []

    def json(self, path):
        self.calls.append(path)
        path_without_query = path.split("?", 1)[0]
        return self.responses[path_without_query]

    def bytes(self, url):
        self.calls.append(url)
        return b"attachment-data", "application/octet-stream"


class RepoDumpTests(unittest.TestCase):
    def test_parse_repository_accepts_owner_name_and_url(self):
        self.assertEqual(parse_repository("owner/name"), ("owner", "name"))
        self.assertEqual(parse_repository("https://github.com/owner/name"), ("owner", "name"))
        with self.assertRaises(ValueError):
            parse_repository("owner/name/extra")

    def test_attachment_urls_ignore_external_links(self):
        text = (
            "https://github.com/user-attachments/files/123/photo.png "
            "https://user-images.githubusercontent.com/1/2/image.png "
            "https://example.com/not-an-attachment.png "
            "https://github.com/user-attachments/assets/xxxx` "
            "https://[malformed.example/user-attachments/assets/123"
        )
        self.assertEqual(
            attachment_urls(text),
            [
                "https://github.com/user-attachments/files/123/photo.png",
                "https://user-images.githubusercontent.com/1/2/image.png",
            ],
        )

    def test_attachment_name_sniffs_magic_bytes_for_uuid_urls(self):
        uuid_url = "https://github.com/user-attachments/assets/8210eda6-f708-448a-8ca3-515bc00d1edc"
        self.assertTrue(
            attachment_name(uuid_url, "application/octet-stream", b"\x89PNG\r\n\x1a\n" + b"x" * 32).endswith(".png")
        )
        self.assertTrue(
            attachment_name(uuid_url, "application/octet-stream", b"xxxx" + b"ftyp" + b"isom" + b"y" * 32).endswith(".mp4")
        )
        self.assertTrue(
            attachment_name(uuid_url, "application/octet-stream", b"%PDF-1.7 body").endswith(".pdf")
        )
        self.assertTrue(
            attachment_name(uuid_url, "application/octet-stream", b"just some text").endswith(".txt")
        )
        self.assertTrue(
            attachment_name(uuid_url, "application/octet-stream", b"\x00\x01\x02\x03binary").endswith(".bin")
        )
        # A real filename in the URL always wins over sniffed content.
        named = "https://github.com/user-attachments/files/32157681/bounty.repo.dump.0001.pdf"
        self.assertEqual(attachment_name(named, "application/octet-stream", b"anything"), "bounty.repo.dump.0001.pdf")

    def test_attachment_download_does_not_send_api_token_to_signed_cdn(self):
        client = GitHubClient(token="secret-token")
        captured = {}

        class Response:
            headers = {"Content-Type": "application/octet-stream"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"ok"

        def fake_urlopen(request, timeout):
            captured["headers"] = dict(request.header_items())
            return Response()

        with patch("tools.repo_dump.urlopen", fake_urlopen):
            client.bytes("https://github.com/user-attachments/assets/123")
        self.assertNotIn("Authorization", captured["headers"])

    def test_export_separates_issues_and_pull_requests_and_downloads_media(self):
        responses = {
            "/repos/o/r": {"full_name": "o/r"},
            "/repos/o/r/issues": [
                {"number": 1, "body": "issue body", "pull_request": None},
                {"number": 2, "body": "pull body", "pull_request": {"url": "x"}},
            ],
            "/repos/o/r/issues/1": {"number": 1, "body": "issue body"},
            "/repos/o/r/issues/1/comments": [{"body": "https://github.com/user-attachments/assets/12345678-1234-1234-1234-123456789abc"}],
            "/repos/o/r/pulls": [{"number": 2}],
            "/repos/o/r/pulls/2": {"number": 2, "body": "pull body"},
            "/repos/o/r/issues/2/comments": [{"body": "issue comment"}],
            "/repos/o/r/pulls/2/comments": [{"body": "review comment"}],
            "/repos/o/r/pulls/2/reviews": [{"body": "review"}],
            "/repos/o/r/releases": [{
                "id": 3,
                "tag_name": "v1",
                "body": "notes",
                "assets": [{"id": 4, "name": "archive.zip", "url": "https://api.example.test/assets/4"}],
            }],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = export_repository(FakeClient(responses), "o/r", Path(temp_dir))
            self.assertEqual(manifest["counts"]["issues"], 1)
            self.assertEqual(manifest["counts"]["pull_requests"], 1)
            self.assertEqual(manifest["counts"]["attachments_downloaded"], 1)
            self.assertEqual(manifest["counts"]["release_assets_downloaded"], 1)
            self.assertTrue((Path(temp_dir) / "attachments.json").exists())
            self.assertTrue((Path(temp_dir) / "manifest.json").exists())
            issues = json.loads((Path(temp_dir) / "issues/index.json").read_text())
            pulls = json.loads((Path(temp_dir) / "pull_requests/index.json").read_text())
            self.assertEqual(
                issues["items"][0]["comments_data"][0]["body"],
                "https://github.com/user-attachments/assets/12345678-1234-1234-1234-123456789abc",
            )
            self.assertEqual(pulls["items"][0]["review_comments"][0]["body"], "review comment")


if __name__ == "__main__":
    unittest.main()
