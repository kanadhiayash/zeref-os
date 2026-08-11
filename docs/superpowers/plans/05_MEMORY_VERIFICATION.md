# Phase 05: Memory and Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge memory and verification onto one canonical SQLite write/read path with one simple deterministic search implementation and one verification report.

**Architecture:** Memory records, sources and relations are canonical SQLite state. Events are replay history. Markdown is generated. Verification composes current privacy/evidence/fact/contradiction/write checks under one engine.

**Tech Stack:** SQLite, Unicode normalization, deterministic token overlap, JSONL events, pytest.

## Global Constraints

- No BM25, FTS rank, JSONL ranking fallback, query expansion or dual backend.
- Every accepted memory write must be immediately recallable.
- Every rejected memory write leaves canonical memory unchanged and records a rejection event.
- Generated Markdown is never source of truth.

---

### Task 1: Create one MemoryService over canonical SQLite

**Files:**
- Create: `shiroe/memory/service.py`
- Create: `shiroe/memory/models.py`
- Test: `tests/unit/memory/test_service.py`
- Test: `tests/integration/memory/test_write_recall_coherence.py`

**Interfaces:**
- Produces: `MemoryService.write()`, `get()`, `list()`, `supersede()`, `archive()`, `relations()`, `history()`.

- [ ] **Step 1: Write failing immediate-coherence test**

```python

def test_accepted_write_is_immediately_readable(tmp_path):
    svc = MemoryService(tmp_path)
    record = svc.write(MemoryWrite(kind="decision", title="Limiter", claim="Use in-process limiter", source_refs=("user-input",)))
    assert svc.get(record.id).claim == "Use in-process limiter"
```

- [ ] **Step 2: Implement service on `memory_records`, `memory_sources`, `memory_relations`**

All writes use one SQLite transaction and append a canonical event only after validation. Do not write `memory/l1_atoms/*.jsonl`.

- [ ] **Step 3: Run tests**

```bash
pytest tests/unit/memory/test_service.py tests/integration/memory/test_write_recall_coherence.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/memory/service.py shiroe/memory/models.py tests/unit/memory tests/integration/memory
git commit -m "feat(memory): converge writes on canonical sqlite"
```

### Task 2: Replace BM25/FTS/query expansion with one deterministic search path

**Files:**
- Rewrite: `shiroe/memory/search.py`
- Delete: `shiroe/memory/indexer.py`
- Delete: `shiroe/memory/expand.py`
- Delete: `shiroe/memory/agent_retrieval.py`
- Delete: `shiroe/memory/atom_store.py` after migration reader no longer imports it
- Test: `tests/unit/memory/test_search.py`
- Test: `tests/invariant/test_memory_search_unicode.py`

**Interfaces:**
- Produces: `search_memory(root, query, *, limit=10, kinds=None, statuses=("active",), as_of=None) -> SearchResult`.

- [ ] **Step 1: Write exact ranking tests with a local seed helper**

```python
from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService


def _seed_memory(root, claim):
    return MemoryService(root).write(MemoryWrite(
        kind="decision",
        title=claim.split()[0],
        claim=claim,
        source_refs=("user-input",),
        privacy_class="internal",
        evidence_grade="C",
    ))


def test_zero_overlap_abstains(tmp_path):
    _seed_memory(tmp_path, claim="Use SQLite for state")
    result = search_memory(tmp_path, "banana telescope")
    assert result.abstained is True
    assert result.hits == ()


def test_more_unique_token_overlap_ranks_first(tmp_path):
    _seed_memory(tmp_path, claim="Use local rate limiter")
    b = _seed_memory(tmp_path, claim="Use local in-process rate limiter")
    hits = search_memory(tmp_path, "local in-process rate limiter").hits
    assert hits[0].record.id == b.id


def test_nfkc_case_normalization(tmp_path):
    _seed_memory(tmp_path, claim="Ｃａｎｏｎｉｃ State")
    assert search_memory(tmp_path, "canonical state").hits
```

- [ ] **Step 2: Implement simple tokenizer and score**

```python
def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return tuple(dict.fromkeys(re.findall(r"\w+", normalized, flags=re.UNICODE)))


def _overlap_score(query_tokens: set[str], candidate: str) -> int:
    return len(query_tokens & set(_tokens(candidate)))
```

Candidate text is `title + claim + summary + tags`. Sort by temporal/currentness rank, negative overlap, negative updated timestamp, id. No alternate backend.

- [ ] **Step 3: Delete old search/index tests tied to BM25/FTS and port only semantic invariants**

Old backend-parity tests are deleted, not rewritten. Unicode normalization and abstention survive in new tests.

- [ ] **Step 4: Run tests and prove no BM25 remains in runtime/tests**

```bash
pytest tests/unit/memory/test_search.py tests/invariant/test_memory_search_unicode.py -q
! grep -R "bm25\|BM25" -n shiroe tests
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(memory): replace bm25 with one deterministic search path"
```

### Task 3: Route recall through MemoryService search

**Files:**
- Rewrite: `shiroe/memory/recall.py`
- Test: `tests/integration/memory/test_recall.py`

**Interfaces:**
- Produces: `recall(root, query, ...) -> RecallResult` with hits, evidence refs, abstention and open contradictions.

- [ ] **Step 1: Write regression for the previously broken write-decision split**

```python

def test_write_then_recall_same_process(tmp_path):
    svc = MemoryService(tmp_path)
    svc.write(MemoryWrite(kind="decision", title="Limiter", claim="Use in-process limiter", source_refs=("user-input",)))
    result = recall(tmp_path, "in-process limiter")
    assert result.abstained is False
    assert result.hits[0].record.claim == "Use in-process limiter"
```

- [ ] **Step 2: Implement recall using only `MemoryService.search`**

No direct atom store, SQLite FTS, JSONL scan or generated Markdown read is permitted.

- [ ] **Step 3: Run tests**

```bash
pytest tests/integration/memory/test_recall.py tests/integration/memory/test_write_recall_coherence.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/memory/recall.py tests/integration/memory/test_recall.py
git commit -m "fix(memory): make recall read canonical writes"
```

### Task 4: Consolidate guards into Verification Engine

**Files:**
- Create: `shiroe/verification/__init__.py`
- Create: `shiroe/verification/schema.py`
- Create: `shiroe/verification/engine.py`
- Move/refactor: privacy/evidence/fact/contradiction/write checks from `shiroe/guards/`
- Test: `tests/unit/verification/test_engine.py`
- Preserve/rehome current privacy/policy/evidence adversarial tests.

**Interfaces:**
- Produces: `CheckStatus`, `VerificationFinding`, `VerificationCheck`, `VerificationReport`, `VerificationEngine.verify(...)`.

- [ ] **Step 1: Write composition test with explicit secret-shaped input**

```python
from shiroe.memory.models import MemoryWrite


def test_verification_report_blocks_when_any_required_check_blocks(tmp_path):
    proposal = MemoryWrite(
        kind="decision",
        title="Credential",
        claim="Use token sk-proj-THIS_IS_SYNTHETIC_NOT_REAL_1234567890",
        source_refs=("user-input",),
        privacy_class="internal",
        evidence_grade="C",
    )
    report = VerificationEngine(tmp_path).verify_memory_write(proposal)
    assert report.status.value == "block"
    assert any(c.name == "privacy" and c.status.value == "block" for c in report.checks)
```

- [ ] **Step 2: Implement common schema**

```python
class CheckStatus(str, Enum):
    passed = "pass"
    warn = "warn"
    block = "block"
```

`VerificationReport.status` is the maximum severity over required checks: block > warn > pass.

- [ ] **Step 3: Wrap existing deterministic logic, do not duplicate it**

Move code into `shiroe/verification/privacy.py`, `evidence.py`, `claims.py`, `contradictions.py`, `writes.py` or call existing functions temporarily. End-state must have no separate public Guard command families.

- [ ] **Step 4: Run hardening tests**

```bash
pytest tests/unit/verification tests/test_privacy_adversarial.py tests/test_privacy_pr17_bypass.py tests/test_evidence_guard.py tests/test_fact_guard.py tests/test_contradiction_guard.py tests/test_memory_write_gate.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/verification tests/unit/verification
git commit -m "refactor(verify): unify runtime verification checks"
```

### Task 5: Make generated views depend only on canonical state

**Files:**
- Move/refactor: `shiroe/storage/views.py` -> `shiroe/memory/views.py`
- Test: `tests/invariant/test_generated_views_rebuild.py`

**Interfaces:**
- Produces: `render_views(root) -> list[Path]`.

- [ ] **Step 1: Write destructive-view rebuild test**

```python

def test_generated_views_can_be_deleted_and_rebuilt(tmp_path):
    MemoryService(tmp_path).write(MemoryWrite(kind="decision", title="Canonical state", claim="Use canonical state", source_refs=("user-input",), privacy_class="internal", evidence_grade="C"))
    paths = render_views(tmp_path)
    for path in paths:
        path.unlink()
    rebuilt = render_views(tmp_path)
    assert rebuilt
    assert "Use canonical state" in (tmp_path / "memory/views/decisions.md").read_text()
```

- [ ] **Step 2: Implement views from SQL queries only**

Do not read previous Markdown to generate new Markdown.

- [ ] **Step 3: Remove duplicate flat-wiki writer paths**

Delete or rewrite `MemoryWriter.write_decision`, `_write_memory_files`, and any direct runtime append to `memory/DECISIONS.md`, `CONFLICTS.md`, `RISKS.md` as canonical writes. Human-readable conflict views must be generated from SQLite contradiction state.

- [ ] **Step 4: Run tests**

```bash
pytest tests/invariant/test_generated_views_rebuild.py tests/integration/memory -q
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(memory): make markdown views fully derived"
```

### Task 6: Remove obsolete memory/guard architecture

**Files:**
- Delete after migrated callers: `shiroe/guards/`
- Delete: `shiroe/memory/triples.py`
- Delete: `shiroe/memory/graph.py`
- Delete: `shiroe/memory/cost_router.py`
- Delete old atom/refinement modules no longer imported
- Delete old BM25/index/ranking tests already replaced
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_single_memory_path.py`

- [ ] **Step 1: Write import/absence test**

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_single_memory_architecture():
    assert not (ROOT / "shiroe/guards").exists()
    assert not (ROOT / "shiroe/memory/indexer.py").exists()
    assert not (ROOT / "shiroe/memory/expand.py").exists()
    assert not (ROOT / "shiroe/memory/atom_store.py").exists()
```

- [ ] **Step 2: Delete only after no import remains**

```bash
grep -R "memory.atom_store\|memory.indexer\|memory.expand\|shiroe.guards" -n shiroe tests
```

Expected before deletion: zero active callers outside files scheduled for deletion.

- [ ] **Step 3: Run memory/verification gate**

```bash
pytest tests/unit/memory tests/integration/memory tests/unit/verification tests/invariant/test_single_memory_path.py tests/invariant/test_generated_views_rebuild.py -q
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(memory): retire split memory and guard layers"
```

## Phase gate

```bash
pytest tests/unit/memory tests/integration/memory tests/unit/verification tests/invariant/test_memory_search_unicode.py tests/invariant/test_generated_views_rebuild.py -q
! grep -R "bm25\|BM25" -n shiroe tests
```
