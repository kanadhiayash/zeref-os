# Doctor

`shiroe doctor` reports local installation and project health.

It checks:

- canonical state opens and migrates
- event hash chain verifies
- policy stack parses
- policy default-deny behavior denies an unapproved network probe
- privacy redaction removes representative sensitive text
- capability store opens
- adapters report healthy
- current schema version is applied
- legacy scaffold paths are absent

Doctor checks are local-only and do not send project data anywhere.
