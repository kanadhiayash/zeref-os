# Security Hardening Checklist

This checklist tracks repository-level security setup.

## GitHub settings to verify

- Secret scanning enabled.
- Push protection enabled.
- Dependabot alerts enabled.
- Dependabot security updates enabled.
- Code scanning enabled.
- Private vulnerability reporting enabled.
- Dependency review enabled for pull requests.
- `main` protected by a branch ruleset.
- `v*` tags protected by a tag ruleset.

## Main branch ruleset

Required behavior:

- Pull request required before merge.
- At least one approving review.
- Conversation resolution required.
- Required status checks pass.
- Force pushes blocked.
- Branch deletion blocked.
- Direct pushes restricted.

## Tag ruleset

Required behavior:

- Applies to `v*`.
- Tag deletion blocked.
- Tag update blocked.
- Release tags only from approved release flow.

## Required local gates

Run before release:

    python3 -m pytest -q
    python3 scripts/shiroe-validate.py
    python3 scripts/check-version-consistency.py
    python3 scripts/check-trust-registry.py
    python3 -m shiroe doctor --json
    python3 -m shiroe state verify --json
    python3 scripts/release_ready.py
    git diff --check
