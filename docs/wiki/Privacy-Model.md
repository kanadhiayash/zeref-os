# Privacy Model

Privacy in Shiroe is deterministic and code-enforced. The `shiroe/privacy.py`
runtime applies redaction rules before canonical writes and handoffs. Nothing
depends on a model remembering to be careful.

That distinction is the whole design. A model asked to redact is a model that can be talked out of redacting. A regex cannot be persuaded.

## Two modes

Set in the root `PRIVACY.md`.

| Mode | Default | Behavior |
|---|---|---|
| `exact` | — | Write verbatim. No abstraction. |
| `abstract` | **yes** | Strip PII, internal paths, and credentials before write. |

```yaml
mode: abstract                  # exact | abstract
abstract_rules:
  strip_pii: true
  strip_internal_paths: true
  strip_credentials: true
  strip_numbers: false
connectors_default: off
external_transmission: off
```

Defaults are conservative on purpose: sharing is off until you turn it on, and a fresh project starts in `abstract`.

## Redaction classes

`REDACT.md` declares what gets stripped. Classes cover credentials (API keys, OAuth tokens, SSH private keys, database connection strings, environment values), personal data (email addresses, phone numbers, physical addresses, government IDs, dates of birth), internal filesystem paths, client data, financial data, and proprietary code.

Each class is independently switchable, so you can loosen one without loosening all of them.

## Why encoding tricks do not work

Pattern matching alone is weak — a credential can evade a regex by changing shape rather than content. Redaction therefore normalizes before it matches:

| Stage | Handles |
|---|---|
| NFKC normalization | Fullwidth and compatibility variants of ASCII characters. |
| Homoglyph folding | Look-alike characters from other scripts standing in for ASCII. |
| Base64 decoding | Credentials wrapped in an encoding layer. |
| Pattern match | The normalized, decoded text. |

Matching normalized text rather than raw input means a secret has to be a secret in substance, not merely in spelling, to slip through.

This is defense-in-depth. It reduces the blast radius of a mistake. It is not a reason to paste production credentials into a prompt.

## Export is fail-closed

Handoff artifacts are compiled from stored atoms and filtered by privacy class on the way out.

| Class | Default export | Private export requested |
|---|---|---|
| `public-safe` | Exported | Exported |
| `private` | Withheld | Exported |
| `unknown` | Withheld | Exported |
| `restricted` | Withheld | Withheld |

Two properties are worth stating explicitly.

**`unknown` is treated exactly like `private`.** An atom whose privacy class was never asserted must not leak simply because nobody got around to classifying it. The default for unclassified content is withhold, not share.

**`restricted` records never leave the machine.** Not with a flag, not with private export enabled. That is the contract of the class; if a flag could override it, the class would mean nothing.

## Sharing policy

`SHARING_POLICY.md` governs connectors and external destinations. Connectors are off by default and require explicit per-action approval. Adding a destination is a deliberate act, not a side effect of using a feature.

## Staged sync

Nothing syncs automatically. Content is filtered by evidence grade, redacted, and staged with a manifest. You see a preview of exactly what would leave before anything moves, and approval is explicit.

For `restricted` records, the path is blocked entirely and staging does not proceed.

## Configuration files

| File | Purpose |
|---|---|
| [`PRIVACY.md`](https://github.com/kanadhiayash/shiroe/blob/main/PRIVACY.md) | Active mode and abstraction rules. |
| [`REDACT.md`](https://github.com/kanadhiayash/shiroe/blob/main/REDACT.md) | Sensitive classes and patterns. |
| [`SHARING_POLICY.md`](https://github.com/kanadhiayash/shiroe/blob/main/SHARING_POLICY.md) | Connector and destination allowlist. |
| [`SECURITY.md`](https://github.com/kanadhiayash/shiroe/blob/main/SECURITY.md) | Vulnerability reporting. |

## Verify it yourself

```bash
python3 -m shiroe doctor --json
python3 -m pytest -q
```

Report vulnerabilities privately per [`SECURITY.md`](https://github.com/kanadhiayash/shiroe/blob/main/SECURITY.md). Do not open public issues for them.

## Related

- [[Memory-Model]] — where writes land
- [[Architecture]] — the governance runtime
- [[Installation]] — configure privacy before first write
- [[FAQ]] — common questions
