#!/usr/bin/env python3
"""Export a GitHub repository into a reviewable, self-contained folder.

The exporter intentionally uses only the Python standard library.  It is
designed to run from GitHub Actions, so a mobile user only has to start the
workflow and choose the source repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com"
PAGE_SIZE = 100
CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_ATTACHMENT_BYTES = 512 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_repository(value: str) -> tuple[str, str]:
    value = value.strip().removesuffix("/")
    if value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    if value.startswith("http://github.com/"):
        value = value.removeprefix("http://github.com/")
    parts = [part for part in value.split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        raise ValueError("source_repository must be OWNER/REPOSITORY or a GitHub URL")
    return parts[0], parts[1]


def safe_name(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-_")
    return value[:120] or fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_output_path(output: Path, require_relative: bool = False) -> None:
    """Keep workflow input from escaping the checked-out destination repo."""

    if (require_relative and output.is_absolute()) or output in {Path("."), Path("")} or ".." in output.parts:
        raise ValueError("output must be a relative directory inside the checked-out repository")


def attachment_urls(value: str | None) -> list[str]:
    """Return only GitHub-hosted attachment URLs, never arbitrary links."""

    if not value:
        return []
    candidates = re.findall(r"https?://[^\s<>\"']+", value)
    found: list[str] = []
    for candidate in candidates:
        candidate = candidate.rstrip(".,;:!?)]}`")
        try:
            parsed = urlparse(candidate)
        except ValueError:
            # Discussion text is user-controlled. Ignore malformed URL-like
            # strings rather than aborting an otherwise complete export.
            continue
        host = parsed.netloc.lower().split(":", 1)[0]
        path = parsed.path
        is_user_attachment = False
        if host == "github.com" and path.startswith("/user-attachments/"):
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 3 and parts[1] == "assets":
                is_user_attachment = bool(
                    re.fullmatch(
                        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                        parts[2],
                    )
                )
            elif len(parts) >= 3 and parts[1] == "files":
                is_user_attachment = bool(re.fullmatch(r"[0-9]+", parts[2]))
        is_repo_attachment = (
            host == "github.com"
            and len([part for part in path.split("/") if part]) >= 4
            and ("/assets/" in path or "/files/" in path)
        )
        is_legacy_attachment = host in {
            "user-images.githubusercontent.com",
            "private-user-images.githubusercontent.com",
        }
        if (is_user_attachment or is_repo_attachment or is_legacy_attachment) and candidate not in found:
            found.append(candidate)
    return found


class GitHubClient:
    def __init__(self, token: str | None = None, api_root: str = API_ROOT) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.api_root = api_root.rstrip("/")

    def _request(self, url: str, accept: str = "application/vnd.github+json") -> tuple[bytes, dict[str, str]]:
        display_url = urlparse(url)._replace(query="", fragment="").geturl()
        headers = {
            "Accept": accept,
            "User-Agent": "repository-dump-tool/1.0",
        }
        # Signed GitHub attachment/CDN URLs already carry their own temporary
        # credentials. Sending a GitHub API token to those hosts both breaks
        # the signed request and risks leaking the token in a CDN error. Only
        # authenticate requests addressed to this client's API root.
        if self.token and (url == self.api_root or url.startswith(f"{self.api_root}/")):
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers)
        for attempt in range(4):
            try:
                with urlopen(request, timeout=60) as response:
                    return response.read(), {key.lower(): value for key, value in response.headers.items()}
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                    detail = error.read(4096).decode("utf-8", errors="replace")
                    if self.token:
                        detail = detail.replace(self.token, "[redacted-token]")
                    raise RuntimeError(f"GitHub request failed ({error.code}) for {display_url}: {detail[:500]}") from error
            except URLError as error:
                if attempt == 3:
                    detail = str(error)
                    if self.token:
                        detail = detail.replace(self.token, "[redacted-token]")
                    raise RuntimeError(f"GitHub request failed for {display_url}: {detail}") from error
            time.sleep(2**attempt)
        raise RuntimeError(f"GitHub request failed for {display_url}")

    def json(self, path: str) -> Any:
        url = path if path.startswith("http") else f"{self.api_root}{path}"
        body, _ = self._request(url)
        return json.loads(body.decode("utf-8"))

    def all(self, path: str) -> list[Any]:
        separator = "&" if "?" in path else "?"
        page = 1
        values: list[Any] = []
        while True:
            page_path = f"{path}{separator}{urlencode({'per_page': PAGE_SIZE, 'page': page})}"
            payload = self.json(page_path)
            if not isinstance(payload, list):
                raise RuntimeError(f"Expected a list from {page_path}")
            values.extend(payload)
            if len(payload) < PAGE_SIZE:
                return values
            page += 1

    def bytes(self, url: str) -> tuple[bytes, str | None]:
        body, headers = self._request(url, accept="application/octet-stream")
        return body, headers.get("content-type")


def issue_has_pull_request(issue: dict[str, Any]) -> bool:
    return bool(issue.get("pull_request"))


def enrich_issue(client: GitHubClient, repo_path: str, issue: dict[str, Any]) -> dict[str, Any]:
    number = issue["number"]
    detail = client.json(f"/repos/{repo_path}/issues/{number}")
    detail["comments_data"] = client.all(f"/repos/{repo_path}/issues/{number}/comments")
    return detail


def enrich_pull_request(client: GitHubClient, repo_path: str, pull: dict[str, Any]) -> dict[str, Any]:
    number = pull["number"]
    detail = client.json(f"/repos/{repo_path}/pulls/{number}")
    detail["issue_comments"] = client.all(f"/repos/{repo_path}/issues/{number}/comments")
    detail["review_comments"] = client.all(f"/repos/{repo_path}/pulls/{number}/comments")
    detail["reviews"] = client.all(f"/repos/{repo_path}/pulls/{number}/reviews")
    return detail


def fmt_user(value: Any) -> str:
    return (value or {}).get("login") or "unknown"


def rewrite_links(text: str | None, link_map: dict[str, str]) -> str:
    """Point attachment URLs at their dumped copy so the archive is self-contained."""

    value = (text or "").strip() or "(empty)"
    for url, path in link_map.items():
        if url in value:
            value = value.replace(url, f"../{path}")
    return value


def render_thread_markdown(kind: str, item: dict[str, Any], comments: list[dict[str, Any]], link_map: dict[str, str]) -> str:
    lines = [
        f"# {kind} #{item.get('number')}: {item.get('title') or '(untitled)'}",
        "",
        f"- State: {item.get('state')}",
        f"- Author: {fmt_user(item.get('user'))}",
        f"- Created: {item.get('created_at')}",
        f"- URL: {item.get('html_url')}",
        "",
        "## Body",
        "",
        rewrite_links(item.get("body"), link_map),
        "",
    ]
    for comment in comments:
        lines.extend(
            [
                f"### Comment by {fmt_user(comment.get('user'))} at {comment.get('created_at')}",
                "",
                rewrite_links(comment.get("body"), link_map),
                "",
            ]
        )
    return "\n".join(lines)


def write_issue_markdown(output: Path, issues: Iterable[dict[str, Any]], link_map: dict[str, str]) -> None:
    folder = output / "issues"
    folder.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        slug = safe_name(str(issue.get("title") or "issue"), "issue").lower()
        path = folder / f"{issue.get('number'):04d}-{slug}.md"
        path.write_text(
            render_thread_markdown("Issue", issue, issue.get("comments_data") or [], link_map),
            encoding="utf-8",
        )


def write_pull_markdown(output: Path, pulls: Iterable[dict[str, Any]], link_map: dict[str, str]) -> None:
    folder = output / "pull_requests"
    folder.mkdir(parents=True, exist_ok=True)
    for pull in pulls:
        slug = safe_name(str(pull.get("title") or "pull-request"), "pull-request").lower()
        path = folder / f"{pull.get('number'):04d}-{slug}.md"
        comments = [
            *(pull.get("issue_comments") or []),
            *(pull.get("review_comments") or []),
            *(pull.get("reviews") or []),
        ]
        comments.sort(key=lambda comment: comment.get("created_at") or "")
        path.write_text(
            render_thread_markdown("Pull request", pull, comments, link_map),
            encoding="utf-8",
        )


def write_release_markdown(output: Path, releases: Iterable[dict[str, Any]], link_map: dict[str, str]) -> None:
    folder = output / "releases"
    folder.mkdir(parents=True, exist_ok=True)
    for release in releases:
        tag = safe_name(str(release.get("tag_name") or release.get("id") or "release"), "release")
        lines = [
            f"# Release {release.get('tag_name') or release.get('name') or release.get('id')}",
            "",
            f"- Name: {release.get('name')}",
            f"- Tag: {release.get('tag_name')}",
            f"- Author: {fmt_user(release.get('author'))}",
            f"- Published: {release.get('published_at')}",
            f"- URL: {release.get('html_url')}",
            "",
            "## Notes",
            "",
            rewrite_links(release.get("body"), link_map),
            "",
            "## Artifacts",
            "",
        ]
        for asset in release.get("assets") or []:
            target = link_map.get(asset.get("browser_download_url") or "", asset.get("browser_download_url"))
            lines.append(f"- {asset.get('name')} ({asset.get('size')} bytes): {target}")
        if not release.get("assets"):
            lines.append("- (none)")
        (folder / f"{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_values(child)


def sniff_extension(body: bytes) -> str | None:
    """Best-effort file-type detection from magic bytes."""

    if body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if body.startswith(b"GIF8"):
        return ".gif"
    if body.startswith(b"%PDF"):
        return ".pdf"
    if body.startswith(b"PK\x03\x04") or body.startswith(b"PK\x05\x06"):
        return ".zip"
    if body.startswith(b"\x1f\x8b"):
        return ".gz"
    if body.startswith(b"ID3") or body[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return ".mp3"
    if body.startswith(b"OggS"):
        return ".ogg"
    if body.startswith(b"fLaC"):
        return ".flac"
    if body.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body[:4] == b"RIFF" and body[8:12] == b"WAVE":
        return ".wav"
    if body[:4] in {b"II*\x00", b"MM\x00*"}:
        return ".tif"
    if body[4:8] == b"ftyp":
        return ".mp4"
    return None


def looks_like_text(body: bytes) -> bool:
    if not body:
        return False
    sample = body[:8192]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def attachment_name(url: str, content_type: str | None, body: bytes = b"") -> str:
    parsed = urlparse(url)
    basename = safe_name(Path(parsed.path).name, "attachment")
    # UUID-only attachment URLs have no useful filename.  Keep a stable name
    # so a rerun does not create duplicate files.  The CDN usually reports a
    # generic octet-stream content type, so sniff the payload first: dumped
    # media then carries a real extension and opens directly from the repo.
    if basename in {"assets", "files", "attachment"} or len(basename) >= 30:
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        extension = sniff_extension(body)
        if extension is None and mime in {"", "application/octet-stream", "binary/octet-stream"} and looks_like_text(body):
            extension = ".txt"
        if extension is None:
            extension = mimetypes.guess_extension(mime) or ".bin"
        basename = f"attachment-{hashlib.sha256(url.encode()).hexdigest()[:12]}{extension}"
    return basename


def download_attachments(
    client: GitHubClient,
    output: Path,
    records: Iterable[dict[str, Any]],
    max_bytes: int,
) -> list[dict[str, Any]]:
    urls: list[str] = []
    for record in records:
        for text in text_values(record):
            for url in attachment_urls(text):
                if url not in urls:
                    urls.append(url)

    attachment_dir = output / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for url in urls:
        parsed_url = urlparse(url)
        safe_url = parsed_url._replace(query="", fragment="").geturl()
        item: dict[str, Any] = {"url": safe_url, "source_url": url, "status": "failed"}
        try:
            body, content_type = client.bytes(url)
            if len(body) > max_bytes:
                raise RuntimeError(f"attachment exceeds {max_bytes} byte limit")
            name = attachment_name(url, content_type, body)
            stem, suffix = os.path.splitext(name)
            candidate = name
            counter = 2
            while candidate in used_names:
                candidate = f"{stem}-{counter}{suffix}"
                counter += 1
            used_names.add(candidate)
            (attachment_dir / candidate).write_bytes(body)
            item.update(
                {
                    "status": "downloaded",
                    "path": f"attachments/{candidate}",
                    "bytes": len(body),
                    "content_type": content_type,
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
        except Exception as error:  # Preserve the manifest even if one old upload is gone.
            item["error"] = str(error)
        results.append(item)
    write_json(output / "attachments.json", results)
    return results


def download_release_assets(
    client: GitHubClient,
    output: Path,
    releases: Iterable[dict[str, Any]],
    max_bytes: int,
) -> list[dict[str, Any]]:
    """Download release files through the authenticated GitHub asset API."""

    asset_dir = output / "release-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for release in releases:
        for asset in release.get("assets", []):
            item: dict[str, Any] = {
                "release_id": release.get("id"),
                "release_tag": release.get("tag_name"),
                "asset_id": asset.get("id"),
                "name": asset.get("name"),
                "source_url": asset.get("browser_download_url"),
                "status": "failed",
            }
            try:
                asset_url = asset.get("url") or asset.get("browser_download_url")
                if not asset_url:
                    raise RuntimeError("release asset has no download URL")
                body, content_type = client.bytes(asset_url)
                if len(body) > max_bytes:
                    raise RuntimeError(f"release asset exceeds {max_bytes} byte limit")
                base = safe_name(asset.get("name") or f"asset-{asset.get('id', 'unknown')}")
                prefix = safe_name(str(release.get("tag_name") or release.get("id") or "release"))
                candidate = f"{prefix}-{base}"
                stem, suffix = os.path.splitext(candidate)
                counter = 2
                while candidate in used_names:
                    candidate = f"{stem}-{counter}{suffix}"
                    counter += 1
                used_names.add(candidate)
                (asset_dir / candidate).write_bytes(body)
                item.update(
                    {
                        "status": "downloaded",
                        "path": f"release-assets/{candidate}",
                        "bytes": len(body),
                        "content_type": content_type,
                        "sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
            except Exception as error:  # Keep metadata if a release asset was deleted.
                item["error"] = str(error)
            results.append(item)
    write_json(output / "release-assets.json", results)
    return results


def export_repository(
    client: GitHubClient,
    source_repository: str,
    output: Path,
    include_attachments: bool = True,
    max_attachment_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
) -> dict[str, Any]:
    validate_output_path(output)
    owner, name = parse_repository(source_repository)
    repo_path = f"{owner}/{name}"
    repository = client.json(f"/repos/{repo_path}")
    issues = [
        item
        for item in client.all(f"/repos/{repo_path}/issues?state=all")
        if not issue_has_pull_request(item)
    ]
    pulls = client.all(f"/repos/{repo_path}/pulls?state=all&sort=created&direction=asc")
    releases = client.all(f"/repos/{repo_path}/releases")

    issue_records = [enrich_issue(client, repo_path, item) for item in issues]
    pull_records = [enrich_pull_request(client, repo_path, item) for item in pulls]

    write_json(output / "repository.json", repository)
    write_json(output / "issues" / "index.json", {"count": len(issue_records), "items": issue_records})
    write_json(output / "pull_requests" / "index.json", {"count": len(pull_records), "items": pull_records})

    release_records: list[dict[str, Any]] = []
    release_assets: list[dict[str, Any]] = []
    for release in releases:
        release_copy = dict(release)
        assets = release_copy.pop("assets", [])
        release_copy["assets"] = assets
        release_records.append(release_copy)
        release_assets.extend(
            {
                "release_id": release.get("id"),
                "release_tag": release.get("tag_name"),
                **asset,
            }
            for asset in assets
        )
    write_json(output / "releases" / "index.json", {"count": len(release_records), "items": release_records})

    records_for_attachments: list[dict[str, Any]] = [*issue_records, *pull_records, *release_records]
    if include_attachments:
        attachment_records = download_attachments(client, output, records_for_attachments, max_attachment_bytes)
        release_asset_records = download_release_assets(client, output, release_records, max_attachment_bytes)
    else:
        attachment_records = []
        release_asset_records = []
        write_json(output / "attachments.json", [])
        write_json(output / "release-assets.json", [])

    # Readable markdown copies next to the raw JSON so the archive can be
    # browsed directly on a phone inside the repository.  Downloaded
    # attachments are linked by relative path so the archive stays usable
    # even if the original upload is later deleted.
    link_map: dict[str, str] = {}
    for item in [*attachment_records, *release_asset_records]:
        if item.get("status") != "downloaded" or not item.get("path"):
            continue
        for key in {item.get("source_url"), item.get("url")} - {None}:
            link_map[key] = item["path"]
    write_issue_markdown(output, issue_records, link_map)
    write_pull_markdown(output, pull_records, link_map)
    write_release_markdown(output, release_records, link_map)

    manifest = {
        "schema_version": 1,
        "source_repository": repo_path,
        "generated_at": utc_now(),
        "counts": {
            "issues": len(issue_records),
            "pull_requests": len(pull_records),
            "releases": len(release_records),
            "release_assets": len(release_assets),
            "attachments_found": len(attachment_records),
            "attachments_downloaded": sum(item.get("status") == "downloaded" for item in attachment_records),
            "attachments_failed": sum(item.get("status") == "failed" for item in attachment_records),
            "release_assets_downloaded": sum(item.get("status") == "downloaded" for item in release_asset_records),
            "release_assets_failed": sum(item.get("status") == "failed" for item in release_asset_records),
        },
        "files": {
            "repository": "repository.json",
            "issues": "issues/index.json",
            "pull_requests": "pull_requests/index.json",
            "releases": "releases/index.json",
            "attachments": "attachments.json",
            "release_assets": "release-assets.json",
        },
        "notes": [
            "Issues and pull requests are separated; GitHub exposes pull requests in the issues endpoint too.",
            "Pull requests include issue comments, reviews, and inline review comments.",
            "Each issue, pull request, and release is also rendered as a readable markdown file next to the raw JSON.",
            "Only GitHub-hosted attachment URLs are downloaded; ordinary external links remain in their source text.",
        ],
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_repository", help="OWNER/REPOSITORY or a GitHub URL")
    parser.add_argument("output", type=Path, help="directory in which to write the dump")
    parser.add_argument("--no-attachments", action="store_true", help="skip GitHub-hosted attachment downloads")
    parser.add_argument(
        "--max-attachment-bytes",
        type=int,
        default=DEFAULT_MAX_ATTACHMENT_BYTES,
        help="reject individual attachments larger than this size",
    )
    parser.add_argument("--token", default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        validate_output_path(args.output, require_relative=True)
        export_repository(
            GitHubClient(token=args.token),
            args.source_repository,
            args.output,
            include_attachments=not args.no_attachments,
            max_attachment_bytes=args.max_attachment_bytes,
        )
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"repo-dump: {error}", file=sys.stderr)
        return 1
    print(f"repo-dump: completed {args.source_repository} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
