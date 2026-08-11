"""Entry point: python -m shiroe <command> [args]."""

import sys
from shiroe.cli import main

if __name__ == "__main__":
    sys.exit(main())
