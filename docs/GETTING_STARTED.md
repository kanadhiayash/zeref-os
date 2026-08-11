# Getting Started

From a repo root:

```bash
python3 -m shiroe --version
python3 -m shiroe init --name "My Project" --privacy abstract --tier auto --parent ""
python3 -m shiroe status
```

Add structured memory:

```bash
python3 -m shiroe memory propose "User prefers public-safe copy by default."
python3 -m shiroe memory write --from proposal.json
python3 -m shiroe memory search "public-safe copy"
```

Run local gates:

```bash
python3 -m pytest -q
python3 scripts/shiroe-validate.py
python3 -m shiroe audit
python3 -m shiroe audit-privacy --strict
python3 scripts/check-version-consistency.py
git diff --check
```

Useful hardening commands:

```bash
python3 -m shiroe factguard scan README.md
python3 -m shiroe evidence check memory/
python3 -m shiroe contradictions scan memory/
python3 -m shiroe privacy scan docs/
python3 -m shiroe route policy validate
python3 -m shiroe release check
python3 -m shiroe doctor
```

`privacy scan` is report-only by default. Use `--strict` when it should fail the
gate on findings.
