"""Dedupe + filter with before/after counts at every stage. No fabrication:
every field is the GitHub API value. Emits machine-readable JSON + CSV + a
per-project/per-license summary."""
import csv
import glob
import json
from datetime import datetime, timezone

OUT = "/tmp/repo_scale"
ACTIVE_AFTER = datetime(2025, 4, 1, tzinfo=timezone.utc)

PERMISSIVE = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc",
              "0bsd", "unlicense", "mpl-2.0", "mit-0", "zlib", "bsl-1.0",
              "postgresql", "ncsa", "artistic-2.0"}
COPYLEFT = {"gpl-3.0", "gpl-2.0", "agpl-3.0", "lgpl-3.0", "lgpl-2.1",
            "epl-2.0", "epl-1.0", "ms-pl", "osl-3.0", "cc-by-sa-4.0", "eupl-1.2"}

REUSE = {
    "permissive": "modify, redistribute, fork, incorporate — keep LICENSE + copyright notice (Apache also NOTICE)",
    "copyleft": "fork/modify OK; redistributing a derivative obliges same-license release of your changes",
    "other": "license present but non-standard — read the LICENSE before reuse",
}

# ---- stage 0: load raw ----
raw = []
for f in sorted(glob.glob(f"{OUT}/*.json")):
    try:
        raw.extend(json.load(open(f)))
    except Exception:
        pass
c0 = len(raw)

# ---- stage 1: dedupe by fullName (keep max stars) ----
by = {}
for r in raw:
    fn = r.get("fullName")
    if not fn:
        continue
    if fn not in by or r.get("stargazersCount", 0) > by[fn].get("stargazersCount", 0):
        tag = by[fn].get("_tag") if fn in by else r.get("_tag")
        by[fn] = r
        by[fn]["_tag"] = tag or r.get("_tag")
dedup = list(by.values())
c1 = len(dedup)

# ---- stage 2: exclude archived ----
s2 = [r for r in dedup if not r.get("isArchived", False)]
c2 = len(s2)

# ---- stage 3: require declared license ----
def lickey(r):
    return (r.get("license") or {}).get("key") or ""
s3 = [r for r in s2 if lickey(r)]
c3 = len(s3)

# ---- stage 4: active (pushed after floor) ----
def pushed_dt(r):
    try:
        return datetime.fromisoformat((r.get("pushedAt") or "").replace("Z", "+00:00"))
    except Exception:
        return None
s4 = []
for r in s3:
    d = pushed_dt(r)
    if d and d >= ACTIVE_AFTER:
        s4.append(r)
c4 = len(s4)

# ---- finalize records ----
final = []
for r in s4:
    k = lickey(r)
    cls = "permissive" if k in PERMISSIVE else ("copyleft" if k in COPYLEFT else "other")
    final.append({
        "fullName": r["fullName"],
        "url": r.get("url"),
        "stars": r.get("stargazersCount", 0),
        "forks": r.get("forksCount", 0),
        "pushed": (r.get("pushedAt") or "")[:10],
        "language": r.get("language") or "",
        "license_key": k,
        "license": (r.get("license") or {}).get("name") or "",
        "license_class": cls,
        "reuse_terms": REUSE[cls],
        "archived": False,
        "description": (r.get("description") or "").strip(),
        "project_area": r.get("_tag", "?"),
    })
final.sort(key=lambda x: (x["project_area"], -x["stars"]))

json.dump(final, open(f"{OUT}/dataset.json", "w"), indent=1)
with open(f"{OUT}/dataset.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(final[0].keys()))
    w.writeheader()
    w.writerows(final)

# ---- report ----
from collections import Counter
proj = Counter(r["project_area"] for r in final)
lic = Counter(r["license"] for r in final)
cls = Counter(r["license_class"] for r in final)

print("=== FILTER FUNNEL (before → after) ===")
print(f"  stage 0 raw rows returned by API : {c0}")
print(f"  stage 1 after dedupe (unique)    : {c1}   (removed {c0-c1})")
print(f"  stage 2 after exclude archived   : {c2}   (removed {c1-c2})")
print(f"  stage 3 after require license    : {c3}   (removed {c2-c3})")
print(f"  stage 4 after active>2025-04-01  : {c4}   (removed {c3-c4})")
print(f"  FINAL qualifying repositories    : {len(final)}")
print()
print("=== per project area ===")
for t, n in proj.most_common():
    print(f"  {t:<22} {n}")
print()
print("=== license class ===")
for c, n in cls.most_common():
    print(f"  {c:<12} {n}")
print()
print("=== top licenses ===")
for l, n in lic.most_common(12):
    print(f"  {l:<40} {n}")
