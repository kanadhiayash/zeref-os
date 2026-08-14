<!-- privacy-audit: allow-file "Install doc. Documents env-var-shaped tokens (OPENAI_API_KEY, GITHUB_TOKEN) as example config strings. No real credentials." -->

# Install Shiroe

## Claude Code (CLI)

```bash
claude plugin marketplace add kanadhiayash/shiroe
claude plugin install shiroe@shiroe
```

Restart Claude Code. Skills surface as `shiroe:<skill-name>` via the Skill tool. Commands as `/shiroe:<command>`.

## Codex / Gemini CLI / Antigravity / Hermes / Amp / Zed / Perplexity Computer

These harnesses read `AGENTS.md` natively.

1. Clone the repo into your project:
   ```bash
   git clone https://github.com/kanadhiayash/shiroe.git .shiroe
   ```
2. Point your harness at `.shiroe/AGENTS.md` as the canonical agent spec.
3. (Optional) Symlink the relevant harness stub to your project root:
   - Gemini → `.shiroe/GEMINI.md`
   - Claude → `.shiroe/CLAUDE.md`

## Cursor

```bash
git clone https://github.com/kanadhiayash/shiroe.git .shiroe
mkdir -p .cursor/rules
cp .shiroe/.cursor/rules/shiroe.mdc .cursor/rules/
```

Cursor auto-loads `.cursor/rules/shiroe.mdc` which points to `.shiroe/AGENTS.md`.

## Windsurf

```bash
git clone https://github.com/kanadhiayash/shiroe.git .shiroe
cp .shiroe/.windsurfrules .
```

Windsurf auto-loads `.windsurfrules` at project root.

## Aider

```bash
git clone https://github.com/kanadhiayash/shiroe.git .shiroe
cp .shiroe/.aider.conf.yml.example .aider.conf.yml
# Edit .aider.conf.yml as needed
```

Aider reads `AGENTS.md` natively and `.aider.conf.yml` for harness-specific behavior.

## First-time setup (any harness)

In any new project:
```
/shiroe:start
```
(or just `/start` if your harness namespaces slash commands automatically).

This triggers the `project-setup` interview. ~5 min. Writes:
- `config/PROJECT.md`
- `PRIVACY.md` (root)
- `REDACT.md` (root)
- `SHARING_POLICY.md` (root)
- `config/PERMISSIONS.md`
- `config/PARENT_SYNC.md`
- `config/BUDGET.md`

Re-run `/shiroe:start` after to boot the session. Default privacy mode is **abstract**; default connectors are **all OFF**.

## Verify

```bash
python3 .shiroe/scripts/shiroe-validate.py
```

Expect output like the following (exact rows are derived from the tree at
run time):

```
Shiroe validator — /path/to/your/project
Contract dirs:    absent
Config:           5/5
Root privacy:     3/3 (PRIVACY, REDACT, SHARING_POLICY)
Harness stubs:    3/3
Memory layout:    flat
PATTERNS lint:    0 finding(s)
✔ Validation passed
```

For the installed Python runtime (once `pip install -e .` has run):

```bash
python3 -m shiroe doctor --json
python3 -m shiroe version --json
```

## Checking install freshness

If commands seem out of date after an update, confirm what's actually
installed:

```bash
python3 -m shiroe version --json
```

If the reported version doesn't match the latest tag on the source repo,
your harness is serving a cached copy — reinstall the plugin to refresh it.

## Uninstall

```bash
claude plugin uninstall shiroe@shiroe
claude plugin marketplace remove shiroe
```

Your `memory/` directory is local data — preserved unless you delete it.
