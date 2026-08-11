"""
privacy-audit: allow-file "Harness names provenance/cost schema fields and env-var names as spec; no user data."

External benchmark runner core (WS5 Phase A).

Loads a dataset through a loader, drives a memory backend (ingest -> recall),
scores per the benchmark's own metric, and writes results JSON bound to
{git SHA, dataset version/hash, model id, prompts hash, token/cost record,
timestamp}. Phase A only supports ``--dry-run`` (no API calls); live provider
runs are Phase B and budget-gated.

Usage:
    python3 -m benchmarks.external.harness --benchmark locomo \
        --data /path/to/locomo --backend plain_files --dry-run \
        --out benchmarks/external/results/locomo-dryrun.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from benchmarks.external.loaders import get_loader  # noqa: E402
from benchmarks.external.providers.base import Provider  # noqa: E402
from benchmarks.external.schema import Task, sha256_file, sha256_text  # noqa: E402

HARNESS_VERSION = "0.1.0-phase-a"

PROMPT_TEMPLATE = (
    "You are answering a question using retrieved memory.\n"
    "Retrieved context:\n{context}\n\n"
    "Question: {question}\n"
    "{options_block}"
    "Answer concisely."
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class MemoryBackend(Protocol):
    """Ingest/recall interface shared by shiroe and the honest baselines."""

    name: str

    def reset(self) -> None: ...

    def ingest(self, chunk_id: str, text: str) -> None: ...

    def recall(self, query: str, k: int = 5) -> list[str]: ...


# --- metrics (the benchmark's own scoring conventions) -----------------------

def normalize_answer(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def exact_match(prediction: str, answers: tuple[str, ...]) -> float:
    prediction_norm = normalize_answer(prediction)
    return float(any(prediction_norm == normalize_answer(answer) for answer in answers))


def token_f1(prediction: str, answers: tuple[str, ...]) -> float:
    """SQuAD-style max token F1 over acceptable answers."""
    prediction_tokens = normalize_answer(prediction).split()
    best = 0.0
    for answer in answers:
        answer_tokens = normalize_answer(answer).split()
        if not prediction_tokens or not answer_tokens:
            best = max(best, float(prediction_tokens == answer_tokens))
            continue
        common = Counter(prediction_tokens) & Counter(answer_tokens)
        overlap = sum(common.values())
        if overlap == 0:
            continue
        precision = overlap / len(prediction_tokens)
        recall = overlap / len(answer_tokens)
        best = max(best, 2 * precision * recall / (precision + recall))
    return best


def choice_accuracy(prediction: str, answers: tuple[str, ...]) -> float:
    prediction_norm = normalize_answer(prediction)
    return float(any(
        prediction_norm == normalize_answer(answer)
        or prediction_norm.startswith(normalize_answer(answer)[:1] + " ")
        for answer in answers
    ))


METRICS = {
    "exact_match": exact_match,
    "token_f1": token_f1,
    "choice_accuracy": choice_accuracy,
}


def retrieval_hit(retrieved: list[str], answers: tuple[str, ...]) -> float:
    """Dry-run proxy only: did any gold answer's tokens appear in retrieved
    context? NOT the benchmark's official metric; never publish as a score."""
    context_tokens = set(_TOKEN_RE.findall(" ".join(retrieved).lower()))
    for answer in answers:
        answer_tokens = set(_TOKEN_RE.findall(answer.lower()))
        if answer_tokens and answer_tokens <= context_tokens:
            return 1.0
    return 0.0


# --- provenance ---------------------------------------------------------------

def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _model_family(model_id: str | None) -> str | None:
    """Coarse vendor family for a model id, for the independence check."""
    if not model_id:
        return None
    lowered = model_id.lower()
    for family in ("gemini", "claude", "gpt", "llama", "mistral"):
        if family in lowered:
            return family
    return None


def _judge_independence(model_id: str | None, judge_model: str | None) -> dict[str, Any]:
    """Whether the generator and judge come from the same model family.

    Not a pass/fail gate — a statement of fact attached to every run so the
    caveat travels with the number instead of living only in a PR comment.
    """
    gen_family = _model_family(model_id)
    judge_family = _model_family(judge_model)
    same_family = bool(gen_family and judge_family and gen_family == judge_family)
    return {
        "generator_family": gen_family,
        "judge_family": judge_family,
        "same_family": same_family,
        "same_model": bool(model_id and judge_model and model_id == judge_model),
        "caveat": (
            "Generator and judge share a model family; LLM judges favour their "
            "own family, so absolute scores may be inflated. All arms share one "
            "generator and one judge, so the relative ranking between arms is "
            "unaffected. Do not publish this as an absolute leaderboard score."
            if same_family else
            "Generator and judge are from different model families."
        ),
    }


def _dataset_digest(loader, data_dir: Path) -> str | None:
    """Digest the dataset, whether it is one file or a directory tree.

    ConvoMem ships ~2,500 files, so the single-file assumption here used to
    raise IsADirectoryError. A loader that knows how to fingerprint itself
    (tree_sha256) wins; otherwise fall back to hashing the named file.
    """
    tree_digest = getattr(loader, "tree_sha256", None)
    if callable(tree_digest):
        return tree_digest(data_dir)
    data_file = data_dir / loader.DATA_FILENAME
    return sha256_file(data_file) if data_file.is_file() else None


def build_provenance(
    loader, data_dir: Path, model_id: str, prompts_hash: str,
    usage_total: dict[str, Any], mode: str,
    *,
    judge_model: str | None = None,
    seed: int | None = None,
    avg_latency_ms: float | None = None,
    failures: list[dict[str, Any]] | None = None,
    exclusions: list[dict[str, Any]] | None = None,
    command: list[str] | None = None,
    raw_artifact: str | None = None,
) -> dict[str, Any]:
    return {
        "git_sha": git_sha(),
        "harness_version": HARNESS_VERSION,
        # SHR-086..089: every published external-run result names its
        # dataset lock, invoking command, model, commit, metric type,
        # cost, and raw-artifact pointer. command defaults to sys.argv
        # so a runner that forgets to pass it still records the
        # interpreter invocation.
        "command": command if command is not None else list(sys.argv),
        "raw_artifact": raw_artifact,
        "metric_type": getattr(loader, "METRIC", None),
        "dataset": {
            "name": loader.NAME,
            "official_url": loader.OFFICIAL_URL,
            "pinned_version": loader.PINNED_VERSION,
            "sha256_pinned": loader.PINNED_SHA256,
            "sha256_actual": _dataset_digest(loader, data_dir),
            "license": getattr(loader, "LICENSE", None),
            "license_note": getattr(loader, "LICENSE_NOTE", None),
            "path": str(data_dir),
        },
        "model_id": model_id,
        # Retrieval granularity decides what every arm can retrieve, so it is
        # part of the run's identity: a result produced at a different chunk
        # size is not comparable to this one.
        "chunk_target_chars": CHUNK_TARGET_CHARS,
        "judge_model": judge_model,
        # Generator and judge sharing one model family biases absolute scores
        # (LLM judges prefer their own family) but not the RELATIVE ranking
        # between arms, because every arm shares the same generator and judge.
        # Recorded per run so a published number carries the caveat with it.
        "judge_independence": _judge_independence(model_id, judge_model),
        "seed": seed,
        "prompts_hash": prompts_hash,
        "cost": usage_total,
        "avg_latency_ms": avg_latency_ms,
        "failures": failures if failures is not None else [],
        "exclusions": exclusions if exclusions is not None else [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
    }


# --- chunking ------------------------------------------------------------------

# Retrieval granularity, in characters (~2k tokens at the 4-chars-per-token
# heuristic used for cost estimates). This is a FROZEN benchmark parameter:
# it decides what a "retrieved chunk" is for every arm, so changing it changes
# every score and starts a new run series. It is recorded in provenance.
CHUNK_TARGET_CHARS = 8000


def _split_oversized(line: str, limit: int) -> list[str]:
    """Break one over-long line, preferring a newline then a space boundary.

    Needed because RULER and HELMET carry their entire haystack as a single
    turn — at long context lengths that is one multi-megabyte line, and
    without splitting it there is nothing for a retriever to choose between.
    """
    pieces: list[str] = []
    remaining = line
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut < limit // 2:  # no usable boundary: hard cut rather than loop
            cut = limit
        pieces.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def iter_chunks(task: Task, limit: int = CHUNK_TARGET_CHARS):
    """Yield ``(chunk_id, text)`` for one task, in original order.

    Chunking is deliberately NOT the same thing as session splitting. Session
    boundaries alone produce exactly one chunk for any benchmark whose loader
    emits a single session — ConvoMem, PersonaMem, RULER and HELMET all do —
    and a single chunk makes `recall(k)` a no-op: every arm receives the whole
    haystack and the three-arm comparison silently degrades into three
    identical prompts and three identical scores.

    So sessions are the primary unit (they carry conversational meaning for
    LoCoMo and LongMemEval), and any session over ``limit`` is packed into
    sub-chunks at turn boundaries, never mid-turn, so speaker attribution and
    temporal order survive. Order is preserved throughout, which is what lets
    the full_context arm reconstruct the original haystack.
    """
    for session_idx, session in enumerate(task.sessions):
        lines: list[str] = []
        for turn in session:
            rendered = f"{turn.role}: {turn.content}"
            if len(rendered) > limit:
                lines.extend(_split_oversized(rendered, limit))
            else:
                lines.append(rendered)

        buffer: list[str] = []
        size = 0
        chunk_idx = 0
        for line in lines:
            if buffer and size + len(line) + 1 > limit:
                yield f"{task.task_id}:s{session_idx}:c{chunk_idx}", "\n".join(buffer)
                chunk_idx += 1
                buffer, size = [], 0
            buffer.append(line)
            size += len(line) + 1
        if buffer:
            yield f"{task.task_id}:s{session_idx}:c{chunk_idx}", "\n".join(buffer)


# --- runner --------------------------------------------------------------------

def ingest_task(backend: MemoryBackend, task: Task, chunk_chars: int = CHUNK_TARGET_CHARS) -> None:
    backend.reset()
    for chunk_id, text in iter_chunks(task, chunk_chars):
        backend.ingest(chunk_id, text)


def build_prompt(task: Task, retrieved: list[str]) -> str:
    options_block = ""
    if task.options:
        options_block = "Options:\n" + "\n".join(task.options) + "\n"
    return PROMPT_TEMPLATE.format(
        context="\n---\n".join(retrieved) if retrieved else "(no context retrieved)",
        question=task.question,
        options_block=options_block,
    )


def run_benchmark(
    benchmark: str,
    data_dir: str | Path,
    backend: MemoryBackend,
    provider: Provider | None = None,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    recall_k: int = 5,
) -> dict[str, Any]:
    """Run one benchmark end-to-end. Phase A: dry_run must be True."""
    if not dry_run and provider is None:
        raise ValueError("live mode requires a provider")
    if not dry_run:
        raise RuntimeError(
            "Live scored runs are Phase B (budget-gated). Phase A only "
            "supports --dry-run, which never calls a paid API."
        )

    loader = get_loader(benchmark)
    data_path = Path(data_dir)
    tasks = loader.load(data_path)
    if limit is not None:
        tasks = tasks[:limit]

    prompts: list[str] = []
    per_task: list[dict[str, Any]] = []
    usage_total = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "estimated": True}

    for task in tasks:
        ingest_task(backend, task)
        retrieved = backend.recall(task.question, k=recall_k)
        prompt = build_prompt(task, retrieved)
        prompts.append(prompt)

        record: dict[str, Any] = {
            "task_id": task.task_id,
            "metric": task.metric,
            "retrieved_chunks": len(retrieved),
            # dry-run proxy only — not the benchmark's official metric
            "retrieval_hit_proxy": retrieval_hit(retrieved, task.answers),
            "official_score": None,
            "prediction": None,
        }
        if provider is not None:
            usage = provider.estimate(prompt)
            usage_total["input_tokens"] += usage.input_tokens
            usage_total["output_tokens"] += usage.output_tokens
            usage_total["cost_usd"] = round(usage_total["cost_usd"] + usage.cost_usd, 6)
        per_task.append(record)

    prompts_hash = sha256_text(PROMPT_TEMPLATE + "\n\x00".join(prompts))
    model_id = provider.model_id if provider is not None else "none (dry-run, no provider)"
    hits = [record["retrieval_hit_proxy"] for record in per_task]

    return {
        "label": (
            "DRY RUN — infrastructure check only. No model was called; "
            "retrieval_hit_proxy is not the benchmark's official metric and "
            "no external benchmark score is claimed."
        ),
        "benchmark": benchmark,
        "backend": backend.name,
        "task_count": len(per_task),
        "official_metric_scores": None,
        "retrieval_hit_proxy_mean": (sum(hits) / len(hits)) if hits else None,
        "tasks": per_task,
        "provenance": build_provenance(
            loader, data_path, model_id, prompts_hash, usage_total,
            mode="dry_run",
        ),
    }


def write_results(path: str | Path, payload: dict[str, Any]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


_BACKEND_FACTORIES = {
    "plain_files": lambda: __import__(
        "benchmarks.external.baselines.plain_files", fromlist=["PlainFilesBackend"]
    ).PlainFilesBackend(),
    "sqlite_fts": lambda: __import__(
        "benchmarks.external.baselines.sqlite_store", fromlist=["SqliteFtsBackend"]
    ).SqliteFtsBackend(),
    "shiroe": lambda: __import__(
        "benchmarks.external.baselines.shiroe_backend", fromlist=["ShiroeBackend"]
    ).ShiroeBackend(),
    "full_context": lambda: __import__(
        "benchmarks.external.baselines.full_context", fromlist=["FullContextBackend"]
    ).FullContextBackend(),
    "bm25": lambda: __import__(
        "benchmarks.external.baselines.bm25", fromlist=["Bm25Backend"]
    ).Bm25Backend(),
}


def _make_backend(name: str):
    try:
        return _BACKEND_FACTORIES[name]()
    except KeyError:
        raise KeyError(
            f"unknown backend {name!r}; supported: {sorted(_BACKEND_FACTORIES)}"
        ) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--data", required=True, help="local dataset directory (manual download)")
    parser.add_argument("--backend", default="plain_files")
    parser.add_argument("--provider", default=None, choices=[None, "anthropic"])
    parser.add_argument("--dry-run", action="store_true",
                        help="estimate tokens/cost without any API call (Phase A: required)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    provider = None
    if args.provider == "anthropic":
        from benchmarks.external.providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(dry_run=True)

    payload = run_benchmark(
        args.benchmark, args.data, _make_backend(args.backend), provider,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    if args.out:
        out = write_results(args.out, payload)
        print(f"results written to {out}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
