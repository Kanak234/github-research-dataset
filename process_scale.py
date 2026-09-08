"""Dedupe + filter with before/after counts at every stage. No fabrication:
every field is the GitHub API value. Emits machine-readable JSON + CSV + a
per-project/per-license summary."""
import argparse
import csv
import glob
import json
import os
from collections import Counter
from datetime import datetime, timezone

OUT = "/tmp/repo_scale"
ACTIVE_AFTER = datetime(2025, 4, 1, tzinfo=timezone.utc)

PERMISSIVE = {
    "mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc",
    "0bsd", "unlicense", "mpl-2.0", "mit-0", "zlib", "bsl-1.0",
    "postgresql", "ncsa", "artistic-2.0"
}
COPYLEFT = {
    "gpl-3.0", "gpl-2.0", "agpl-3.0", "lgpl-3.0", "lgpl-2.1",
    "epl-2.0", "epl-1.0", "ms-pl", "osl-3.0", "cc-by-sa-4.0", "eupl-1.2"
}

REUSE = {
    "permissive": "modify, redistribute, fork, incorporate — keep LICENSE + copyright notice (Apache also NOTICE)",
    "copyleft": "fork/modify OK; redistributing a derivative obliges same-license release of your changes",
    "other": "license present but non-standard — read the LICENSE before reuse",
}


def load_raw_batches(raw_path_or_dir):
    """Load raw records from json files in a directory or single json file."""
    records = []
    if os.path.isdir(raw_path_or_dir):
        files = sorted(glob.glob(os.path.join(raw_path_or_dir, "*.json")))
    elif os.path.isfile(raw_path_or_dir):
        files = [raw_path_or_dir]
    else:
        files = sorted(glob.glob(raw_path_or_dir))

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict):
                    records.append(data)
        except Exception:
            pass
    return records


def deduplicate_records(records):
    """Deduplicate records by fullName, keeping the one with higher stars."""
    by = {}
    for r in records:
        fn = r.get("fullName")
        if not fn:
            continue
        if fn not in by or r.get("stargazersCount", 0) > by[fn].get("stargazersCount", 0):
            tag = by[fn].get("_tag") if fn in by else r.get("_tag")
            by[fn] = dict(r)
            by[fn]["_tag"] = tag or r.get("_tag")
    return list(by.values())


def filter_archived(records):
    """Exclude archived repositories."""
    return [r for r in records if not r.get("isArchived", False)]


def get_license_key(r):
    """Extract declared license key from record."""
    lic = r.get("license")
    if isinstance(lic, dict):
        return (lic.get("key") or "").strip().lower()
    elif isinstance(lic, str):
        return lic.strip().lower()
    return (r.get("license_key") or "").strip().lower()


def filter_declared_license(records):
    """Require non-empty declared license."""
    return [r for r in records if bool(get_license_key(r))]


def parse_pushed_at(r):
    """Parse pushed date/time safely."""
    val = r.get("pushedAt") or r.get("pushed") or ""
    if not val:
        return None
    try:
        iso_str = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            dt = datetime.strptime(str(val)[:10], "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def filter_active_after(records, cutoff=ACTIVE_AFTER):
    """Keep records pushed at or after the cutoff date."""
    res = []
    for r in records:
        d = parse_pushed_at(r)
        if d and d >= cutoff:
            res.append(r)
    return res


def classify_license(license_key):
    """Classify license key into permissive, copyleft, or other."""
    k = (license_key or "").lower().strip()
    if k in PERMISSIVE:
        return "permissive"
    if k in COPYLEFT:
        return "copyleft"
    return "other"


def transform_record(r):
    """Format record into final standardized schema."""
    k = get_license_key(r)
    cls = classify_license(k)
    pushed = ""
    if r.get("pushed"):
        pushed = str(r.get("pushed"))[:10]
    elif r.get("pushedAt"):
        pushed = str(r.get("pushedAt"))[:10]

    lic_name = ""
    if isinstance(r.get("license"), dict):
        lic_name = r.get("license", {}).get("name") or ""
    elif isinstance(r.get("license"), str):
        lic_name = r.get("license")

    return {
        "fullName": r["fullName"],
        "url": r.get("url") or f"https://github.com/{r['fullName']}",
        "stars": int(r.get("stargazersCount", r.get("stars", 0))),
        "forks": int(r.get("forksCount", r.get("forks", 0))),
        "pushed": pushed,
        "language": r.get("language") or "",
        "license_key": k,
        "license": lic_name,
        "license_class": cls,
        "reuse_terms": REUSE[cls],
        "archived": False,
        "description": (r.get("description") or "").strip(),
        "project_area": r.get("_tag", r.get("project_area", "?")),
    }


def process_dataset(raw_records, cutoff=ACTIVE_AFTER):
    """Execute full filter funnel from raw records to sorted final dataset."""
    c0 = len(raw_records)
    dedup = deduplicate_records(raw_records)
    c1 = len(dedup)
    s2 = filter_archived(dedup)
    c2 = len(s2)
    s3 = filter_declared_license(s2)
    c3 = len(s3)
    s4 = filter_active_after(s3, cutoff=cutoff)
    c4 = len(s4)

    final = [transform_record(r) for r in s4]
    final.sort(key=lambda x: (x["project_area"], -x["stars"]))

    funnel_counts = {
        "raw": c0,
        "dedup": c1,
        "non_archived": c2,
        "licensed": c3,
        "active": c4,
        "final": len(final),
    }
    return final, funnel_counts


def export_dataset_json(records, filepath):
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=1)


def export_dataset_csv(records, filepath):
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    if not records:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("")
        return
    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(records)


def export_reuse_subsets(records, out_dir):
    permissive = [r for r in records if r["license_class"] == "permissive"]
    copyleft = [r for r in records if r["license_class"] == "copyleft"]
    export_dataset_json(permissive, os.path.join(out_dir, "reuse_permissive.json"))
    export_dataset_json(copyleft, os.path.join(out_dir, "reuse_copyleft.json"))
    return len(permissive), len(copyleft)


def print_funnel_and_summary(final, funnel_counts=None):
    if funnel_counts:
        c0 = funnel_counts["raw"]
        c1 = funnel_counts["dedup"]
        c2 = funnel_counts["non_archived"]
        c3 = funnel_counts["licensed"]
        c4 = funnel_counts["active"]
        print("=== FILTER FUNNEL (before → after) ===")
        print(f"  stage 0 raw rows returned by API : {c0}")
        print(f"  stage 1 after dedupe (unique)    : {c1}   (removed {c0-c1})")
        print(f"  stage 2 after exclude archived   : {c2}   (removed {c1-c2})")
        print(f"  stage 3 after require license    : {c3}   (removed {c2-c3})")
        print(f"  stage 4 after active>2025-04-01  : {c4}   (removed {c3-c4})")
        print(f"  FINAL qualifying repositories    : {len(final)}")
        print()

    proj = Counter(r["project_area"] for r in final)
    lic = Counter(r["license"] for r in final)
    cls = Counter(r["license_class"] for r in final)

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


def verify_dataset_files(root_dir="."):
    """Verify integrity of repositories_dataset.json, csv, and reuse subsets."""
    json_path = os.path.join(root_dir, "repositories_dataset.json")
    csv_path = os.path.join(root_dir, "repositories_dataset.csv")
    perm_path = os.path.join(root_dir, "reuse_permissive.json")
    copy_path = os.path.join(root_dir, "reuse_copyleft.json")

    assert os.path.isfile(json_path), f"Missing {json_path}"
    assert os.path.isfile(csv_path), f"Missing {csv_path}"
    assert os.path.isfile(perm_path), f"Missing {perm_path}"
    assert os.path.isfile(copy_path), f"Missing {copy_path}"

    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    with open(perm_path, "r", encoding="utf-8") as fh:
        perm = json.load(fh)
    with open(copy_path, "r", encoding="utf-8") as fh:
        copy = json.load(fh)

    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert len(data) == len(rows), f"Row count mismatch: JSON {len(data)} vs CSV {len(rows)}"
    assert len(data) > 0, "Dataset is empty"

    required_keys = {
        "fullName", "url", "stars", "forks", "pushed", "language",
        "license_key", "license", "license_class", "project_area"
    }
    for idx, item in enumerate(data):
        missing = required_keys - set(item.keys())
        assert not missing, f"Item {idx} ({item.get('fullName')}) missing keys: {missing}"
        assert not item.get("archived", False), f"Archived repository found: {item.get('fullName')}"
        assert item.get("license_key"), f"Missing license key: {item.get('fullName')}"

    # Partition check
    perm_names = {r["fullName"] for r in perm}
    copy_names = {r["fullName"] for r in copy}
    assert perm_names.isdisjoint(copy_names), "Permissive and Copyleft overlap"

    perm_in_data = {r["fullName"] for r in data if r["license_class"] == "permissive"}
    copy_in_data = {r["fullName"] for r in data if r["license_class"] == "copyleft"}
    assert perm_names == perm_in_data, "Permissive subset mismatch"
    assert copy_names == copy_in_data, "Copyleft subset mismatch"

    return len(data), len(perm), len(copy)


def main():
    parser = argparse.ArgumentParser(description="Process GitHub API scale repository search results.")
    parser.add_argument("--raw-dir", default=OUT, help="Directory containing raw *.json batch files")
    parser.add_argument("--out-dir", default=OUT, help="Output directory for generated dataset files")
    parser.add_argument("--cutoff", default="2025-04-01", help="Pushed-at cutoff date floor (YYYY-MM-DD)")
    parser.add_argument("--verify", action="store_true", help="Verify integrity of current repo dataset files")
    args = parser.parse_args()

    if args.verify:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        total, perm, copy = verify_dataset_files(repo_dir)
        print(f"Verified dataset files in {repo_dir}:")
        print(f"  Total repositories: {total}")
        print(f"  Permissive reuse  : {perm}")
        print(f"  Copyleft reuse    : {copy}")
        with open(os.path.join(repo_dir, "repositories_dataset.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        print_funnel_and_summary(data)
        return

    cutoff_dt = datetime.strptime(args.cutoff, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    raw = load_raw_batches(args.raw_dir)
    if not raw:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.isfile(os.path.join(repo_dir, "repositories_dataset.json")):
            print(f"No raw files found in {args.raw_dir}; verifying existing repository dataset.")
            total, perm, copy = verify_dataset_files(repo_dir)
            with open(os.path.join(repo_dir, "repositories_dataset.json"), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            print_funnel_and_summary(data)
            return
        else:
            print(f"No raw files found in {args.raw_dir} and no dataset found in {repo_dir}.")
            return

    final, counts = process_dataset(raw, cutoff=cutoff_dt)
    os.makedirs(args.out_dir, exist_ok=True)
    export_dataset_json(final, os.path.join(args.out_dir, "dataset.json"))
    export_dataset_csv(final, os.path.join(args.out_dir, "dataset.csv"))
    export_reuse_subsets(final, args.out_dir)
    print_funnel_and_summary(final, counts)


if __name__ == "__main__":
    main()
