# GitHub Research Dataset

A verified, deduplicated dataset of **668 actively-maintained, licensed,
non-archived** open-source repositories relevant to my project domains
(exoplanet detection, traffic simulation, GPU orchestration, security scanning,
space situational awareness, programming languages, satellite imagery ML, local
LLMs, speech translation, VS Code tooling, IDEs, agriculture/health/medical ML,
and more).

**This repository contains metadata about other people's repositories — not
their code.** Every row is a pointer (owner/name, URL) plus facts pulled from the
GitHub API. No third-party source code is copied, mirrored, forked, rebranded, or
claimed here. Each listed repository remains the property of its own authors
under its own license.

## Files

| File | What it is |
|---|---|
| `repositories_dataset.json` | All 668 records (machine-readable) |
| `repositories_dataset.csv` | The same, as CSV |
| `reuse_permissive.json` | 492 repos under permissive licenses (MIT/Apache/BSD/ISC/…) |
| `reuse_copyleft.json` | 90 repos under copyleft licenses (GPL/AGPL/LGPL/EPL) |
| `gather_scale.sh` | The exact gather script — reproduce with an authenticated `gh` |
| `process_scale.py` | The dedupe + filter + funnel-count pipeline |

## Each record's fields (all from the GitHub API — nothing estimated)

`fullName`, `url`, `stars`, `forks`, `pushed` (last-push date, the activity
evidence), `language`, `license_key`, `license`, `license_class`
(permissive / copyleft / other), `reuse_terms`, `archived` (always false here),
`description`, `project_area` (which of my projects it relates to — the one
judgment field, labelled as such).

## How it was built (filter funnel)

```
stage 0  raw rows returned by the API   : 1627
stage 1  after dedupe (unique)          : 1576   (-51)
stage 2  after excluding archived       : 1491   (-85)
stage 3  after requiring a license      : 1077   (-414)
stage 4  after active (pushed >2025-04-01): 668   (-668 total kept)
FINAL                                     : 668
```

The target was 1,000–2,000, but only 668 clear all three gates. The count is not
padded — repositories that are archived, unlicensed, or stale were dropped, not
back-filled.

## Reuse terms (summary)

- **Permissive** (492): modify, redistribute, fork, incorporate — keep the
  original LICENSE and copyright notice (Apache-2.0 also requires keeping NOTICE).
- **Copyleft** (90): forking/modifying is fine, but redistributing a derivative
  obliges releasing your changes under the same license.
- **Other** (86, inside the JSON): a license is present but non-standard — read
  the repository's LICENSE before reuse.

Nothing here authorises removing any upstream attribution. If you build on any
listed repository, preserve its license, copyright, and NOTICE requirements.

## Reproduce

```bash
gh auth status                 # needs an authenticated GitHub CLI
bash gather_scale.sh           # pulls fresh metadata into /tmp/repo_scale
python3 process_scale.py       # dedupe + filter + funnel counts + dataset
```

Stars and push dates drift over time — re-run to refresh.
