<!-- privacy-audit: allow-file "Sharing policy enumerates connector names and redaction classes." -->
---
defaults:
  read_project_context: false
  write_external: false
connectors:
  github:
    enabled: false
    read_project_context: false
    allowed_surfaces: []
    redact_classes: [credentials, pii, internal_paths]
  linear:
    enabled: false
    read_project_context: false
    allowed_surfaces: []
    redact_classes: [credentials, pii, client_data]
  notion:
    enabled: false
    read_project_context: false
    allowed_surfaces: []
    redact_classes: [credentials, pii, client_data, financial]
  slack:
    enabled: false
    read_project_context: false
    allowed_surfaces: []
    redact_classes: [credentials, pii, client_data]
  provider_refresh:
    enabled: false
    read_project_context: false
    allowed_surfaces: [list-models]
    redact_classes: []
---

# SHARING_POLICY.md

Connectors are off by default. Shiroe does not install or enable connectors on
the user's behalf.

## Rules

1. A connector must be explicitly enabled before use.
2. Reading project context and writing externally are separate permissions.
3. External writes still require policy allowance and any required human
   approval.
4. Outbound content is scrubbed using the connector's `redact_classes`.
5. Connectors are integration surfaces, not canonical memory.

Related files: `PRIVACY.md`, `REDACT.md`, and `.shiroe/policy/*.json`.
