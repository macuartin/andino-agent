"""Allow running an agent with: python -m andino agent.yaml"""
from __future__ import annotations

import sys

from andino.service import AgentService


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m andino <agent.yaml>")
        sys.exit(1)
    AgentService.from_yaml(sys.argv[1]).run()


if __name__ == "__main__":
    main()
