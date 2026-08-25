"""Development and packaged entry point for Power Systems Costing Workbook."""

from __future__ import annotations

import argparse
from pathlib import Path

from erics_quoter.ui import QuoterApp


def main() -> None:
    parser = argparse.ArgumentParser(description="GDI Ainsworth costing workbook generator")
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="Capture the rendered app window and exit (visual QA helper).",
    )
    args = parser.parse_args()

    app = QuoterApp(screenshot_path=args.screenshot)
    app.mainloop()


if __name__ == "__main__":
    main()
