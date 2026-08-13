"""Local task routing policy for Shiroe commands."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


DEFAULT_POLICY = {
    "version": "route-policy.v1",
    "default": {"domain": "implementation", "weight": "medium", "lead": "codex-implementer"},
    "routes": [
        {
            "domain": "security",
            "keywords": ["secret", "privacy", "redact", "credential", "threat"],
            "weight": "high",
            "lead": "security-reviewer",
        },
        {
            "domain": "release",
            "keywords": ["release", "publish", "version", "benchmark", "claim"],
            "weight": "high",
            "lead": "release-reviewer",
        },
        {
            "domain": "memory",
            "keywords": ["memory", "recall", "contradiction", "evidence", "source"],
            "weight": "medium",
            "lead": "shiroe-runtime",
        },
        {
            "domain": "docs",
            "keywords": ["readme", "docs", "copy", "public-safe"],
            "weight": "medium",
            "lead": "docs-reviewer",
        },
    ],
}


@dataclass(frozen=True)
class RouteDecision:
    domain: str
    weight: str
    lead: str
    matched_keywords: list[str]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def classify_task(text: str, *, policy: dict | None = None) -> RouteDecision:
    active = policy or DEFAULT_POLICY
    lowered = text.lower()
    best = None
    best_matches: list[str] = []
    for route in active["routes"]:
        matches = [keyword for keyword in route["keywords"] if keyword in lowered]
        if len(matches) > len(best_matches):
            best = route
            best_matches = matches
    if best is None:
        default = active["default"]
        return RouteDecision(
            domain=default["domain"],
            weight=default["weight"],
            lead=default["lead"],
            matched_keywords=[],
            reason="No route keyword matched; using default route.",
        )
    return RouteDecision(
        domain=best["domain"],
        weight=best["weight"],
        lead=best["lead"],
        matched_keywords=best_matches,
        reason=f"Matched route keywords: {', '.join(best_matches)}.",
    )


def validate_policy(policy: dict | None = None) -> list[str]:
    active = policy or DEFAULT_POLICY
    issues: list[str] = []
    if active.get("version") != "route-policy.v1":
        issues.append("policy version must be route-policy.v1")
    if "default" not in active:
        issues.append("policy default route missing")
    for index, route in enumerate(active.get("routes", []), start=1):
        for field in ("domain", "keywords", "weight", "lead"):
            if not route.get(field):
                issues.append(f"route {index} missing {field}")
        if route.get("weight") not in {"low", "medium", "high", "critical"}:
            issues.append(f"route {index} has invalid weight")
    return issues


def policy_json() -> str:
    return json.dumps(DEFAULT_POLICY, indent=2, sort_keys=True) + "\n"


def route_report(samples: list[str] | None = None) -> str:
    tasks = samples or [
        "scan docs for benchmark claims",
        "write memory with evidence",
        "redact credentials before release",
    ]
    lines = ["# Route Report", ""]
    for task in tasks:
        decision = classify_task(task)
        lines.append(f"- `{task}` -> {decision.domain} / {decision.weight} / {decision.lead}")
    return "\n".join(lines) + "\n"
