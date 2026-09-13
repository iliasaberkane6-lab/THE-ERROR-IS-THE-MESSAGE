# Pull request #69: Add phone-triggered repository export with verified media preservation

- State: open
- Author: mrfandu1
- Created: 2026-09-13T10:00:10Z
- URL: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/pull/69

## Body

Related to #60. This adds a dependency-free Python exporter and a one-button GitHub Actions workflow that saves issues, PR conversations and reviews, releases, tags, and uploaded files directly to a dedicated `repository-archive` branch. Team members can run it from a phone browser without installing software or creating a token.

The PR was submitted before the bounty's closing time. After addressing the automated review, a fresh hosted demonstration against **attogram/THE-ERROR-IS-THE-MESSAGE** succeeded at code commit `66fca5758a9e5d987b835856898dda75abdce59f` on September 13 at 13:19–13:20 UTC, including downloads, SHA-256 verification and publication:

- [Successful full Actions run](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/actions/runs/34759467212)
- [Published archive at its immutable commit](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/tree/6cb6e27a19f849bdb02965dedfce1311bbacd580/archive)
- [Issue #60: text, all 29 comments at collection time, and saved media links](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/blob/6cb6e27a19f849bdb02965dedfce1311bbacd580/archive/issues/60/README.md)
- [Completeness report](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/blob/6cb6e27a19f849bdb02965dedfce1311bbacd580/archive/report.json)

The demonstration preserved **61 issues, 14 PRs, 189 conversation comments, 1 PR review, 5 inline review comments, 4 releases, 4 tags and 410 saved asset URLs totaling 1,911,545,028 bytes**, including all eight release source ZIP/TAR files. The report is complete with **zero API/download errors**.

Raw JSON preserves original text; readable pages link to saved media. Downloads and generated JSON/Markdown over 40 MiB are split into checksum-verified parts and can be restored byte for byte. Reruns verify cached downloads before reuse, invalidate changed release assets/tags, and retry failures. Publication uses small, retryable pushes with an explicit incomplete marker until its final commit. Tokens are restricted to GitHub's API and stripped on cross-origin redirects; downloaded content is never executed. Archive Git attributes preserve exact file bytes on Windows clones.

**Validation:** All 29 tests pass locally and on [Windows/Linux CI](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/actions/runs/34759446486) at the submitted code commit. Tests cover pagination, failures, credentials, inline links, concurrency, metadata chunking/restoration, cache reruns, corruption, and real Git publication/retries. The exact detached-worktree/`git switch --orphan` workflow is covered by a real Git regression that confirms only archive files are published; pre-staged content is rejected.

The hosted workflow verified every saved file before publication. Independent remote checks confirmed all **657 checksum-listed files** exist, every asset-part length matches, and no published file exceeds 40 MiB. Core metadata and all nine new asset URLs (eight distinct content files) were downloaded again and SHA-256 verified. The earlier 1.9 GB of media was not all downloaded a second time for this independent check. The latest issue #60 page was inspected in a real browser, including its saved media links and localized images.

The source snapshot is sequential, not atomic; deleted records/historical edits unavailable through GitHub's APIs cannot be recovered. Full scope, limitations, restoration and phone instructions are in `REPOSITORY_DUMP.md`.

Submitted for the advertised EUR 100 bounty. AI-assisted implementation for @mrfandu1. Please confirm whether this demonstration meets the acceptance criteria and your preferred payout method for the accepted award.

### Comment by copilot-pull-request-reviewer[bot] at None

### 🟡 Changes recommended

Critical archive-branch and upload-trust issues, along with moderate publication, CI, link, and concurrency issues, remain unresolved.

*Get a fresh assessment by requesting another Copilot review.*

<details>
<summary>Pull request overview</summary>

Adds a dependency-free, phone-triggered GitHub repository exporter that preserves discussions, releases, tags, and media in an archive branch.

**Changes:**
- Exports and verifies repository records and uploaded files.
- Publishes archives incrementally with large-file handling.
- Adds tests, documentation, and cross-platform workflows.
</details>

<details>
<summary>File summaries</summary>

| File | Summary and review notes |
|---|---|
| `tools/repository_dump.py` | Export, download, verification, and restoration logic. **Critical (1 vote):** upload URL validation trusts attacker-controlled hosts. **Moderate (2 votes):** some bare media links are not clickable. **Moderate (1 vote):** concurrent media-map access can fail during checkpointing. |
| `tools/publish_archive.py` | Batched archive publication. **Moderate (2 votes):** generated metadata is not chunked and may exceed the archive file limit. |
| `tests/test_repository_dump.py` | Exporter and security test coverage. |
| `tests/test_publish_archive.py` | Publication test coverage. |
| `REPOSITORY_DUMP.md` | Usage and phone workflow documentation. |
| `.gitignore` | Ignores generated export artifacts. |
| `.github/workflows/test-repository-dump.yml` | Cross-platform test workflow. **Moderate (3 votes):** path filters omit publisher files, allowing publisher-only changes to bypass these tests. |
| `.github/workflows/repository-dump.yml` | Phone-triggered export and publication workflow. **Critical (2 votes):** orphan-branch initialization can include the source tree in the archive and bypass the large-file guard. |
</details>

<details>
<summary>Review details</summary>

### Suppressed comments (1)

**tools/repository_dump.py:367**
* With multiple upload workers, a worker can assign to `self.media` while the main thread constructs `dict(self.media)` here. Iterating a dict during a concurrent size change can raise `RuntimeError: dictionary changed size during iteration`, which `run()` records as an API-collection failure and makes an otherwise successful export incomplete. Serialize this checkpoint or protect all shared map access with a lock.
```
                # Each completed record is immutable; snapshot the map before serialization.
                write_json(self.output / 'assets.json', dict(self.media))
```

- **Files reviewed:** 7/8 changed files
- **Comments generated:** 5
- **Review effort level:** Lite
</details>

---

💡 <a href="/attogram/THE-ERROR-IS-THE-MESSAGE/new/main?filename=.github/skills/code-review/SKILL.md" class="Link--inTextBlock" target="_blank" rel="noopener noreferrer">Add a `code-review` agent skill</a> or configure MCP servers for context-aware, tailored reviews. <a href="https://docs.github.com/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review?tool=webui#mcp-servers-and-agent-skills" class="Link--inTextBlock" target="_blank" rel="noopener noreferrer">Learn more in the docs.</a>

### Comment by Copilot at 2026-09-13T10:10:41Z

When no archive branch exists, `git switch --orphan` leaves the checked-out source tree in the index/worktree. The publisher's first staged commit can therefore include every source file, so the supposedly dedicated archive branch duplicates the repository and can bypass the 40 MiB archive-file guard. Clear the orphan index/worktree before exporting.

### Comment by Copilot at 2026-09-13T10:10:41Z

Any URL whose host starts with `github-production-user-asset-` is treated as an upload, while `trusted_download` accepts any matching S3 bucket. A repository commenter can therefore make the action fetch an attacker-controlled public object instead of a GitHub upload. Only accept GitHub upload URLs initially; keep the S3 pattern for redirects from GitHub storage (or otherwise bind the redirect origin).

### Comment by Copilot at 2026-09-13T10:10:41Z

This workflow is the matrix that runs the Python test suite on both Linux and Windows, but neither the `pull_request` nor `push` path filters includes `tools/publish_archive.py` or `tests/test_publish_archive.py`. A publisher-only change can therefore merge without running the tests that cover it; add both files to each filter.

### Comment by Copilot at 2026-09-13T10:10:42Z

Only downloaded media is split by `repository_dump.py`; generated metadata such as `issue-comments.json`, `issue-index.json`, and per-PR `files.json` is written as one file. A repository with enough discussion or patch data can exceed 40 MiB, causing this guard to abort publication even though the export is otherwise complete, contrary to the documented large-file handling. Chunk generated metadata as well (or use another size-safe representation) before enforcing the archive file limit.

### Comment by Copilot at 2026-09-13T10:10:42Z

The final replacement turns an inline bare upload such as `See <upload-url> for details` into plain `See ../../assets/<hash>` text. Relative paths are not autolinked by Markdown, so these supported bare media references are not clickable in the archived page; only whole-line URLs and angle autolinks are converted to links. Preserve the existing Markdown/HTML cases while wrapping remaining bare occurrences in a local Markdown link.

### Comment by mrfandu1 at 2026-09-13T13:19:44Z

Addressed the review in 66fca5758a9e5d987b835856898dda75abdce59f. All 29 tests pass locally and on [Windows/Linux CI](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/actions/runs/34759446486).

- Comment bodies now accept GitHub upload endpoints/image hosts only. S3 hosts remain available for GitHub redirects; tests cover rejection of initial bucket URLs and credential stripping on a valid redirect.
- Generated JSON and Markdown now split above 40 MiB, with original byte lengths, SHA-256 hashes and exact restoration. Tests cover chunked caches/checksum inventories, reruns, corrupted parts, large-to-small transitions and remote Git publication. Archive Git attributes also prevent newline conversion on Windows clones.
- Inline bare links are clickable while Markdown destinations, angle destinations, HTML attributes and reference definitions retain their syntax. Publisher code/tests are included in both CI path filters. Download workers and checkpoints share a lock.
- The orphan-branch finding does not reproduce with the actual workflow command: [Git documents that `git switch --orphan` removes tracked files](https://git-scm.com/docs/git-switch#Documentation/git-switch.txt---orphanltnew-branchgt). A real Git test now runs the exact detached-worktree/orphan sequence and invokes the standalone publisher, confirming the remote tree contains only `archive/` files. The publisher additionally rejects a nonempty staging index before making any commit or push.

The [fresh hosted export](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/actions/runs/34759467212) succeeded at this same commit. Its [immutable archive](https://github.com/mrfandu1/THE-ERROR-IS-THE-MESSAGE/tree/6cb6e27a19f849bdb02965dedfce1311bbacd580/archive) preserves 61 issues, 14 PRs, 189 conversation comments, 1 review, 5 inline review comments, 4 releases, 4 tags and 410 saved asset URLs, with zero reported errors. The workflow verified every saved file before publication. Independent remote checks confirmed all 657 checksum-listed files are present, every asset-part length matches, and core metadata plus every new attachment passes SHA-256 verification. The PR description now links this updated evidence.
