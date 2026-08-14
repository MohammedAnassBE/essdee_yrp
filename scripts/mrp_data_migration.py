#!/usr/bin/env python3
"""Schema-only planner for the Production API data migration.

This command cannot read or write site data.  Live adapters will be connected
only after the schema plan has no unexplained blockers and the owner explicitly
starts the dry run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from essdee_yrp.migration.planner import (  # noqa: E402
	DEFAULT_SOURCE_ROOT,
	DEFAULT_TARGET_ROOTS,
	build_schema_analysis,
)


def plan_payload(source_root: Path, target_roots: list[Path]) -> dict:
	return build_schema_analysis(source_root=source_root, target_roots=target_roots)[1]


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
	parser.add_argument(
		"--target-root",
		type=Path,
		action="append",
		dest="target_roots",
		help="Repeat for each target app; defaults to yrp + essdee_yrp.",
	)
	parser.add_argument("--output", type=Path, help="Optional JSON report path.")
	parser.add_argument("--summary", action="store_true", help="Print only the summary.")
	args = parser.parse_args()
	payload = plan_payload(args.source_root, args.target_roots or list(DEFAULT_TARGET_ROOTS))
	text = json.dumps(payload, indent=2, sort_keys=True)
	if args.output:
		args.output.parent.mkdir(parents=True, exist_ok=True)
		args.output.write_text(text + "\n")
	if args.summary:
		print(
			json.dumps(
				{
					key: value
					for key, value in payload.items()
					if key not in {"issues", "dependency_groups", "doctype_details"}
				},
				indent=2,
				sort_keys=True,
			)
		)
	else:
		print(text)
	return 0 if payload["ready"] else 2


if __name__ == "__main__":
	raise SystemExit(main())
