from __future__ import annotations

from wanzhi.core.config import load_config
from wanzhi.ui.app import run


def main() -> None:
    run(load_config())


if __name__ == "__main__":
    main()
