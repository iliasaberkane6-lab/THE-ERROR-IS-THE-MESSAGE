# Pull request #61: feat: add mobile-friendly repository dump workflow

- State: open
- Author: iliasaberkane6-lab
- Created: 2026-09-13T08:36:28Z
- URL: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/pull/61

## Body

## Summary

Implements the repository dump tool requested in #60.

- Adds a mobile-friendly `workflow_dispatch` workflow with `source_repository`, output directory, and attachment controls.
- Exports all issues, pull requests, issue comments, reviews, inline review comments, releases, release notes, tags, and release assets through the GitHub REST API.
- Downloads GitHub-hosted attachments referenced by discussions while leaving ordinary external links untouched.
- Writes deterministic JSON indexes plus a manifest with counts, hashes, and failed-download records.
- Uses only the Python standard library; no paid service or third-party dependency is required.

## Validation

- `python -m unittest discover -s tests -v`
- `python -m py_compile tools/repo_dump.py`
- `git diff --check`
- Authenticated read-only smoke run against this repository: 60 issues and 4 releases discovered.

The workflow can be started from GitHub's web or mobile Actions UI and commits the resulting dump into `repo-dump/`.

### Comment by iliasaberkane6-lab at 2026-09-13T08:58:57Z

Follow-up commit `dc32aea` hardens attachment handling: API tokens are never sent to signed CDN URLs, malformed URL-like text is ignored, and tokens are redacted from errors.

Validation: 4/4 local tests pass; a real 10.6 MB GitHub-hosted attachment downloaded successfully. The workflow remains dependency-free and mobile-triggerable.

### Comment by iliasaberkane6-lab at 2026-09-13T13:09:01Z

Hosted validation completed on the fork after the workflow and attachment-parser fixes:\n\n- [Successful mobile-triggerable Actions run](https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/actions/runs/34758711188)\n- [Immutable published archive](https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/tree/fe3dbb8f003914153582b2fef6768d7d071c0c79/repo-dump-demo)\n- 60 issues, 14 pull requests, and 4 releases exported\n- 401 GitHub-hosted attachments found and downloaded, 0 failures (about 1.83 GB)\n- Local regression suite: 4/4 tests passing\n\nThe archive is committed directly into the fork and the workflow remains runnable from Actions on a phone. This is a demonstration for review; no acceptance or payout is assumed.

### Comment by iliasaberkane6-lab at 2026-09-13T15:47:51Z

Final pre-tally status — PR #61 against the posted spec:

- **Issues/PRs/Releases**: paginated export of all open+closed issues, PRs, comments, reviews, inline review comments, releases, notes, tags, and release assets via the REST API.
- **Media/artifacts**: every GitHub-hosted attachment referenced in discussions is downloaded; hosted run recorded **401/401** attachments, **0** failures.
- **Direct repo dump**: output is committed into the repository (`repo-dump/`); manifest carries counts, SHA-256 hashes, and any failure records.
- **Mobile-friendly**: `workflow_dispatch` trigger — runnable from the GitHub mobile/web Actions UI; stdlib-only Python, no paid service.
- **Demonstration on this repo**: hosted Actions run [34758711188](https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/actions/runs/34758711188) completed successfully — 60 issues, 14 PRs, 4 releases, ~1.83 GB committed to the fork archive at commit `fe3dbb8`.

PR is open, mergeable, and clean. Happy to adjust anything during the test step.

### Comment by iliasaberkane6-lab at 2026-09-13T16:14:15Z

Refreshed the hosted demo one more time so the snapshot also covers the new attachments and comments added today:

- [Run 34767425167](https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/actions/runs/34767425167) — completed 16:11 UTC
- Archive commit: `2597e5f` — 61 issues, 14 PRs, 4 releases, 402/402 GitHub-hosted attachments downloaded, 0 failures, ~1.8 GB committed to `repo-dump/`

Ready for the 23:00 CEST tally.

### Comment by iliasaberkane6-lab at 2026-09-13T17:00:27Z

Verified against test 1 (consume issue #60): the archive at `2597e5f` contains the example attachments posted this morning — including the embedded-artifact links (`8210eda6`, `fbea768a`, `3f05c7d0`, `dfd1e8da`), the music files (`85df85e8`, `4597f589`, `9396df72`, `2fe23ffe`, `bbb31476`), the images, and the spec PDF `bounty.repo.dump.0001.pdf` — all in `repo-dump/attachments/` with SHA-256 entries in the manifest.

### Comment by iliasaberkane6-lab at 2026-09-13T17:09:18Z

Final submission summary for PR #61 before the 23:00 tally.

**Test 1 (consume this issue) verified end-to-end on hosted Actions:**
- Run: https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/actions/runs/34758711188
- Result archive branch: https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/tree/fe3dbb8f003914153582b2fef6768d7d071c0c79/repo-dump-demo
- Coverage: 60 issues, 14 PRs, 4 releases, **401/401 attachments downloaded, 0 failures** (~1.83 GB total), including the bounty PDF attached to this issue.

**Spec compliance:**
- Zero-dependency Python exporter (stdlib only), paginated issues/PRs/reviews/releases
- Release assets and user-attachment URLs preserved and downloaded; API tokens never sent to signed CDN URLs (verified in the hosted run)
- Manifest with per-file checksums and an explicit failure list, so partial results are auditable
- Mobile-triggerable `workflow_dispatch` workflow; resumable
- Local unit tests 4/4 green

Ready for your review. Payout coordination available privately on acceptance — no details posted publicly here.

### Comment by iliasaberkane6-lab at 2026-09-13T17:50:21Z

Follow-up hardening, verified on a fresh hosted run: https://github.com/iliasaberkane6-lab/THE-ERROR-IS-THE-MESSAGE/actions/runs/34772173585

Attachment downloads now sniff magic bytes, so the 402 dumped files carry real extensions and open directly from the repository instead of landing as `.bin`:

- 180 × .mp4, 143 × .jpg, 39 × .pdf, 30 × .png
- plus .gif, .webp, .zip, .html, .md, .txt
- 402/402 downloaded, 0 failures — manifest and per-file sha256 in `repo-dump/attachments.json`

The dump for this run is committed on the PR branch under `repo-dump/`.
