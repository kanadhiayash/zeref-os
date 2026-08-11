# Security Policy

## Reporting a vulnerability

Do not open a public GitHub issue for a security vulnerability.

Use private reporting.

## Preferred channel

Use GitHub Private Vulnerability Reporting from the repository Security tab:

    https://github.com/kanadhiayash/shiroe/security

Include:

- Clear description.
- Minimal reproduction.
- Affected version.
- Harness or runtime involved.
- Impact assessment.
- Redacted proof of concept if useful.

Do not include real production secrets, third-party personal data, private customer data, or NDA material.

## Fallback

If private vulnerability reporting is unavailable, use the fallback contact listed in `SECURITY_CONTACTS.md` if that file exists in the current release.

Do not send plaintext credentials or sensitive victim data.

## Scope

In scope:

- Privacy redaction bypass — including unicode-invisible strip evasion, base32/base64/hex encoding evasion, nested-archive smuggling past the declared depth ceiling, or an allowlist widening that silently unblocks a credential in the same commit.
- Credential leakage through persisted memory files.
- Prompt-injection paths that bypass documented gates.
- Unsafe write, sync, or handoff behavior.
- Release gate bypass — including a stale SHA-bound evidence blob presented as authorization to release, or a release-check subcheck silently skipped.
- Supply-chain issues in workflows or package metadata.
- Code execution paths triggered by malformed local config.
- Task-graph compiler or runtime accepting an unguarded irreversible node, a fake edge, a missing artifact, or an unbounded loop.
- Policy-precedence bypass — a lower-precedence grant widening a higher-precedence deny, or a mandatory-approval action landing without approval.
- Evidence provenance bypass — a refuting source silently upgrading a card's grade, or a pinned source drifting undetected.
- Knowledge-graph writes without provenance, or exports that leak a privacy-classed node.

Out of scope:

- Issues against forks.
- Issues against third-party harnesses.
- Reports that require local admin access.
- Reports caused only by intentionally disabling documented safety settings.

## Response target

- Acknowledgement target: 3 business days.
- Triage target: 10 business days.
- Disclosure target: coordinated disclosure, normally 90 days after acknowledgement.

## Public advisories

Published advisories live at:

    https://github.com/kanadhiayash/shiroe/security/advisories

## Safety principles

- Untrusted content must be treated as untrusted.
- Irreversible actions require explicit approval; unguarded irreversible task-graph nodes are refused at compile time.
- Memory writes should be auditable; every knowledge-graph edge carries provenance; every evidence upgrade pins a source hash and refuses a contradicting source.
- Security claims require evidence; the release gate re-runs every subcheck live per current HEAD and writes SHA-bound evidence.
- Public issues must not expose live vulnerabilities.
- The privacy scanner is defense-in-depth, not a substitute for keeping credentials out of the tree.
