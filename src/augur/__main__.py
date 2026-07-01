"""Enable ``python -m augur`` in addition to the ``augur`` console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
