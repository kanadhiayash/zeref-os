## Summary

-

## Type

- [ ] feat
- [ ] fix
- [ ] refactor
- [ ] docs
- [ ] test
- [ ] ci
- [ ] chore

## Public surface impact

- [ ] README changed
- [ ] docs changed
- [ ] benchmark wording changed
- [ ] release wording changed
- [ ] no public surface impact

## Security and privacy impact

- [ ] privacy behavior changed
- [ ] security behavior changed
- [ ] no security or privacy impact

## Verification

Paste command outputs:

    python3 -m pytest -q
    python3 scripts/shiroe-validate.py
    python3 -m shiroe audit
    python3 -m shiroe audit-privacy --strict
    python3 scripts/check-version-consistency.py
    git diff --check

## Risks

-

## Rollback

-
