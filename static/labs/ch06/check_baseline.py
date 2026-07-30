#!/usr/bin/env python3
"""Validate the ch06 development baseline without third-party packages."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


RULE_KEYS = {
    "id",
    "title",
    "level",
    "status",
    "owner",
    "scope",
    "statement",
    "rationale",
    "evidence",
    "exception",
    "checks",
}
TOP_KEYS = {
    "schema_version",
    "baseline_version",
    "published_on",
    "compatibility",
    "source_chapters",
    "future_evidence_chapters",
    "levels",
    "rules",
}
RULE_ID = re.compile(r"^(SAFE|DEFAULT|PREF)-[A-Z]{4}-[0-9]{3}$")
PREFIX_LEVEL = {
    "SAFE": "safety",
    "DEFAULT": "default",
    "PREF": "preference",
}
EXCEPTION_MODES = {
    "safety": {"none", "breakglass"},
    "default": {"waiver"},
    "preference": {"review"},
}
CHECK_KINDS = {"automated", "runtime", "review"}


class DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return value


def nonempty_string(value: Any, minimum: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= minimum


def unique_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(nonempty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def artifact_path(repo_root: Path, public_path: str) -> Path:
    if not public_path.startswith("/labs/"):
        raise ValueError(
            f"evidence artifact must use a /labs/... public path: {public_path}"
        )
    return repo_root / "static" / public_path.removeprefix("/")


def validate_registry(
    registry: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> dict[str, Any]:
    if set(registry) != TOP_KEYS:
        errors.append(
            "registry top-level keys differ: "
            f"missing={sorted(TOP_KEYS - set(registry))}, "
            f"extra={sorted(set(registry) - TOP_KEYS)}"
        )

    if registry.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    baseline_version = registry.get("baseline_version")
    if not isinstance(baseline_version, str) or not re.fullmatch(
        r"0\.1\.[0-9]+", baseline_version
    ):
        errors.append("baseline_version must match 0.1.x")

    try:
        dt.date.fromisoformat(str(registry.get("published_on")))
    except ValueError:
        errors.append("published_on must be an ISO date")

    expected_sources = [f"ch0{number}" for number in range(1, 6)]
    expected_future = ["ch07", "ch08", "ch09", "ch10", "ch11"]
    if registry.get("source_chapters") != expected_sources:
        errors.append(f"source_chapters must be exactly {expected_sources}")
    if registry.get("future_evidence_chapters") != expected_future:
        errors.append(
            f"future_evidence_chapters must be exactly {expected_future}"
        )

    levels = registry.get("levels")
    if not isinstance(levels, dict) or set(levels) != set(EXCEPTION_MODES):
        errors.append("levels must define safety, default, preference exactly")

    rules = registry.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules must be a non-empty array")
        rules = []

    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    level_counts: collections.Counter[str] = collections.Counter()
    evidence_chapters: set[str] = set()
    referenced_artifacts: set[str] = set()
    safety_non_review = 0

    for index, rule in enumerate(rules, start=1):
        prefix = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be an object")
            continue

        if set(rule) != RULE_KEYS:
            errors.append(
                f"{prefix} keys differ: "
                f"missing={sorted(RULE_KEYS - set(rule))}, "
                f"extra={sorted(set(rule) - RULE_KEYS)}"
            )

        rule_id = rule.get("id")
        match = RULE_ID.fullmatch(rule_id) if isinstance(rule_id, str) else None
        if match is None:
            errors.append(f"{prefix}.id has invalid format: {rule_id!r}")
        elif rule_id in seen_ids:
            errors.append(f"duplicate rule id: {rule_id}")
        else:
            seen_ids.add(rule_id)

        title = rule.get("title")
        if not nonempty_string(title):
            errors.append(f"{prefix}.title must be non-empty")
        elif title in seen_titles:
            errors.append(f"duplicate rule title: {title}")
        else:
            seen_titles.add(title)

        level = rule.get("level")
        if level not in EXCEPTION_MODES:
            errors.append(f"{prefix}.level is invalid: {level!r}")
        else:
            level_counts[level] += 1
            if match and PREFIX_LEVEL[match.group(1)] != level:
                errors.append(f"{rule_id}: ID prefix and level disagree")

        if rule.get("status") not in {"active", "deprecated"}:
            errors.append(f"{prefix}.status must be active or deprecated")
        if not nonempty_string(rule.get("owner")):
            errors.append(f"{prefix}.owner must be non-empty")
        if not unique_string_list(rule.get("scope")):
            errors.append(f"{prefix}.scope must be a unique non-empty string list")
        if not nonempty_string(rule.get("statement"), 20):
            errors.append(f"{prefix}.statement is too short")
        if not nonempty_string(rule.get("rationale"), 20):
            errors.append(f"{prefix}.rationale is too short")

        evidence = rule.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{prefix}.evidence must be non-empty")
            evidence = []
        for evidence_index, item in enumerate(evidence, start=1):
            evidence_prefix = f"{prefix}.evidence[{evidence_index}]"
            if not isinstance(item, dict) or set(item) != {
                "chapter",
                "artifact",
                "observation",
            }:
                errors.append(
                    f"{evidence_prefix} must contain chapter/artifact/observation"
                )
                continue
            chapter = item["chapter"]
            public_path = item["artifact"]
            observation = item["observation"]
            if chapter not in expected_sources:
                errors.append(f"{evidence_prefix}.chapter is outside ch01-ch05")
            else:
                evidence_chapters.add(chapter)
            if not nonempty_string(observation, 10):
                errors.append(f"{evidence_prefix}.observation is too short")
            if not isinstance(public_path, str):
                errors.append(f"{evidence_prefix}.artifact must be a string")
            else:
                referenced_artifacts.add(public_path)
                try:
                    resolved = artifact_path(repo_root, public_path)
                except ValueError as exc:
                    errors.append(str(exc))
                else:
                    if not resolved.is_file():
                        errors.append(
                            f"{evidence_prefix}.artifact does not exist: "
                            f"{resolved}"
                        )

        exception = rule.get("exception")
        if not isinstance(exception, dict) or set(exception) != {
            "mode",
            "requirements",
        }:
            errors.append(
                f"{prefix}.exception must contain mode and requirements exactly"
            )
        else:
            mode = exception["mode"]
            if level in EXCEPTION_MODES and mode not in EXCEPTION_MODES[level]:
                errors.append(
                    f"{rule_id}: exception mode {mode!r} is invalid for {level}"
                )
            if not unique_string_list(exception["requirements"]):
                errors.append(
                    f"{prefix}.exception.requirements must be non-empty/unique"
                )

        checks = rule.get("checks")
        if not isinstance(checks, list) or not checks:
            errors.append(f"{prefix}.checks must be non-empty")
            checks = []
        rule_check_kinds: set[str] = set()
        for check_index, check in enumerate(checks, start=1):
            check_prefix = f"{prefix}.checks[{check_index}]"
            if not isinstance(check, dict) or set(check) != {
                "kind",
                "criterion",
            }:
                errors.append(
                    f"{check_prefix} must contain kind and criterion exactly"
                )
                continue
            if check["kind"] not in CHECK_KINDS:
                errors.append(f"{check_prefix}.kind is invalid")
            else:
                rule_check_kinds.add(check["kind"])
            if not nonempty_string(check["criterion"], 10):
                errors.append(f"{check_prefix}.criterion is too short")
        if level == "safety" and rule_check_kinds & {"automated", "runtime"}:
            safety_non_review += 1

    if evidence_chapters != set(expected_sources):
        errors.append(
            "active evidence does not cover all source chapters: "
            f"{sorted(evidence_chapters)}"
        )

    if set(level_counts) != set(EXCEPTION_MODES):
        errors.append("rules must include all three levels")

    canonical = json.dumps(
        registry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return {
        "rule_count": len(rules),
        "level_counts": level_counts,
        "source_chapter_count": len(evidence_chapters),
        "artifact_reference_count": len(referenced_artifacts),
        "safety_non_review_count": safety_non_review,
        "checksum": hashlib.sha256(canonical).hexdigest(),
        "rule_ids": seen_ids,
    }


def validate_manifest(
    manifest: dict[str, Any],
    baseline_version: Any,
    script_dir: Path,
    errors: list[str],
) -> int:
    expected_keys = {
        "manifest_version",
        "baseline_version",
        "chapter",
        "canonical_registry",
        "required_artifacts",
        "required_gate_actions",
        "v1_exit_chapter",
        "v1_required_evidence",
    }
    if set(manifest) != expected_keys:
        errors.append("delivery manifest keys differ from the v1 contract")
    if manifest.get("manifest_version") != 1:
        errors.append("delivery manifest_version must be 1")
    if manifest.get("baseline_version") != baseline_version:
        errors.append("delivery manifest baseline_version disagrees")
    if manifest.get("chapter") != "ch06":
        errors.append("delivery manifest chapter must be ch06")
    if manifest.get("canonical_registry") != "baseline-v0.1.json":
        errors.append("canonical_registry must be baseline-v0.1.json")
    if manifest.get("v1_exit_chapter") != "ch12":
        errors.append("v1_exit_chapter must be ch12")

    required_actions = manifest.get("required_gate_actions")
    if required_actions != ["static", "live", "negative", "review", "all"]:
        errors.append("required_gate_actions order/content drifted")

    artifacts = manifest.get("required_artifacts")
    if not unique_string_list(artifacts):
        errors.append("required_artifacts must be a unique non-empty list")
        return 0
    for name in artifacts:
        if "/" in name or name.startswith("."):
            errors.append(f"required artifact must be a local basename: {name}")
        elif not (script_dir / name).is_file():
            errors.append(f"required artifact is missing: {name}")
    return len(artifacts)


def validate_guide(
    guide_path: Path,
    expected_rule_ids: set[str],
    errors: list[str],
) -> None:
    guide = guide_path.read_text(encoding="utf-8")
    guide_ids = re.findall(
        r"\|\s*((?:SAFE|DEFAULT|PREF)-[A-Z]{4}-[0-9]{3})\s*\|",
        guide,
    )
    counts = collections.Counter(guide_ids)
    if set(counts) != expected_rule_ids:
        errors.append(
            "baseline guide rule IDs differ: "
            f"missing={sorted(expected_rule_ids - set(counts))}, "
            f"extra={sorted(set(counts) - expected_rule_ids)}"
        )
    repeated = sorted(rule_id for rule_id, count in counts.items() if count != 1)
    if repeated:
        errors.append(f"baseline guide repeats rule IDs: {repeated}")


def scan_source_safety(repo_root: Path, errors: list[str]) -> int:
    lab_root = repo_root / "static" / "labs"
    source_files: list[Path] = []
    for chapter_number in range(1, 7):
        chapter_dir = lab_root / f"ch{chapter_number:02d}"
        if not chapter_dir.is_dir():
            errors.append(f"missing lab directory: {chapter_dir}")
            continue
        source_files.extend(
            path
            for path in chapter_dir.rglob("*")
            if path.is_file()
            and path.suffix in {".sql", ".sh", ".json", ".yml", ".yaml"}
        )
        source_files.extend(chapter_dir.glob("*.conf.example"))

    secret_patterns = {
        "PGPASSWORD assignment": re.compile(r"(?im)^\s*(?:export\s+)?PGPASSWORD\s*="),
        "credential-bearing PostgreSQL URI": re.compile(
            r"postgres(?:ql)?://[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
        "password assignment": re.compile(
            r"(?im)^\s*(?:password|passphrase)\s*=\s*\S+"
        ),
    }
    destructive_pattern = re.compile(
        r"\bDROP\s+(?:DATABASE|ROLE)\b", re.IGNORECASE
    )

    for path in sorted(set(source_files)):
        text = path.read_text(encoding="utf-8")
        for label, pattern in secret_patterns.items():
            if pattern.search(text):
                errors.append(
                    f"{label} found in managed source: "
                    f"{path.relative_to(repo_root)}"
                )
        if destructive_pattern.search(text):
            if path.name != "reset.sql" or "RESET_" not in text:
                errors.append(
                    "DROP DATABASE/ROLE outside tokenized reset.sql: "
                    f"{path.relative_to(repo_root)}"
                )
    return len(set(source_files))


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_repo = script_dir.parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=script_dir / "baseline-v0.1.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=script_dir / "delivery-manifest.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=script_dir / "baseline-schema.json",
    )
    parser.add_argument(
        "--guide",
        type=Path,
        default=script_dir / "baseline-guide.md",
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []

    try:
        registry = load_json(args.registry)
        manifest = load_json(args.manifest)
        schema = load_json(args.schema)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("baseline-schema.json is not draft 2020-12")

    summary = validate_registry(registry, args.repo_root.resolve(), errors)
    artifact_count = validate_manifest(
        manifest,
        registry.get("baseline_version"),
        args.registry.resolve().parent,
        errors,
    )
    try:
        validate_guide(args.guide, summary["rule_ids"], errors)
    except OSError as exc:
        errors.append(str(exc))
    scanned_source_count = scan_source_safety(
        args.repo_root.resolve(),
        errors,
    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"status=failed error_count={len(errors)}", file=sys.stderr)
        return 1

    counts = summary["level_counts"]
    print("status=ok")
    print(f"baseline_version={registry['baseline_version']}")
    print(f"rule_count={summary['rule_count']}")
    print(f"safety_count={counts['safety']}")
    print(f"default_count={counts['default']}")
    print(f"preference_count={counts['preference']}")
    print(f"safety_non_review_count={summary['safety_non_review_count']}")
    print(f"source_chapter_count={summary['source_chapter_count']}")
    print(f"artifact_reference_count={summary['artifact_reference_count']}")
    print(f"delivery_artifact_count={artifact_count}")
    print(f"scanned_source_count={scanned_source_count}")
    print(f"baseline_checksum={summary['checksum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
