<!-- privacy-audit: allow-file "REDACT.md defines redaction classes and example pattern names." -->
---
classes:
  credentials:
    enabled: true
    patterns:
      - api_keys
      - oauth_tokens
      - ssh_private_keys
      - database_connection_strings
  pii:
    enabled: true
    patterns:
      - email_addresses
      - phone_numbers
      - physical_addresses
      - government_ids
  email:
    enabled: true
    replacement: "[PII:email]"
    patterns:
      - email_addresses_standalone
  internal_paths:
    enabled: true
    patterns:
      - absolute_filesystem_paths
      - hostnames
      - internal_urls
  client_data:
    enabled: false
    patterns:
      - client_names
      - account_ids
  financial:
    enabled: false
    patterns:
      - dollar_amounts
      - revenue_figures
  proprietary_code:
    enabled: false
    patterns:
      - internal_function_names
      - proprietary_algorithms
---

# REDACT.md

The runtime scrubber in `shiroe/privacy.py` reads these classes before memory
writes and external output. Credentials are always checked even if a project
customizes this file.

When classification is uncertain, halt the write and ask the user how to treat
the content. Never silently persist raw sensitive content.

Related files: `PRIVACY.md` and `SHARING_POLICY.md`.
