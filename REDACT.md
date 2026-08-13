<!-- privacy-audit: allow-file "REDACT.md IS the redaction spec — every pattern description is intentional documentation of the classifier." -->
---
# Concrete sensitive classes — `privacy-abstraction` skill strips these before write
# `privacy-guardian` checks these before any external transmission
classes:
  credentials:
    enabled: true
    patterns:
      - api_keys                  # AWS_ACCESS_KEY_ID, OPENAI_API_KEY, bearer tokens, etc.
      - oauth_tokens
      - ssh_private_keys
      - database_connection_strings
      - .env values
  pii:
    enabled: true
    patterns:
      - email_addresses
      - phone_numbers
      - physical_addresses
      - government_ids            # SSN, passport, license
      - dates_of_birth
  email:
    enabled: true                  # always-on — homoglyph + base64 bypass coverage
    replacement: "[PII:email]"
    patterns:
      - email_addresses_standalone # bare addresses outside name patterns
  internal_paths:
    enabled: true
    patterns:
      - absolute_filesystem_paths  # /Users/<name>/..., /home/<name>/...
      - hostnames
      - internal_urls              # *.internal, *.corp, VPN-only domains
  client_data:
    enabled: false                 # enable per project if client/employer work
    patterns:
      - client_names
      - account_ids
      - contract_numbers
  financial:
    enabled: false                 # enable to redact $/metric values
    patterns:
      - dollar_amounts
      - revenue_figures
      - headcount_numbers
  proprietary_code:
    enabled: false                 # enable for closed-source work
    patterns:
      - internal_function_names
      - proprietary_algorithms
---

# REDACT.md — Concrete sensitive classes

> Sourced from package §4.1. Enable classes per project. `privacy-abstraction` reads this before every write when mode = `abstract`.

## How redaction works

1. `privacy-guardian` reads `PRIVACY.md` mode.
2. If mode = `abstract`, `privacy-abstraction` skill runs over the candidate write.
3. Skill walks each `enabled: true` class in this file and substitutes per the `replacement_strategy` below.
4. Resulting content goes to `shiroe-runtime` for write.
5. Original raw content NEVER lands in `memory/` outside `memory/raw/` (which is gitignored or local-only).

## Replacement strategy

| Class | Strategy |
|---|---|
| credentials | full removal — replace with `<REDACTED:credential>` |
| pii | hash-based pseudonym — `<user:a3f9>` consistent across writes |
| internal_paths | abstract to repo-relative — `/Users/x/proj/foo` → `<repo>/foo` |
| client_data | full removal or pseudonym (project-configured) |
| financial | bucket — `$1,234,567` → `<order:$1M-10M>` |
| proprietary_code | full removal — replace with `<REDACTED:internal>` |

## What to do when uncertain

If `privacy-abstraction` cannot classify with high confidence:
- HALT the write
- Surface to user: "Cannot classify <snippet>. Treat as: [credentials | pii | safe | skip]?"
- Never silently include uncertain content.

## Add a custom class

Append to `classes:` with `enabled: true` and `patterns:` list. The pattern names are routed to the regex/heuristic library in `skills/privacy-abstraction/SKILL.md`.

## Related

- `PRIVACY.md` — modes and global policy
- `SHARING_POLICY.md` — per-connector external sharing rules
