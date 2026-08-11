"""
Drives scripts/check-canon-consistency.py — the SHR-003..SHR-006 canon audit.

Two halves:

* Real-tree tests bind the audit to the actual checkout: the authority map must
  declare a total order, ADR-0001 must be the accepted authority for the
  canonical-store question, every baseline acknowledgement must be attributable,
  and the checker must exit clean.
* Synthetic-tree tests are the anti-vacuity proof. A checker that never fires is
  worthless, so a detector is fed a tmp_path repo with one injected defect and
  must fail on it — and must stay silent when the same defect lives under an
  archived glob.

Coverage is partial, and saying otherwise in a file whose whole purpose is
punishing unverified claims would be the exact failure SHR-006 exists to catch.
What has a synthetic single-defect proof:

    markdown-canonical, unclassified-surface, unledgered-claim, claim-drift,
    cites-archived, archived-unmarked, unreadable-surface,
    excluded-into-unscoped, markerless-archived-entry, ledger ReDoS,
    ledger path escape, missing evidence handle, and the reconcile verdicts
    NEW, DROPPED, COUNT DRIFT, CONTENT DRIFT, REGRESSED.

What still has none — each is a real gap, not a decision:

    ambiguous-authority, dead-glob, missing-authority, authority-not-accepted,
    canonical-wiki, markdown-source-of-truth, status-enum-divergence,
    status-missing, status-invalid, agent-cap-contradiction.

The script filename has hyphens and is not importable; it is driven via
subprocess, matching tests/test_validator.py and tests/test_version_consistency.py.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_REL = "scripts/check-canon-consistency.py"
AUTHORITY_REL = "docs/canon/SOURCE_AUTHORITY.md"
BASELINE_REL = "docs/canon/canon-baseline.json"
LEDGER_REL = "docs/canon/PUBLIC_CLAIM_LEDGER.json"

AUTHORITY_BLOCK_RE = re.compile(
    r"```json\s+shiroe\.source-authority/v1\s*\n(.*?)\n```",
    re.DOTALL,
)

# The five source classes SHR-003 names explicitly.
SHR003_REQUIRED_TIER_IDS = {
    "code-and-schemas",
    "accepted-adrs",
    "agents-spec",
    "glossary",
    "generated-docs",
}

# Contradictions this PR only *detects*. Each is (surface, rule, probe regex).
# Written as an implication: present on the surface => acknowledged in baseline.
# PR 02 removes the text; the assertion then passes vacuously instead of flipping red.
KNOWN_CONTRADICTIONS = [
    ("SOUL.md", "markdown-canonical", r"(?i)canonical[^.;\n]{0,60}\bmarkdown\b"),
    ("AGENTS.md", "markdown-canonical", r"(?i)canonical[^.;\n]{0,60}\bmarkdown\b"),
    ("AGENTS.md", "canonical-wiki", r"(?i)canonical\s+wiki"),
]


def _run(
    script: Path, root: Path, budget_s: float | None = None
) -> subprocess.CompletedProcess[str]:
    # timeout is load-bearing, not hygiene: the denial-of-service tests below
    # assert the checker *terminates*, and without a bound their failure mode is
    # a pytest run that never finishes rather than a red test.
    env = None
    if budget_s is not None:
        env = {**os.environ, "CANON_AUDIT_BUDGET_S": str(budget_s)}
    return subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def _authority_map(repo_root: Path) -> dict:
    text = (repo_root / AUTHORITY_REL).read_text(encoding="utf-8")
    blocks = AUTHORITY_BLOCK_RE.findall(text)
    assert len(blocks) == 1, (
        f"{AUTHORITY_REL} must carry exactly one "
        f"```json shiroe.source-authority/v1 block, found {len(blocks)}"
    )
    return json.loads(blocks[0])


# --------------------------------------------------------------------------- #
# Real tree
# --------------------------------------------------------------------------- #


def test_canon_script_exists(repo_root: Path) -> None:
    assert (repo_root / SCRIPT_REL).exists(), f"{SCRIPT_REL} is missing"


def test_canon_audit_exits_clean_on_real_tree(repo_root: Path) -> None:
    result = _run(repo_root / SCRIPT_REL, repo_root)
    assert result.returncode == 0, (
        f"canon audit failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_authority_map_declares_a_total_order(repo_root: Path) -> None:
    amap = _authority_map(repo_root)
    ranks = [t["rank"] for t in amap["tiers"]]
    assert len(ranks) == len(set(ranks)), f"tier ranks are not unique: {ranks}"
    assert sorted(ranks) == list(range(1, len(ranks) + 1)), (
        f"tier ranks must be contiguous 1..N, got {sorted(ranks)}"
    )


def test_authority_map_covers_shr003_source_classes(repo_root: Path) -> None:
    amap = _authority_map(repo_root)
    ids = {t["id"] for t in amap["tiers"]}
    missing = SHR003_REQUIRED_TIER_IDS - ids
    assert not missing, f"authority map is missing SHR-003 source classes: {sorted(missing)}"


def test_authority_map_has_archived_and_unscoped_sections(repo_root: Path) -> None:
    amap = _authority_map(repo_root)
    assert amap["schema"] == "shiroe.source-authority/v1"
    assert amap["archived"], "authority map must name at least one archived surface"
    assert amap["unscoped"], "authority map must name the unscoped (non-canon) globs"


def test_adr_0001_is_the_accepted_canonical_store_authority(repo_root: Path) -> None:
    amap = _authority_map(repo_root)
    rules = {r["question"]: r for r in amap["conflict_rules"]}
    assert "canonical-store" in rules, "no conflict rule for the canonical-store question"
    authority = repo_root / rules["canonical-store"]["authority"]
    assert authority.exists(), f"conflict authority {authority} does not exist"
    assert "**Status:** Accepted" in authority.read_text(encoding="utf-8"), (
        f"{authority} is cited as an authority but is not Accepted"
    )


def test_every_baseline_acknowledgement_is_attributable(repo_root: Path) -> None:
    baseline = json.loads((repo_root / BASELINE_REL).read_text(encoding="utf-8"))
    seen: set[str] = set()
    for finding in baseline["findings"]:
        fid = finding["id"]
        assert fid not in seen, f"duplicate baseline finding id: {fid}"
        seen.add(fid)
        assert finding["status"] in {"acknowledged", "wontfix", "resolved"}
        if finding["status"] in {"acknowledged", "wontfix"}:
            for field in ("owner", "resolving_pr", "why_open"):
                assert finding.get(field), (
                    f"baseline finding {fid} is anonymous: missing {field!r}"
                )
        assert finding["shr"].startswith("SHR-")
        assert isinstance(finding["count"], int) and finding["count"] >= 1


@pytest.mark.parametrize("surface,rule,probe", KNOWN_CONTRADICTIONS)
def test_known_contradiction_is_absent_or_acknowledged(
    repo_root: Path, surface: str, rule: str, probe: str
) -> None:
    """Detect-only PR: if the text is still there it must be on the books."""
    text = (repo_root / surface).read_text(encoding="utf-8")
    if not re.search(probe, text):
        return  # PR 02 removed it — nothing to acknowledge.
    baseline = json.loads((repo_root / BASELINE_REL).read_text(encoding="utf-8"))
    ids = {f["id"] for f in baseline["findings"] if f["status"] != "resolved"}
    assert f"{surface}::{rule}" in ids, (
        f"{surface} still contains the {rule} contradiction but the baseline "
        f"does not acknowledge it"
    )


def test_public_claim_ledger_entries_are_well_formed(repo_root: Path) -> None:
    ledger = json.loads((repo_root / LEDGER_REL).read_text(encoding="utf-8"))
    assert ledger["schema"] == "shiroe.public-claim-ledger/v1"
    assert ledger["claims"], "ledger must carry at least one claim"
    seen: set[str] = set()
    for claim in ledger["claims"]:
        cid = claim["id"]
        assert cid not in seen, f"duplicate claim id: {cid}"
        seen.add(cid)
        assert claim["claim_class"] in {"machine_verified", "command_attested", "manual"}
        assert claim["status"] in {"verified", "unverified", "contradicted", "removed"}
        assert (repo_root / claim["surface"]).exists(), (
            f"claim {cid} names a surface that does not exist: {claim['surface']}"
        )
        assert (
            "verify" in claim or "evidence_command" in claim or "evidence_path" in claim
        ), f"claim {cid} carries no evidence handle"
        if claim["status"] != "verified":
            for field in ("owner", "resolving_pr", "why_unverified"):
                assert claim.get(field), (
                    f"non-verified claim {cid} is anonymous: missing {field!r}"
                )


def test_status_enum_is_single_sourced_from_the_schema(repo_root: Path) -> None:
    """Phase 01 removes the contract registry; if it returns, labels stay schema-owned."""
    schema_path = repo_root / "registry" / "shiroe-registry.schema.json"
    registry_path = repo_root / "shiroe-registry.json"
    if not schema_path.exists() and not registry_path.exists():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    skills_enum = schema["properties"]["skills"]["items"]["properties"]["status"]["enum"]
    agents_enum = schema["properties"]["agents"]["items"]["properties"]["status"]["enum"]
    assert skills_enum == agents_enum, (
        f"status enum diverges between skills {skills_enum} and agents {agents_enum}"
    )
    script = (repo_root / SCRIPT_REL).read_text(encoding="utf-8")
    for label in skills_enum:
        assert f'"{label}"' not in script, (
            f"status label {label!r} is hardcoded in {SCRIPT_REL}; "
            f"read it from the schema instead"
        )


# --------------------------------------------------------------------------- #
# Synthetic trees — the anti-vacuity proof
# --------------------------------------------------------------------------- #

_SYNTH_AUTHORITY_MAP = {
    "schema": "shiroe.source-authority/v1",
    "tiers": [
        {"rank": 1, "id": "code-and-schemas", "paths": ["registry/*.schema.json"]},
        {"rank": 2, "id": "accepted-adrs", "paths": ["docs/adr/ADR-*.md"]},
        {"rank": 3, "id": "agents-spec", "paths": ["AGENTS.md"]},
        {"rank": 4, "id": "glossary", "paths": ["docs/GLOSSARY.md"]},
        {"rank": 5, "id": "generated-docs", "paths": ["shiroe-registry.json"]},
        {"rank": 6, "id": "narrative-docs", "paths": ["README.md", "docs/notes/*.md"]},
    ],
    "archived": [
        {"id": "old-canon", "paths": ["references/old/**"], "marker": "Superseded"},
    ],
    "unscoped": ["docs/canon/**"],
    "conflict_rules": [
        {
            "question": "canonical-store",
            "authority": "docs/adr/ADR-0001-canonical-store.md",
            "resolution": "sqlite=current-state, jsonl=history, markdown=generated-view",
        }
    ],
}

_SYNTH_SCHEMA = {
    "properties": {
        "skills": {
            "items": {
                "properties": {
                    "status": {"type": "string", "enum": ["runtime", "adapter", "contract", "experimental"]}
                }
            }
        },
        "agents": {
            "items": {
                "properties": {
                    "status": {"type": "string", "enum": ["runtime", "adapter", "contract", "experimental"]}
                }
            }
        },
    }
}

_SYNTH_REGISTRY = {
    "version": "0.0.0",
    "skills": [{"id": "s1", "status": "runtime"}],
    "agents": [{"id": "a1", "status": "contract"}],
    "commands": [{"id": "c1", "status": "runtime"}],
    "team_packs": [{"id": "t1", "status": "contract"}],
    "gates": [{"id": "g1", "status": "runtime"}],
}

_SYNTH_LEDGER = {
    "schema": "shiroe.public-claim-ledger/v1",
    "verified_at_commit": None,
    "claims": [
        {
            "id": "synth-notes-count",
            "surface": "README.md",
            "line": 3,
            "claim": "1 files of notes",
            "claim_class": "machine_verified",
            "status": "verified",
            "evidence_value": 1,
            "verify": {"kind": "count_glob", "glob": "docs/notes/*.md"},
        }
    ],
}

_SYNTH_BASELINE = {
    "schema": "shiroe.canon-baseline/v1",
    "generated": "2026-08-03",
    "recorded_at_commit": None,
    "findings": [],
}


def _synth(tmp_path: Path, **overrides: str | None) -> Path:
    """
    Minimum viable synthetic root: every file classified, zero findings.

    `overrides` maps a repo-relative path to file content; a value of None omits
    the file from an otherwise fresh tree (it deletes nothing — there is nothing
    there yet). JSON structures are injected by writing the path directly.
    """
    root = tmp_path / "synth"
    files: dict[str, str] = {
        "README.md": "# Synth\n\nSQLite is canonical for current state.\n1 files of notes.\n",
        "AGENTS.md": "# AGENTS\n\nSpec surface.\n",
        "docs/GLOSSARY.md": "# Glossary\n\nCanonical store invariant.\n",
        "docs/notes/note.md": "# Note\n\nNothing controversial here.\n",
        "docs/adr/ADR-0001-canonical-store.md": (
            "# ADR-0001\n\n**Status:** Accepted\n\nSQLite is the canonical current state.\n"
        ),
        "references/old/legacy.md": "# Legacy\n\nSuperseded by ADR-0001.\n",
        "registry/shiroe-registry.schema.json": json.dumps(_SYNTH_SCHEMA, indent=2),
        "shiroe-registry.json": json.dumps(_SYNTH_REGISTRY, indent=2),
        AUTHORITY_REL: (
            "# Source authority\n\nPrecedence, highest first.\n\n"
            "```json shiroe.source-authority/v1\n"
            + json.dumps(_SYNTH_AUTHORITY_MAP, indent=2)
            + "\n```\n"
        ),
        BASELINE_REL: json.dumps(_SYNTH_BASELINE, indent=2),
        LEDGER_REL: json.dumps(_SYNTH_LEDGER, indent=2),
    }
    files.update(overrides)  # type: ignore[arg-type]

    for rel, content in files.items():
        path = root / rel
        if content is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _baseline_with(*findings: dict) -> str:
    return json.dumps({**_SYNTH_BASELINE, "findings": list(findings)}, indent=2)


def _ledger_counting(n: int) -> dict:
    """The synth ledger, re-pinned to a tree holding `n` note files."""
    claim = {**_SYNTH_LEDGER["claims"][0], "claim": f"{n} files of notes", "evidence_value": n}
    return {**_SYNTH_LEDGER, "claims": [claim]}


def _authority_doc(amap: dict) -> str:
    """Render an authority map back into the prose+fenced-block file shape."""
    return (
        "# Source authority\n\nPrecedence, highest first.\n\n"
        "```json shiroe.source-authority/v1\n"
        + json.dumps(amap, indent=2)
        + "\n```\n"
    )


CONTRADICTION_LINE = "Canonical state is markdown on disk.\n"


def test_clean_synthetic_tree_passes(repo_root: Path, tmp_path: Path) -> None:
    result = _run(repo_root / SCRIPT_REL, _synth(tmp_path))
    assert result.returncode == 0, (
        f"clean synthetic tree should pass:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_injected_contradiction_fails(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(
        tmp_path,
        **{"docs/notes/bad.md": "# Bad\n\n" + CONTRADICTION_LINE},
    )
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "NEW:" in result.stderr, result.stderr
    assert "bad.md" in result.stderr, result.stderr


def test_archived_path_is_not_scanned(repo_root: Path, tmp_path: Path) -> None:
    """Same contradicting sentence, but under an archived glob — must stay silent."""
    root = _synth(
        tmp_path,
        **{"references/old/legacy.md": "# Legacy\n\nSuperseded by ADR-0001.\n" + CONTRADICTION_LINE},
    )
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 0, (
        f"archived surfaces must not be scanned:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_dropped_acknowledgement_fails(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(
        tmp_path,
        **{
            BASELINE_REL: _baseline_with(
                {
                    "id": "docs/notes/ghost.md::markdown-canonical",
                    "shr": "SHR-004",
                    "count": 1,
                    "excerpt": "Canonical state is markdown on disk.",
                    "why_open": "placeholder",
                    "owner": "kanadhiayash",
                    "resolving_pr": "fix/shr-canonical-state",
                    "status": "acknowledged",
                }
            )
        },
    )
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "DROPPED" in result.stderr, result.stderr


def test_count_drift_fails(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(
        tmp_path,
        **{
            "docs/notes/bad.md": "# Bad\n\n" + CONTRADICTION_LINE + "\n" + CONTRADICTION_LINE,
            BASELINE_REL: _baseline_with(
                {
                    "id": "docs/notes/bad.md::markdown-canonical",
                    "shr": "SHR-004",
                    "count": 1,  # observed will be 2
                    "excerpt": "Canonical state is markdown on disk.",
                    "why_open": "placeholder",
                    "owner": "kanadhiayash",
                    "resolving_pr": "fix/shr-canonical-state",
                    "status": "acknowledged",
                }
            ),
        },
    )
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "COUNT DRIFT" in result.stderr, result.stderr


def test_unclassified_surface_fails(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(tmp_path, **{"stray/unknown.txt": "not claimed by any glob\n"})
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "unclassified" in result.stderr.lower(), result.stderr


def test_missing_authority_map_exits_2(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(tmp_path)
    (root / AUTHORITY_REL).unlink()
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 2, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_acknowledgement_without_owner_exits_2(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(
        tmp_path,
        **{
            "docs/notes/bad.md": "# Bad\n\n" + CONTRADICTION_LINE,
            BASELINE_REL: _baseline_with(
                {
                    "id": "docs/notes/bad.md::markdown-canonical",
                    "shr": "SHR-004",
                    "count": 1,
                    "excerpt": "Canonical state is markdown on disk.",
                    "why_open": "placeholder",
                    # owner + resolving_pr deliberately absent
                    "status": "acknowledged",
                }
            ),
        },
    )
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 2, (
        f"anonymous acknowledgement must exit 2:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_unledgered_numeric_claim_fails(repo_root: Path, tmp_path: Path) -> None:
    root = _synth(
        tmp_path,
        **{"README.md": "# Synth\n\n1 files of notes.\n\nWe run 500 tests on every push.\n"},
    )
    result = _run(repo_root / SCRIPT_REL, root)
    assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "unledgered-claim" in result.stderr, result.stderr


@pytest.fixture(scope="module")
def canon_module(repo_root: Path):
    """The canon checker loaded as a module, for unit-level detector tests."""
    import importlib.util

    path = repo_root / SCRIPT_REL
    spec = importlib.util.spec_from_file_location("_canon_checker_unit", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- Exculpation scope (security audit finding: one-word bypass of SHR-004) ---
#
# EXCULPATING_RE used to be tested against the whole line, so appending any
# qualifying word anywhere on it silenced a real contradiction. It is now scoped
# to the clause containing the hit. These cases are the audit's proof-of-concept.

_BYPASS_MUST_FIRE = [
    "Canonical state is markdown on disk.",
    "Canonical state is markdown on disk. Views are generated.",
    "Canonical state is markdown on disk. [docs](https://example.invalid/views/y)",
    "| store | Canonical state is markdown on disk | generated |",
]

_MUST_STAY_SILENT = [
    "Markdown views are generated (never canonical)",
    "JSONL holds canonical append-only history; Markdown is a generated view",
    "| Markdown | a generated view, never canonical |",
]


def _hits(canon, text: str) -> list[str]:
    return [h for _rule, pat in canon.CONFLICT_RULES for h in canon._contradiction_hits(text, pat)]


@pytest.mark.parametrize("line", _BYPASS_MUST_FIRE)
def test_exculpation_cannot_be_bypassed_by_an_unrelated_clause(canon_module, line: str) -> None:
    assert _hits(canon_module, line), (
        f"contradiction silenced by an unrelated qualifier on the same line: {line!r}. "
        "EXCULPATING_RE must be scoped to the clause containing the hit."
    )


@pytest.mark.parametrize("line", _MUST_STAY_SILENT)
def test_correct_invariant_statements_do_not_fire(canon_module, line: str) -> None:
    assert not _hits(canon_module, line), (
        f"line restates ADR-0001 correctly but was flagged: {line!r}"
    )


# --- Content drift (audit: acknowledgements were laundering slots) ---


def test_acknowledged_finding_is_bound_to_its_matched_text(canon_module) -> None:
    """Same rule, same surface, same count, different text must not stay [KNOWN]."""
    a = canon_module.Finding("x.md", "r", "SHR-004", count=1, hits=("canonical state is markdown",))
    b = canon_module.Finding("x.md", "r", "SHR-004", count=1, hits=("the markdown wiki is canonical",))
    assert a.id == b.id and a.count == b.count
    assert a.digest and b.digest and a.digest != b.digest


def test_baseline_digests_cover_every_finding_that_can_supply_one(repo_root: Path, canon_module) -> None:
    amap = canon_module.load_authority_map(repo_root)
    cls, _ = canon_module.classify(amap, canon_module.walk_files(repo_root))
    observed = (
        canon_module.check_canon_conflicts(repo_root, cls, amap)
        + canon_module.check_live_citations_of_archived(repo_root, amap, cls)
    )
    baseline = json.loads((repo_root / "docs/canon/canon-baseline.json").read_text())
    entries = {f["id"]: f for f in baseline["findings"]}
    missing = [
        f.id for f in observed
        if f.digest and f.id in entries and not entries[f.id].get("digest")
    ]
    assert not missing, f"acknowledged finding(s) with no content digest: {missing}"


# --- Claim shapes must see marked-up and capitalised numbers (audit CRITICAL 3) ---


@pytest.mark.parametrize(
    "phrase",
    ["500 tests", "**500** tests", "`500` tests", "500 Tests", "500 tests",
     "capped at **4** agents", "Max **4** agents per pack"],
)
def test_claim_shapes_see_marked_up_numbers(canon_module, phrase: str) -> None:
    assert any(s.search(phrase) for s in canon_module.CLAIM_SHAPES), (
        f"public surfaces bold their numbers; claim shape is blind to {phrase!r}"
    )


# --- Availability: a surface the checker cannot safely read (audit HIGH 1) ---


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs only")
def test_non_regular_active_surface_is_reported_not_read(repo_root: Path, tmp_path: Path) -> None:
    """A non-regular file on an active surface must fail the audit, not hang it.

    `read_text` sized files with `stat()`, which follows symlinks and reports 0
    for character devices, so a committed `x.md -> /dev/zero` passed the
    MAX_SCAN_BYTES guard and was then read unbounded. A FIFO is the same defect
    without the memory blow-up: `open()` simply never returns.

    Silence is not a safe answer either. `read_text` returning None is the *skip*
    path, so a symlinked surface would classify active, be skipped by the
    conflict scan, and ship an unscanned contradiction -- exactly the evasion
    SHR-004 exists to stop. Hence a finding, not a quiet pass.
    """
    root = _synth(tmp_path)
    os.mkfifo(root / "docs" / "notes" / "evil.md")

    result = _run(repo_root / SCRIPT_REL, root)

    assert result.returncode == 1, (
        f"non-regular active surface should fail the audit (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "unreadable-surface" in result.stdout + result.stderr


# --- Availability: a ledger-supplied regex must not run forever (audit HIGH 2) ---


_REDOS_LEDGER = {
    **_SYNTH_LEDGER,
    "claims": [
        {
            "id": "synth-redos",
            "surface": "README.md",
            "line": 3,
            "claim": "1 files of notes",
            "claim_class": "machine_verified",
            "status": "verified",
            "evidence_value": 1,
            # No 'x' anywhere in the input, so the match must FAIL -- and it is
            # the failing case that backtracks. A pattern that succeeds returns
            # immediately and proves nothing.
            "verify": {"kind": "count_regex", "file": "docs/notes/*.md", "pattern": "(a+)+x"},
        }
    ],
}


def test_ledger_supplied_regex_cannot_hang_the_audit(repo_root: Path, tmp_path: Path) -> None:
    """`verify.pattern` is data, and data must not be able to stop the gate.

    A nested quantifier backtracks exponentially: this pattern needs about 2**n
    steps on n leading 'a's, so 40 bytes of input outlasts any CI job. Pattern
    length caps and `(?m)^` anchoring were both measured and both fail -- an
    11-character anchored pattern hangs just as hard -- so the guard is a wall
    clock budget on the whole audit rather than a filter on the pattern.
    """
    root = _synth(
        tmp_path,
        **{
            "docs/notes/note.md": "a" * 40 + "\n",
            LEDGER_REL: json.dumps(_REDOS_LEDGER, indent=2),
        },
    )

    # A short budget only shortens the test; the pattern outruns any ceiling.
    result = _run(repo_root / SCRIPT_REL, root, budget_s=5)

    assert result.returncode == 2, (
        f"a runaway ledger regex is malformed input, so exit 2 (got {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "budget" in result.stderr


def test_ledger_path_cannot_escape_the_root(repo_root: Path, tmp_path: Path) -> None:
    """`verify.file` is data; `root / "/abs"` silently yields "/abs".

    Left unconfined this reads arbitrary host files -- an existence oracle, and
    pointed at a device or FIFO the same unbounded read the surface reader was
    hardened against. A FIFO outside the root proves both halves at once.
    """
    outside = tmp_path / "outside.json"
    if hasattr(os, "mkfifo"):
        os.mkfifo(outside)
    else:  # pragma: no cover - POSIX-only CI
        outside.write_text("[]", encoding="utf-8")

    escaping = {
        **_SYNTH_LEDGER,
        "claims": [{**_SYNTH_LEDGER["claims"][0],
                    "verify": {"kind": "count_json_array", "file": str(outside), "path": "x"}}],
    }
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{LEDGER_REL: json.dumps(escaping, indent=2)}),
        budget_s=5,
    )

    assert result.returncode == 2, (
        f"a ledger path outside --root is malformed input (got {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "escapes --root" in result.stderr


def test_malformed_ledger_verify_exits_two_not_one(repo_root: Path, tmp_path: Path) -> None:
    """Bad input is exit 2. A traceback with exit 1 reads as 'drift found'."""
    broken = {
        **_SYNTH_LEDGER,
        "claims": [{**_SYNTH_LEDGER["claims"][0],
                    "verify": {"kind": "count_json_array",
                               "file": "shiroe-registry.json", "path": "nope"}}],
    }
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{LEDGER_REL: json.dumps(broken, indent=2)}),
    )
    assert result.returncode == 2, (
        f"malformed verify block should exit 2, got {result.returncode}:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_ledger_claim_without_evidence_handle_exits_two(repo_root: Path, tmp_path: Path) -> None:
    """A verified claim with no handle silences every numeric phrase it contains."""
    naked = {**_SYNTH_LEDGER["claims"][0]}
    naked.pop("verify")
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{LEDGER_REL: json.dumps({**_SYNTH_LEDGER, "claims": [naked]}, indent=2)}),
    )
    assert result.returncode == 2
    assert "evidence handle" in result.stderr


# --- Scope holes in the authority map (audit HIGH 3) ---


def test_excluding_a_surface_into_unscoped_is_reported(repo_root: Path, tmp_path: Path) -> None:
    """`exclude` + a covering `unscoped` glob drops a live surface silently.

    `unscoped` is deliberately exempt from the dead-glob check, so this pairing
    leaves no unused glob behind for the audit to notice.
    """
    amap = json.loads(json.dumps(_SYNTH_AUTHORITY_MAP))  # deep copy
    amap["tiers"][-1]["exclude"] = ["docs/notes/hidden.md"]
    amap["unscoped"] = [*amap["unscoped"], "docs/notes/hidden.md"]

    # A second note keeps `docs/notes/*.md` matching, so no dead-glob fires and
    # `excluded-into-unscoped` is the only thing standing between this map and a
    # silently unscanned surface. Without the sibling the test would pass on the
    # dead glob alone and prove nothing.
    root = _synth(
        tmp_path,
        **{
            AUTHORITY_REL: _authority_doc(amap),
            "docs/notes/hidden.md": "# Hidden\n\n" + CONTRADICTION_LINE,
            # The sibling note moves the counted total to 2; record that so the
            # tree's only finding is the scope hole under test.
            LEDGER_REL: json.dumps(_ledger_counting(2), indent=2),
            "README.md": "# Synth\n\nSQLite is canonical for current state.\n2 files of notes.\n",
        },
    )
    result = _run(repo_root / SCRIPT_REL, root)

    assert result.returncode == 1, (
        f"excluded-then-unscoped surface should fail the audit:\n{result.stdout}"
    )
    assert "excluded-into-unscoped" in result.stdout
    assert "dead-glob" not in result.stdout, (
        "this tree must fail on the exclusion itself, not on an incidental dead glob"
    )


def test_markerless_archived_entry_exits_two(repo_root: Path, tmp_path: Path) -> None:
    """An archived entry with no marker silences its files and looks ordinary.

    The shipped map legitimately carries two markerless entries (CHANGELOG.md,
    MIGRATION.md), so a third would pass review unremarked. Demanding a marker
    or a written reason makes the exemption reviewable.
    """
    amap = json.loads(json.dumps(_SYNTH_AUTHORITY_MAP))
    # Tiers are matched before archived, so the entry only captures anything if
    # the tier lets go first. exclude + markerless archived is the actual hole:
    # the file leaves the conflict scan and check_archived_files_marked skips it
    # for want of a marker, so nothing anywhere reports it.
    amap["tiers"][-1]["exclude"] = ["docs/notes/hidden.md"]
    amap["archived"].append({"id": "sneaky", "paths": ["docs/notes/hidden.md"]})

    root = _synth(
        tmp_path,
        **{
            AUTHORITY_REL: _authority_doc(amap),
            "docs/notes/hidden.md": "# Hidden\n\n" + CONTRADICTION_LINE,
            # The sibling note moves the counted total to 2; record that so the
            # tree's only finding is the scope hole under test.
            LEDGER_REL: json.dumps(_ledger_counting(2), indent=2),
            "README.md": "# Synth\n\nSQLite is canonical for current state.\n2 files of notes.\n",
        },
    )
    result = _run(repo_root / SCRIPT_REL, root)

    assert result.returncode == 2, (
        f"markerless archived entry should be rejected outright:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "why_no_marker" in result.stderr


# --- Reconcile verdicts that had no synthetic proof ---


_BAD_NOTE = {"docs/notes/bad.md": "# Bad\n\n" + CONTRADICTION_LINE}
_BAD_ID = "docs/notes/bad.md::markdown-canonical"


def test_resolved_finding_that_reappears_is_regressed(repo_root: Path, tmp_path: Path) -> None:
    """The whole `status: "resolved"` lifecycle rests on this verdict.

    Marking a finding resolved is the only way to retire it from the baseline
    without DROPPED failing the build. If a resolved finding can come back
    unnoticed, every closed finding is reopenable in silence -- and this was the
    one reconcile verdict with no test at all.
    """
    root = _synth(
        tmp_path,
        **{
            **_BAD_NOTE,
            BASELINE_REL: _baseline_with(
                {"id": _BAD_ID, "shr": "SHR-004", "count": 1, "status": "resolved",
                 "excerpt": "canonical state is markdown"}
            ),
        },
    )

    result = _run(repo_root / SCRIPT_REL, root)

    assert result.returncode == 1, (
        f"a resolved finding present again must fail the audit:\n{result.stdout}"
    )
    assert "REGRESSED" in result.stderr


def test_acknowledged_finding_with_changed_text_is_content_drift(
    repo_root: Path, tmp_path: Path
) -> None:
    """Same surface, same rule, same count, different text: the laundering slot."""
    root = _synth(
        tmp_path,
        **{
            **_BAD_NOTE,
            BASELINE_REL: _baseline_with(
                {"id": _BAD_ID, "shr": "SHR-004", "count": 1, "status": "acknowledged",
                 "excerpt": "something else", "digest": "0" * 12,
                 "owner": "tests", "resolving_pr": "none", "why_open": "fixture"}
            ),
        },
    )

    result = _run(repo_root / SCRIPT_REL, root)

    assert result.returncode == 1
    assert "CONTENT DRIFT" in result.stderr


def test_active_surface_citing_an_archived_directory_fails(
    repo_root: Path, tmp_path: Path
) -> None:
    """Pointing a reader at superseded material reads as pointing them at canon."""
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{"docs/notes/note.md": "# Note\n\nSee references/old/ for detail.\n"}),
    )
    assert result.returncode == 1
    assert "cites-archived" in result.stdout


def test_archived_surface_without_its_marker_fails(repo_root: Path, tmp_path: Path) -> None:
    """An archived file that does not say so reads as live to every reader."""
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{"references/old/legacy.md": "# Legacy\n\nStill current, honest.\n"}),
    )
    assert result.returncode == 1
    assert "archived-unmarked" in result.stdout


def test_a_removed_claim_is_not_drift_checked(repo_root: Path, tmp_path: Path) -> None:
    """A claim withdrawn from its surface asserts nothing to drift against.

    The ledger's status enum carries "removed" for exactly this. Drift-checking
    it reports the tree disagreeing with a number nobody publishes any more, so
    withdrawing a stale claim would be impossible without also deleting the
    record of why it was withdrawn.
    """
    withdrawn = {
        **_SYNTH_LEDGER,
        "claims": [{
            **_SYNTH_LEDGER["claims"][0],
            "status": "removed",
            "evidence_value": None,
            "owner": "tests",
            "resolving_pr": "none",
            "why_unverified": "withdrawn from the surface",
        }],
    }
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{
            LEDGER_REL: json.dumps(withdrawn, indent=2),
            # No numeric claim left on the surface either, matching a real
            # withdrawal -- otherwise unledgered-claim fires instead.
            "README.md": "# Synth\n\nSQLite is canonical for current state.\n",
        }),
    )
    assert result.returncode == 0, (
        f"a removed claim should not be drift-checked:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_claim_drift_between_ledger_and_tree_fails(repo_root: Path, tmp_path: Path) -> None:
    """The recorded evidence value must still match what the tree computes."""
    drifted = {
        **_SYNTH_LEDGER,
        "claims": [{**_SYNTH_LEDGER["claims"][0], "evidence_value": 5}],
    }
    result = _run(
        repo_root / SCRIPT_REL,
        _synth(tmp_path, **{LEDGER_REL: json.dumps(drifted, indent=2)}),
    )
    assert result.returncode == 1
    assert "claim-drift" in result.stdout
