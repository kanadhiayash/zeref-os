<!-- privacy-audit: allow-file "Public hero doc. Documents install commands with example env-var names. No user memory." -->

<p align="center">
  <img src="./assets/shiroe-banner-motion.svg" alt="Shiroe — Strategy over noise. One governed project state across humans, agents, models, and harnesses." width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license"></a>
  <a href="AGENTS.md"><img src="https://img.shields.io/badge/AGENTS.md-canonical-blue" alt="AGENTS.md canonical spec"></a>
  <a href="SECURITY.md"><img src="https://img.shields.io/badge/security-private%20reporting-critical" alt="private vulnerability reporting"></a>
  <a href="https://github.com/kanadhiayash/shiroe/actions/workflows/shr-verify.yml"><img src="https://github.com/kanadhiayash/shiroe/actions/workflows/shr-verify.yml/badge.svg" alt="verify"></a>
</p>

<p align="center">
  <a href="#the-problem">Problem</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#what-is-actually-verified">Verified</a> ·
  <a href="#install">Install</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#limitations">Limitations</a>
</p>

---

## The problem

Tuesday morning. You open **Claude Code**:

> **You:** Add rate limiting to the upload endpoint.
>
> **Claude:** I'll add a Redis-backed limiter —
>
> **You:** No. We ruled out Redis in March. Single-node.

Afternoon, you switch to **Codex** for a refactor:

> **Codex:** For rate limiting here, I'd suggest Redis —

Thursday, **Cursor**, different file, same endpoint:

> **Cursor:** Consider adding a Redis-backed rate limiter.

None of them is stupid. None of them has memory, and none of them can see what you told the other two. You are the only shared state in the system, and you are re-typing the same decision until you stop trusting the tools with anything that took real thought.

The usual fixes do not hold. A long `CLAUDE.md` grows until it eats your context budget and gets skimmed — and Codex and Cursor never read it anyway. A vector database puts your project's decisions in a vendor's account and returns fuzzy matches with no provenance. Neither survives the switch between tools, which is exactly where the memory is lost.

Shiroe puts that memory in your repo, as files you can read, diff, and review in a pull request. Every tool reads the same ones.

Current release **v3.0.0-alpha.1**. Alpha software — interfaces may change. See [Limitations](#limitations).

## Before / after

Without a memory layer, a decision lives in a chat log no future session reads:

```
$ git log --oneline -1
a3f21c9 feat(upload): add rate limiting

# Why not Redis? Ask whoever was in that meeting.
```

With Shiroe, it is a reviewable file with its evidence grade attached:

```markdown
<!-- memory/DECISIONS.md -->
## D-014 — In-process token bucket for rate limiting

**Decided:** 2026-03-11 · **Grade:** A (benchmarked) · **Supersedes:** —

Redis rejected: single-node deployment, operational cost not justified
below ~2k req/s. Re-open if we go multi-node.

**Source:** benchmarks/rate-limit-2026-03-11.md
```

The next session, in any harness, reads that before it writes a line.

<p align="center">
  <img src="./assets/shiroe-character-snapshot-motion.svg" alt="Shiroe — the tactician: a coordinating intelligence over one governed project state" width="72%">
</p>

---

## How it works

**Reads are bounded.** A session does not load your memory. It walks inward until it has enough, then stops:

```
1. memory/hot.md      ≤500 words — last 3 sessions
2. memory/index.md    domain index, only if hot is insufficient
3. one page section   only if the index points at one
```

That ceiling holds whether the project is two weeks or two years old. Context cost does not grow with your history.

**Writes are gated.** A proposed write clears four checks before it lands:

```
fact_guard         → superlatives, benchmark claims, readiness assertions
evidence_guard     → claim graded A-F; ungraded claims do not pass
privacy_guard      → NFKC + homoglyph fold + base64 decode, then match
contradiction      → conflicts with stored state? halt, queue both sides
```

**Contradictions stop.** When a new claim contradicts a stored one, the write **halts**. Both sides go to `memory/CONFLICTS.md` with provenance, and you arbitrate. Nothing auto-resolves, nothing is silently overwritten, and the newer claim does not win by being newer.

**Routing names classes, never models.** Core code says `fast`, `balanced`, `deep`, `frontier`. Vendor model IDs live only in `shiroe/adapters/providers/*.json`. Swapping providers does not touch core.

---

## What is actually verified

Most projects put benchmark numbers here. Shiroe has none to put — no scored external run has ever executed, and the release gate mechanically blocks this README from implying otherwise.

So this is the honest version: what a machine checks on every commit, and what nobody has checked at all.

### Enforced on every push

| Check | What it proves |
|---|---|
| `pytest` — Python 3.11/3.12/3.13 | Behaviour under test |
| `shiroe release check` — SHA-bound evidence gate | Every check re-runs live per current HEAD; writes evidence to `docs/audits/release-evidence/<sha>_<ts>.json`; a stale SHA cannot substitute |
| `audit-privacy --strict` | Zero credential-class hits, repo-wide — unicode-invisible strip, base32/base64/hex probes, nested-archive scan up to depth 3, and allowlist-change detection all defeat the common bypass paths |
| `check-version-consistency` | 13 version and identity surfaces cannot drift |
| `shiroe-validate` | Registry matches disk; every `runtime`/`adapter` entry resolves to a real artifact; non-runtime entries carry an honest status |
| `check-trust-registry` | Every public visual under `assets/` and every URL cited from README + root spec files has an approved source + rights status in `docs/canon/TRUST_REGISTRY.json` |
| Clean-clone install + `init` + `doctor` | It installs and runs from a fresh venv |

### Enforced against this README

`shiroe/release/claim_gate.py` and `shiroe/guards/fact_guard.py` scan every public surface — including this file — and **fail the release** on:

- a superiority claim with no public benchmark behind it,
- a Shiroe benchmark number published without a full-context and a lexical baseline beside it,
- a comparative ranking resting on contested vendor figures,
- a readiness or perfect-score assertion, or a routing-accuracy claim off a fixture corpus.

That gate is why the next section exists and is not marketing.

### Not verified by anything

- **No external benchmark score exists.** The harness has run in proxy mode only: ingest and retrieve, zero network calls.
- **Retrieval trails a lexical baseline** on that proxy signal — plain BM25 finds the answer more often on LoCoMo and LongMemEval at equal `k`. The root cause (a substring-count ranker on the JSONL path) was found and fixed, but **has not been re-measured**. Tracked in [#196](https://github.com/kanadhiayash/shiroe/issues/196).
- **Live provider and judge paths are untested** against a mocked transport ([#207](https://github.com/kanadhiayash/shiroe/issues/207)).
- **Three dataset loaders carry no checksum pin**, so `--check` cannot detect a corrupt download ([#206](https://github.com/kanadhiayash/shiroe/issues/206)).

The coverage floor is 15%, and the CI comment says so plainly: that is the measured figure, not an aspiration. Most CLI paths run through subprocesses, which in-process coverage does not see.

---

## Install

Core is stdlib-only. Zero mandatory dependencies. Python 3.11+.

```bash
git clone https://github.com/kanadhiayash/shiroe.git .shiroe
python3 -m shiroe init
```

Then point your harness at `.shiroe/AGENTS.md`. That file is the behaviour contract; everything below is one line telling a specific tool to read it.

Three tiers of integration exist and they are **not** equivalent. `docs/HARNESS_MATRIX.md` states which is which.

### Claude Code

```bash
/plugin marketplace add kanadhiayash/shiroe
```

```bash
/plugin install shiroe@shiroe
```

Commands resolve under `/shiroe:<command>`. Full adapter, and a handoff target.

### Codex

```bash
cp .shiroe/CODEX.md ./CODEX.md
```

Native `AGENTS.md` support. Full adapter, and a handoff target.

### Cursor

```bash
cp .shiroe/.cursor/rules/shiroe.mdc .cursor/rules/
```

Handoff target; no adapter.

### Gemini CLI / Antigravity

```bash
cp .shiroe/GEMINI.md ./GEMINI.md
```

Adapter; no handoff target.

### Hermes · Kimi · Odysseus

Adapters ship in `shiroe/adapters/harnesses/`. These read `AGENTS.md` directly — no stub file needed.

### Windsurf

```bash
cp .shiroe/.windsurfrules ./.windsurfrules
```

**Context-only.** The rules file points at `AGENTS.md`; there is no Python adapter. The harness is asked, not compelled.

### Aider

```bash
cp .shiroe/.aider.conf.yml.example ./.aider.conf.yml
```

**Context-only**, same caveat. Note the `.example` suffix — you must copy it.

### Llama family (Ollama, vLLM, Open WebUI)

```bash
cp .shiroe/LLAMA.md ./LLAMA.md
```

System-prompt wrapper approach. Documented, not host-verified.

### Verify

```bash
python3 -m shiroe doctor
```

---

## Commands

Session commands, through your harness:

| Command | Does |
|---|---|
| `/start` | Boot session, restore context per the read ladder |
| `/done` | Persist decisions, refresh `hot.md`, conflict scan, snapshot |
| `/stop` | End session, optional handoff compile and parent sync |
| `/status` | Project, active decisions, open questions, conflicts |
| `/team [type]` | Activate a pack — `solo`, `build`, `research`, `red`, `audit`, `ship` |
| `/sync-parent` | Manual parent rollup |
| `/review-skill` | Review pattern-detected skill drafts |
| `/reset-permissions` | Clear session overrides |

CLI, for verification and inspection:

| Command | Does |
|---|---|
| `shiroe recall <query>` | Search memory — BM25, bi-temporally ranked |
| `shiroe explain-search <query>` | Why each result ranked where it did |
| `shiroe contradictions scan` | Find and queue conflicts |
| `shiroe claims matrix` | Capability evidence matrix — what may be claimed publicly |
| `shiroe release check` | Full 16-check release gate |
| `shiroe doctor` | Installation and freshness report |
| `shiroe audit-privacy --strict` | Repo-wide PII and credential scan |

`shiroe --help` lists all 31.

---

## Memory layout

Everything is a file you can read, diff, and review.

```text
memory/
  hot.md                   ≤500 words, read first
  index.md                 domain index, the boundary file
  DECISIONS.md             confirmed decisions + provenance + evidence grade
  OPEN_QUESTIONS.md        unresolved, with owners
  RISKS.md                 identified risks, with severity
  CONFLICTS.md             contradiction queue — you arbitrate
  MEMORY.md                agent-written session notes
  l1_atoms/*.jsonl         append-only history, never edited
  state/shiroe.sqlite      canonical current state
  indexes/shiroe.sqlite    derived search index, rebuildable
  snapshots/<iso>/         point-in-time state + manifest
  patterns/PATTERNS.jsonl  append-only event log
```

SQLite is canonical for current state. JSONL is the append-only history. Markdown views are **generated** — do not edit them and expect it to stick.

---

## Privacy and security

External sharing is off unless you turn it on. Privacy mode defaults to `abstract`.

| File | Purpose |
|---|---|
| [`PRIVACY.md`](PRIVACY.md) | Privacy mode. Default `abstract`. |
| [`REDACT.md`](REDACT.md) | Sensitive classes and redaction rules. |
| [`SHARING_POLICY.md`](SHARING_POLICY.md) | Connector and sharing policy. All off by default. |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting. |

Redaction is deterministic — regex and Unicode normalization in code, not a model asked to be careful. Input is NFKC-normalized, homoglyphs folded to ASCII, and base64 payloads decoded **before** pattern matching, so a credential cannot evade a rule by changing encoding.

Report vulnerabilities privately. Do not open public issues for them.

---

## FAQ

**Does this call an LLM?**
No. Shiroe performs no inference. It decides which *class* of model a task is entitled to and governs what gets written; your harness makes the call.

**How is this different from a long `CLAUDE.md`?**
A single instruction file grows until it eats your context and gets skimmed. Shiroe's read path is bounded by construction — `hot.md`, then an index, then one section — so cost does not scale with history. And a Markdown file has no write gate: nothing stops a session from recording a claim that contradicts one you already made.

**Why not a vector database?**
Retrieval is lexical BM25 over files in your repo, bi-temporally ranked. You can grep it, diff it, and review a memory change in a PR. A vector store puts your project's decisions in a vendor's account and returns fuzzy matches with no provenance. If semantic recall proves necessary, that is an addition — not the foundation.

**What happens when two sessions disagree?**
The write halts. Both sides land in `memory/CONFLICTS.md` with provenance, and you arbitrate. Newer does not win by being newer.

**Does it work across more than one AI tool?**
That is the point. They all read the same `AGENTS.md` and the same `memory/`. There is no per-tool sync because there is one copy. Enforcement varies by tier — see [Install](#install).

**Is my memory sent anywhere?**
No. There is no Shiroe server. Connectors are off by default in `SHARING_POLICY.md` and must be enabled explicitly.

**Can I use it on an existing project?**
Yes. `shiroe init` scaffolds alongside your code and writes only under `memory/` and `config/`.

**Why are there no benchmark numbers?**
Because none have been produced. See [What is actually verified](#what-is-actually-verified). The release gate blocks this README from claiming otherwise, deliberately.

---

## Limitations

Stated plainly, because the alternative is letting you discover them later.

- **No published benchmark results.** The external harness has run in proxy mode only — retrieval, no generation, no judging.
- **Retrieval trails a lexical baseline** on that proxy. Root cause fixed, not re-measured ([#196](https://github.com/kanadhiayash/shiroe/issues/196)).
- **Shiroe performs no inference.** It routes and governs; your harness calls the model.
- **Enforcement varies by harness.** Context-only integrations can be instructed but not compelled. Tiers are stated in [`docs/HARNESS_MATRIX.md`](docs/HARNESS_MATRIX.md).
- **Privacy redaction is defense-in-depth.** It shrinks the blast radius of a mistake. It is not a reason to paste production credentials into a prompt.
- **Single-machine memory.** Project state lives on the machine it was written on. There is no sync, no shared store, and no multi-device or multi-user story yet.
- **Task graph exists but is not wired into mission execution yet.** `shiroe.graph.compile_task_graph` + `shiroe.graph.run_task_graph` (Wave 6) validate and execute declarative task graphs — unknown nodes, fake edges, missing artifacts, unguarded irreversible steps all fail compilation; parallel-ready nodes overlap, sequential ones do not, loops bound, joins wait. Missions still declare an ordered `execution_sequence` of seats; the task-graph runtime is available for other callers but is not the mission executor yet.
- **Pattern detection proposes, never installs.** Drafts land in `skills/drafts/` for review.
- **Alpha software.** Interfaces may change. MIT, no warranty.

---

## What ships

| Surface | Purpose |
|---|---|
| `AGENTS.md` | Canonical behaviour contract for AI harnesses. |
| `memory/` | Decisions, risks, conflicts, history, generated views. |
| `shiroe/` | Python runtime, guards, adapters, CLI. |
| `skills/` | 15 on-trigger procedures. |
| `agents/` | 6 background roles. |
| `commands/` | 8 user-facing command contracts. |
| `team-packs/` | 9 on-demand multi-agent configurations, capped at 6 agents. |
| `benchmarks/` | Internal quality axes and external loader scaffolding. |
| `shiroe/graph/` | Task-graph compiler + runtime; knowledge graph with provenance, domain/range, atomic merges, guarded promotion, privacy-filtered exports. |
| `docs/` | Architecture, security, release, reference. |

---

## Documentation

| Document | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Canonical agent and harness behaviour. |
| [`INSTALL.md`](INSTALL.md) | Install instructions. |
| [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) | Local setup and verification. |
| [`docs/MEMORY_MODEL.md`](docs/MEMORY_MODEL.md) | Memory layout and read discipline. |
| [`docs/HARNESS_MATRIX.md`](docs/HARNESS_MATRIX.md) | Per-harness support tier and evidence state. |
| [`docs/ROUTING.md`](docs/ROUTING.md) | Reasoning classes and cost policy. |
| [`docs/RELEASE_GATES.md`](docs/RELEASE_GATES.md) | Release readiness checks. |
| [`docs/PUBLIC_SURFACE.md`](docs/PUBLIC_SURFACE.md) | Public claim rules. |
| [`docs/TRUST_AUDIT.md`](docs/TRUST_AUDIT.md) | Trust axis posture and re-grade binding. |
| [`docs/canon/TRUST_RIGHTS.md`](docs/canon/TRUST_RIGHTS.md) | Trust and rights registry — approved sources and rights status for every public visual and imported reference. |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Owner and review cadence for every maintenance surface. |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | Canonical term definitions. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history and naming lineage. |

Wiki pages live under [`docs/wiki/`](docs/wiki/).

---

## Contributing

Open an issue before large changes. Keep pull requests focused. Report security issues privately.

Every PR runs the full local gate before push:

```bash
python3 -m pytest -q \
  && python3 scripts/check-canon-consistency.py --root . \
  && python3 scripts/check-active-identity.py --root . \
  && python3 scripts/shiroe-validate.py \
  && python3 scripts/check-version-consistency.py \
  && python3 scripts/check-trust-registry.py \
  && python3 benchmarks/run-all.py \
  && python3 -m shiroe audit-privacy --strict --fail-classes credentials \
  && python3 -m shiroe release check
```

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)

---

## License

MIT. Bring your own models, harnesses, and workflows. No warranty.
