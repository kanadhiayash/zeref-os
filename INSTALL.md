<!-- privacy-audit: allow-file "Install doc with example commands. No real credentials." -->

# Install Shiroe

## Python Runtime

```bash
git clone https://github.com/kanadhiayash/shiroe.git
cd shiroe
python3 -m pip install -e .
python3 -m shiroe --help
```

## Project Setup

```bash
python3 -m shiroe init /path/to/project --name "My Project" --privacy abstract --network-scope device-only
cd /path/to/project
python3 -m shiroe status --json
python3 -m shiroe doctor --json
```

`init` creates current runtime config, privacy policy files, `.shiroe/policy/`,
canonical SQLite state, and event-log directories. It does not install or
enable connectors.

## Harness Shims

Use `AGENTS.md` as the canonical instruction file. Optional shims are included
for hosts that expect host-specific files:

- `CLAUDE.md`
- `CODEX.md`
- `GEMINI.md`
- `LLAMA.md`
- `.cursor/rules/shiroe.mdc`
- `.windsurfrules`
- `.aider.conf.yml.example`

Each shim points back to the same runtime boot sequence and does not change
authority.

## Verify

```bash
python3 -m shiroe version
python3 -m shiroe doctor --json
python3 -m shiroe state verify --json
```

## Remove

Remove the checkout or installed package with your normal Python environment
tooling. Project state under a user project remains local until the user
deletes it.
