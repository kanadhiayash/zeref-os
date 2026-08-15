# Installation

Current release: `shiroe@shiroe v3.0.0-alpha.1` (canonical source:
`shiroe/VERSION`). Shiroe requires Python 3.11 or newer and has no mandatory
runtime dependency.

## From source

```bash
git clone https://github.com/kanadhiayash/shiroe.git
cd shiroe
python3 -m pip install -e .
python3 -m shiroe --help
```

## Initialize a project

```bash
python3 -m shiroe init /path/to/project --name my-project --privacy abstract
cd /path/to/project
python3 -m shiroe status --json
```

`init` creates local configuration, privacy files, canonical state directories,
and append-only event-log directories. It does not enable connectors.

## Verify the runtime

```bash
python3 -m compileall -q shiroe
python3 -m pytest -q
python3 -m shiroe doctor --json
python3 -m shiroe version
```

The supported CLI surface is the one shown by:

```bash
python3 -m shiroe --help
```

## Project lifecycle smoke

```bash
TMP="$(mktemp -d)"
python3 -m shiroe init "$TMP" --name smoke --privacy abstract
cd "$TMP"
python3 -m shiroe status --json
```

For source-tree development from another working directory, install the package
editable or set `PYTHONPATH` to the repository root.

## Uninstall

Uninstall the Python package with your package manager. Project memory and
configuration remain in the project directory until you remove them yourself.

## Related

- [[Architecture]]
- [[Memory-Model]]
- [[Privacy-Model]]
- [[FAQ]]
