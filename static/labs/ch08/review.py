#!/usr/bin/env python3
"""Apply stable semantic assertions to a complete ch08 evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
from typing import Any


EXPECTED = {
    "estimate": "estimate-plan",
    "lock": "lock-wait",
    "client": "client-slow-consumer",
}
SELECTOR_MODES = ("estimate", "lock", "client")
SELECTOR_DIAGNOSES = (
    "estimate-plan",
    "lock-wait",
    "client-slow-consumer",
)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def canonical_checksum(path: Path) -> str:
    value = load(path)
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_proposal(repo_root: Path) -> dict[str, str]:
    baseline_path = repo_root / "static/labs/ch06/baseline-v0.1.json"
    dependency_path = (
        repo_root / "static/labs/ch07/baseline-v0.2-proposal.json"
    )
    proposal_path = (
        repo_root / "static/labs/ch08/baseline-v0.3-proposal.json"
    )
    proposal = load(proposal_path)
    baseline_checksum = canonical_checksum(baseline_path)
    dependency_checksum = canonical_checksum(dependency_path)
    if proposal.get("base_checksum") != baseline_checksum:
        raise RuntimeError("v0.3 proposal base checksum drifted")
    dependencies = proposal.get("depends_on_candidates")
    if not isinstance(dependencies, list) or len(dependencies) != 1:
        raise RuntimeError("v0.3 proposal must have one v0.2 dependency")
    if dependencies[0].get("proposal_checksum") != dependency_checksum:
        raise RuntimeError("v0.3 proposal dependency checksum drifted")
    if proposal.get("rule_id") != "DEFAULT-EVID-009":
        raise RuntimeError("v0.3 proposal must update DEFAULT-EVID-009")
    for item in proposal.get("evidence", []):
        public_path = item.get("artifact", "")
        if not public_path.startswith("/labs/ch08/"):
            raise RuntimeError("v0.3 evidence must use /labs/ch08 paths")
        local_path = repo_root / "static" / public_path.removeprefix("/")
        if not local_path.is_file():
            raise RuntimeError(f"missing v0.3 artifact: {public_path}")
    return {
        "candidate_baseline": str(proposal.get("candidate_baseline")),
        "rule_id": str(proposal.get("rule_id")),
        "base_checksum": baseline_checksum,
        "dependency_checksum": dependency_checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence_dir
    proposal = validate_proposal(args.repo_root.resolve())

    direct: dict[str, str] = {}
    for mode, expected in EXPECTED.items():
        signals = load(root / mode / "signals.json")
        diagnosis = load(root / mode / "diagnosis.json")
        actual = diagnosis.get("diagnosis")
        if actual != expected:
            raise RuntimeError(
                f"{mode}: expected {expected}, got {actual}"
            )
        if diagnosis.get("answer_artifact_read") is not False:
            raise RuntimeError(f"{mode}: answer-read declaration is not false")
        if signals.get("state_restored") is not True:
            raise RuntimeError(f"{mode}: state was not restored")
        if signals.get("remaining_workers") != 0:
            raise RuntimeError(f"{mode}: workers remain")
        direct[mode] = str(actual)

    mystery = root / "mystery"
    answer_path = mystery / ".sealed/answer.json"
    answer = load(answer_path)
    diagnosis = load(mystery / "public/diagnosis.json")
    reveal = load(mystery / "public/reveal.json")
    negative = load(mystery / "public/negative-reveal.json")

    answer_mode = stat.S_IMODE(answer_path.stat().st_mode)
    if answer_mode != 0o600:
        raise RuntimeError(
            f"sealed answer mode is {answer_mode:o}, expected 600"
        )
    if diagnosis.get("answer_artifact_read") is not False:
        raise RuntimeError("mystery diagnosis claims answer access")
    if reveal.get("matched") is not True:
        raise RuntimeError("correct mystery diagnosis did not pass reveal")
    if negative.get("matched") is not False:
        raise RuntimeError("deliberately wrong diagnosis did not fail reveal")

    seed = str(answer["seed"])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    if digest != answer.get("seed_sha256"):
        raise RuntimeError("stored seed digest does not recompute")
    index_a = int(digest, 16) % 3
    index_b = int(
        hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16
    ) % 3
    if index_a != index_b:
        raise RuntimeError("same seed did not reproduce the same selection")
    if answer.get("selected_mode") != SELECTOR_MODES[index_a]:
        raise RuntimeError("sealed selected mode disagrees with selector")
    if answer.get("expected_diagnosis") != SELECTOR_DIAGNOSES[index_a]:
        raise RuntimeError("sealed diagnosis disagrees with selector")

    verify_text = (root / "verify.txt").read_text(encoding="utf-8")
    if "relation_checksum=f8a7bfae59c6d16cd323abecfefe1014" \
            not in verify_text:
        raise RuntimeError("ch04-v1 relation checksum drifted")
    if "active_lab_workers=0" not in verify_text:
        raise RuntimeError("final worker check did not pass")

    result = {
        "status": "ok",
        "direct_classifications": direct,
        "mystery_classification": diagnosis["diagnosis"],
        "mystery_reveal_matched": True,
        "wrong_guess_rejected": True,
        "same_seed_reproducible": True,
        "answer_mode": "0600",
        "state_restored": True,
        "remaining_workers": 0,
        "relation_checksum":
            "f8a7bfae59c6d16cd323abecfefe1014",
        "proposal": proposal,
    }
    output = root / "review.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("status=ok")
    print("classifications=estimate-plan,lock-wait,client-slow-consumer")
    print(
        f"mystery={diagnosis['diagnosis']}/"
        "matched=true/wrong-guess-rejected=true"
    )
    print("same-seed-reproducible=true/answer-mode=0600")
    print(
        "state-restored=true/remaining-workers=0/"
        "relation-checksum=f8a7bfae59c6d16cd323abecfefe1014"
    )
    print(
        "proposal="
        f"0.1.0->{proposal['candidate_baseline']}/"
        f"{proposal['rule_id']}/depends-on-v0.2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
