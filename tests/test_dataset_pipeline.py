import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import pytest

import process_scale


def test_license_classification_permissive():
    for lic in ["mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "0bsd", "unlicense", "mpl-2.0"]:
        assert process_scale.classify_license(lic) == "permissive"
        assert process_scale.classify_license(lic.upper()) == "permissive"


def test_license_classification_copyleft():
    for lic in ["gpl-3.0", "gpl-2.0", "agpl-3.0", "lgpl-3.0", "lgpl-2.1", "epl-2.0"]:
        assert process_scale.classify_license(lic) == "copyleft"
        assert process_scale.classify_license(lic.upper()) == "copyleft"


def test_license_classification_other():
    for lic in ["custom", "proprietary", "unknown", ""]:
        assert process_scale.classify_license(lic) == "other"


def test_get_license_key():
    rec_dict = {"license": {"key": "MIT", "name": "MIT License"}}
    assert process_scale.get_license_key(rec_dict) == "mit"

    rec_str = {"license": "apache-2.0"}
    assert process_scale.get_license_key(rec_str) == "apache-2.0"

    rec_fallback = {"license_key": "gpl-3.0"}
    assert process_scale.get_license_key(rec_fallback) == "gpl-3.0"

    rec_empty = {}
    assert process_scale.get_license_key(rec_empty) == ""


def test_parse_pushed_at():
    dt_iso = process_scale.parse_pushed_at({"pushedAt": "2026-08-17T12:34:56Z"})
    assert dt_iso is not None
    assert dt_iso.year == 2026
    assert dt_iso.month == 8
    assert dt_iso.tzinfo is not None

    dt_ymd = process_scale.parse_pushed_at({"pushed": "2025-10-01"})
    assert dt_ymd is not None
    assert dt_ymd.year == 2025
    assert dt_ymd.month == 10

    dt_invalid = process_scale.parse_pushed_at({"pushed": "invalid-date"})
    assert dt_invalid is None


def test_filter_predicates():
    # Load two real records from repositories_dataset.json
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(repo_root, "repositories_dataset.json")
    with open(json_path, "r", encoding="utf-8") as fh:
        real_records = json.load(fh)[:2]

    rec1 = dict(real_records[0])
    rec2 = dict(real_records[1])
    rec2["isArchived"] = True

    active = process_scale.filter_archived([rec1, rec2])
    assert len(active) == 1
    assert active[0]["fullName"] == rec1["fullName"]

    rec_unlicensed = dict(rec1)
    rec_unlicensed["license"] = None
    rec_unlicensed["license_key"] = None
    licensed = process_scale.filter_declared_license([rec1, rec_unlicensed])
    assert len(licensed) == 1
    assert licensed[0]["fullName"] == rec1["fullName"]

    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
    after = process_scale.filter_active_after([rec1], cutoff=cutoff)
    assert len(after) == 1


def test_deduplicate_records():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(repo_root, "repositories_dataset.json")
    with open(json_path, "r", encoding="utf-8") as fh:
        sample = dict(json.load(fh)[0])

    entry1 = dict(sample)
    entry1["stargazersCount"] = 100
    entry1["_tag"] = "area_a"

    entry2 = dict(sample)
    entry2["stargazersCount"] = 500
    entry2["_tag"] = "area_b"

    deduped = process_scale.deduplicate_records([entry1, entry2])
    assert len(deduped) == 1
    assert deduped[0]["stargazersCount"] == 500
    assert deduped[0]["fullName"] == sample["fullName"]


def test_transform_record():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(repo_root, "repositories_dataset.json")
    with open(json_path, "r", encoding="utf-8") as fh:
        sample = json.load(fh)[0]

    raw_input = {
        "fullName": sample["fullName"],
        "url": sample["url"],
        "stargazersCount": sample["stars"],
        "forksCount": sample["forks"],
        "pushedAt": sample["pushed"] + "T00:00:00Z",
        "language": sample["language"],
        "license": {"key": sample["license_key"], "name": sample["license"]},
        "description": sample["description"],
        "_tag": sample["project_area"]
    }

    out = process_scale.transform_record(raw_input)
    assert out["fullName"] == sample["fullName"]
    assert out["stars"] == sample["stars"]
    assert out["forks"] == sample["forks"]
    assert out["license_key"] == sample["license_key"]
    assert out["license_class"] == sample["license_class"]
    assert out["project_area"] == sample["project_area"]
    assert out["archived"] is False


def test_process_dataset_pipeline():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(repo_root, "repositories_dataset.json")
    with open(json_path, "r", encoding="utf-8") as fh:
        dataset = json.load(fh)

    # Use first 10 records transformed into raw shape
    raw_batch = []
    for r in dataset[:10]:
        raw_batch.append({
            "fullName": r["fullName"],
            "url": r["url"],
            "stargazersCount": r["stars"],
            "forksCount": r["forks"],
            "pushedAt": r["pushed"] + "T00:00:00Z",
            "language": r["language"],
            "license": {"key": r["license_key"], "name": r["license"]},
            "description": r["description"],
            "_tag": r["project_area"],
            "isArchived": False
        })

    final, counts = process_scale.process_dataset(raw_batch, cutoff=process_scale.ACTIVE_AFTER)
    assert len(final) == 10
    assert counts["final"] == 10
    assert counts["raw"] == 10


def test_export_dataset_roundtrip():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(repo_root, "repositories_dataset.json")
    with open(json_path, "r", encoding="utf-8") as fh:
        records = json.load(fh)[:5]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_json = os.path.join(tmpdir, "test.json")
        out_csv = os.path.join(tmpdir, "test.csv")

        process_scale.export_dataset_json(records, out_json)
        process_scale.export_dataset_csv(records, out_csv)
        perm_cnt, copy_cnt = process_scale.export_reuse_subsets(records, tmpdir)

        assert os.path.isfile(out_json)
        assert os.path.isfile(out_csv)

        with open(out_json, "r", encoding="utf-8") as fh:
            loaded_json = json.load(fh)
        assert len(loaded_json) == 5

        with open(out_csv, "r", encoding="utf-8") as fh:
            loaded_csv = list(csv.DictReader(fh))
        assert len(loaded_csv) == 5
        assert loaded_csv[0]["fullName"] == records[0]["fullName"]


def test_real_dataset_integrity():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    total, perm, copy = process_scale.verify_dataset_files(repo_root)

    assert total == 668
    assert perm == 492
    assert copy == 90
    assert (perm + copy) <= total


def test_cli_verify_flag():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(repo_root, "process_scale.py")
    result = subprocess.run(
        [sys.executable, script, "--verify"],
        cwd=repo_root,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Total repositories: 668" in result.stdout
    assert "Permissive reuse  : 492" in result.stdout
    assert "Copyleft reuse    : 90" in result.stdout
