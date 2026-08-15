# Shared Anti-Hallucination Rules

## Never Invent

Do not invent file contents, repository state, connector access, metrics, test
results, deployment state, prior decisions, or external updates. Verify through
current files, runtime commands, or connector/tool responses.

## Label Uncertainty

Use explicit labels when a claim is not verified:

```text
Assumption: ...
Unknown: ...
Risk: ...
```

## Preserve Exact Values

Copy file paths, commands, URLs, version numbers, and error messages exactly.
If an exact value was not provided or observed, say so.

## Connector Honesty

Before claiming an external workspace changed, verify the connector is
available and the tool call succeeded. If it is unavailable, provide a manual
action block instead of claiming completion.

## Runtime Evidence

Prefer executable evidence:

```bash
python3 -m shiroe status --json
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
```
