# Trust and rights registry (SHR-077..080)

This repository imports two kinds of third-party surface into what it
publishes: **imported references** (URLs cited from `README.md` and the
root spec files) and **public visuals** (images and vector art committed
under `assets/`). Every one of them must have an approved source and a
rights status recorded before it can appear in a released tree.

The record lives in `docs/canon/TRUST_REGISTRY.json`. The check that
enforces it is `scripts/check-trust-registry.py`, wired into the per-PR
gate.

## Why this exists

Two failure modes are cheap to fall into and expensive to recover from:

- Shipping a visual whose license was never verified.
- Citing a page whose owner changed the URL or the content behind it.

Both stay silent until someone looks. The trust registry makes silence
impossible: an added visual or a new URL that lacks a matching entry
fails the gate on the same PR that introduced it.

## The two coverage walks

**Public visuals.** Every file under `assets/` with a raster or vector
extension (`.png .svg .jpg .jpeg .gif .webp`) must match a
`public_visuals[]` entry keyed by `path` (repo-relative POSIX). The
`assets/archive/` subtree is deliberately excluded — it holds historical
snapshots that `assets/README.md` marks as not-the-current-brand-kit.

**Imported references.** Every `http(s)://…` URL that appears in
`README.md`, `SOUL.md`, `PRIVACY.md`, `REDACT.md`, `SHARING_POLICY.md`,
or `AGENTS.md` must match at least one `imported_references[].url_pattern`
(anchored Python regex). Patterns beat one-URL-per-entry because badges
and self-links accumulate — one shields.io row covers every current
and future badge in the same domain.

## Rights statuses

| Status | Meaning |
|---|---|
| `owned_project` | Authored inside this project; the project holds all rights. |
| `self_owned` | Points at another surface of this same project (self-links, self-issues, self-CI). |
| `public_service` | Public API or generator whose terms allow use without attribution — badges, redirectors. |
| `licensed_third_party` | Third-party content used under a license that requires attribution; the license itself must be captured in `approved_source` or `notes`. |
| `public_domain` | Not covered by copyright, or dedicated to the public domain. |

## Adding an entry

1. Land the new visual or the new URL as usual.
2. Run the gate — it will fail loudly with the offending path or URL.
3. Add an entry to `docs/canon/TRUST_REGISTRY.json` with an
   `approved_source`, a `rights_status` from the enum, a real
   `approved_by` handle, and today's ISO date in `approved_at`. For a
   URL, prefer a regex that covers a class of URLs, not one row per
   link.
4. Re-run the gate. It must pass silently.

## Relationship to other surfaces

`docs/canon/SOURCE_AUTHORITY.md` decides **which surface wins** when
they disagree. The trust registry answers a different question: **is
what any surface is showing allowed to be shown at all**. Neither
supersedes the other; they are consulted in different situations.
