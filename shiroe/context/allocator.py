"""Token-budget allocator around the six-section context packet (SHR-64).

``packet.py`` renders sections but owns no budget: it cannot exceed-check,
cannot reserve room for the model's answer, and cannot report what it
dropped. A packet can silently overflow the model's context window or
crowd out the output entirely. This module puts a hard budget around it.

Budget order (fixed):

    model context_window (PR 2's provider capability registry)
    - system/harness reserve
    - required output reserve (registry max_output_tokens, unless overridden)
    - safety margin
    = section budget

``objective``, ``permissions``, ``output_schema`` and ``stop_rules`` are
mandatory and are never dropped or trimmed — if they alone exceed the
section budget, :func:`allocate_packet` refuses via :class:`AllocatorError`
rather than emit an impossible packet. Whatever budget remains is split
between memory and evidence records, each ranked (constraint/provenance
records first, else original order) and filled with **whole records
only** — a half-record is corrupted provenance, worse than an absent one.
Every record left out is accounted for in the returned omission manifest.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from shiroe.adapters.providers import DEFAULT_PROVIDER, get_provider
from shiroe.adapters.providers.base import ModelCapability
from shiroe.codecs.base import default_token_estimate
from shiroe.context.packet import ContextPacket, build_packet

# ponytail: fixed constants rather than a config surface. Upgrade path: move
# to config/COST_POLICY.json if a second caller needs to tune these
# independently of the allocator's defaults.
DEFAULT_SYSTEM_HARNESS_RESERVE = 500
DEFAULT_SAFETY_MARGIN_RATIO = 0.02
DEFAULT_SAFETY_MARGIN_MIN = 100

# ponytail: naive kind-based ranking (records tagged kind/type in
# {"constraint", "provenance"} sort first, ties broken by original order).
# Upgrade path: an explicit numeric priority field on the record schema if
# a caller needs finer-grained ranking than "pinned vs everything else".
_HIGH_PRIORITY_KINDS = frozenset({"constraint", "provenance"})

MANDATORY_SECTIONS: tuple[str, ...] = ("objective", "permissions", "output_schema", "stop_rules")
RANKED_SECTIONS: tuple[str, ...] = ("memory", "evidence")


class AllocatorError(ValueError):
    """Raised when the packet cannot be built within the model's budget."""


@dataclass(frozen=True)
class Omission:
    section: str
    kept_count: int
    dropped_count: int
    reason: str


@dataclass(frozen=True)
class AllocationBudget:
    context_window: int
    system_harness_reserve: int
    output_reserve: int
    safety_margin: int
    available_for_sections: int
    mandatory_tokens: int
    ranked_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.mandatory_tokens + self.ranked_tokens

    @property
    def reserved_output(self) -> int:
        return self.output_reserve


@dataclass
class AllocationResult:
    packet: ContextPacket
    budget: AllocationBudget
    omissions: list[Omission] = field(default_factory=list)

    def as_manifest(self) -> dict:
        """The omission manifest: what was dropped, how many, why.

        Always present (even when nothing was dropped) so silent omission —
        the defect this ticket exists to close — is structurally impossible.
        """
        return {
            "context_window": self.budget.context_window,
            "available_for_sections": self.budget.available_for_sections,
            "used_tokens": self.budget.total_tokens,
            "omissions": [
                {
                    "section": o.section,
                    "kept": o.kept_count,
                    "dropped": o.dropped_count,
                    "reason": o.reason,
                }
                for o in self.omissions
            ],
        }


def resolve_capability(reasoning_class: str, provider: str = DEFAULT_PROVIDER) -> ModelCapability:
    """The one place the allocator touches PR 2's registry directly."""
    return get_provider(provider).capability(reasoning_class)


def _record_priority(record: dict) -> int:
    kind = str(record.get("kind") or record.get("type") or "").strip().lower()
    return 0 if kind in _HIGH_PRIORITY_KINDS else 1


def _record_tokens(record: dict) -> int:
    return default_token_estimate(json.dumps(record, sort_keys=True, ensure_ascii=False))


def _fit_section(records: list[dict], budget: int) -> tuple[list[dict], int, int]:
    """Greedily keep whole records within ``budget``, ranked by priority
    (see ``_record_priority``) then original position. Returned records
    keep their original relative order. Never slices a record."""
    if not records or budget <= 0:
        return [], len(records), 0
    order = sorted(range(len(records)), key=lambda i: (_record_priority(records[i]), i))
    used = 0
    keep: set[int] = set()
    for i in order:
        cost = _record_tokens(records[i])
        if used + cost <= budget:
            used += cost
            keep.add(i)
    kept = [records[i] for i in range(len(records)) if i in keep]
    return kept, len(records) - len(kept), used


def _split_and_fit(
    memory_records: list[dict], evidence: list[dict], total_budget: int
) -> tuple[list[dict], int, int, list[dict], int, int]:
    """Deterministic two-pass split: an even half each, then any budget one
    section leaves unused rolls over to the other. A second, bounded pass
    lets memory reclaim slack evidence didn't need, so neither list is
    starved just because it was the second one filled."""
    mem_budget = total_budget // 2
    ev_budget = total_budget - mem_budget

    mem_kept, mem_dropped, mem_used = _fit_section(memory_records, mem_budget)
    ev_kept, ev_dropped, ev_used = _fit_section(evidence, ev_budget + (mem_budget - mem_used))

    leftover = (ev_budget + (mem_budget - mem_used)) - ev_used
    if leftover > 0 and mem_dropped > 0:
        mem_kept, mem_dropped, mem_used = _fit_section(memory_records, mem_used + leftover)

    return mem_kept, mem_dropped, mem_used, ev_kept, ev_dropped, ev_used


def allocate_packet(
    *,
    objective: str,
    permissions: dict,
    memory_records: list[dict] | None = None,
    evidence: list[dict] | None = None,
    output_schema: dict | None = None,
    stop_rules: str = "",
    capability: ModelCapability | None = None,
    reasoning_class: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    model_or_harness: str | None = None,
    output_reserve: int | None = None,
    system_harness_reserve: int = DEFAULT_SYSTEM_HARNESS_RESERVE,
    safety_margin: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> AllocationResult:
    """Build a six-section :class:`ContextPacket` that fits the resolved
    model's context window, or refuse. Deterministic: identical input
    (including the resolved capability) produces identical allocation.

    ``capability`` is the resolved model's :class:`ModelCapability` (pass it
    directly, e.g. from a ``RouteDecision``, when you already resolved one).
    ``reasoning_class``/``provider`` are a convenience that looks it up from
    PR 2's registry when you have not resolved one yet.
    """
    memory_records = list(memory_records or [])
    evidence = list(evidence or [])

    if capability is None:
        if reasoning_class is None:
            raise AllocatorError(
                "allocate_packet requires either capability= or reasoning_class= "
                "to look up a context limit — refusing to guess one"
            )
        capability = resolve_capability(reasoning_class, provider)

    if capability.context_window is None:
        raise AllocatorError(
            "resolved model has no context_window recorded in the provider "
            "capability registry — refusing to allocate against an unknown limit"
        )

    context_window = capability.context_window
    reserve_output = output_reserve if output_reserve is not None else capability.max_output_tokens
    if reserve_output is None:
        raise AllocatorError(
            "resolved model has no max_output_tokens recorded and no output_reserve "
            "override was given — refusing to allocate without reserving room for the answer"
        )
    margin = (
        safety_margin
        if safety_margin is not None
        else max(DEFAULT_SAFETY_MARGIN_MIN, round(context_window * DEFAULT_SAFETY_MARGIN_RATIO))
    )

    available = context_window - system_harness_reserve - reserve_output - margin
    if available <= 0:
        raise AllocatorError(
            f"reserves alone ({system_harness_reserve} harness + {reserve_output} output + "
            f"{margin} safety margin = {system_harness_reserve + reserve_output + margin}) "
            f"meet or exceed the model's context window ({context_window}) — nothing left for content"
        )

    # Mandatory sections, rendered once through the existing codec pipeline
    # (packet.py owns the rendering; the allocator only measures and gates).
    mandatory_packet = build_packet(
        objective=objective,
        permissions=permissions,
        output_schema=output_schema,
        stop_rules=stop_rules,
        model_or_harness=model_or_harness,
        conn=conn,
    )
    mandatory_tokens = sum(
        default_token_estimate(mandatory_packet.sections[name])
        for name in MANDATORY_SECTIONS
        if name in mandatory_packet.sections
    )
    if mandatory_tokens > available:
        raise AllocatorError(
            f"mandatory sections alone need {mandatory_tokens} tokens but only "
            f"{available} are available after reserves — refusing to emit a "
            "packet that cannot carry its required sections"
        )

    ranked_budget = available - mandatory_tokens
    mem_kept, mem_dropped, mem_used, ev_kept, ev_dropped, ev_used = _split_and_fit(
        memory_records, evidence, ranked_budget
    )

    final_packet = build_packet(
        objective=objective,
        permissions=permissions,
        memory_records=mem_kept,
        evidence=ev_kept,
        output_schema=output_schema,
        stop_rules=stop_rules,
        model_or_harness=model_or_harness,
        conn=conn,
    )

    omissions: list[Omission] = []
    if memory_records:
        omissions.append(Omission(
            section="memory",
            kept_count=len(mem_kept),
            dropped_count=mem_dropped,
            reason=(
                "all records retained"
                if mem_dropped == 0
                else f"budget exhausted after ranking — {mem_dropped} whole record(s) omitted, none truncated"
            ),
        ))
    if evidence:
        omissions.append(Omission(
            section="evidence",
            kept_count=len(ev_kept),
            dropped_count=ev_dropped,
            reason=(
                "all records retained"
                if ev_dropped == 0
                else f"budget exhausted after ranking — {ev_dropped} whole record(s) omitted, none truncated"
            ),
        ))

    budget = AllocationBudget(
        context_window=context_window,
        system_harness_reserve=system_harness_reserve,
        output_reserve=reserve_output,
        safety_margin=margin,
        available_for_sections=available,
        mandatory_tokens=mandatory_tokens,
        ranked_tokens=mem_used + ev_used,
    )
    return AllocationResult(packet=final_packet, budget=budget, omissions=omissions)
