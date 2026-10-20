#!/usr/bin/env python3
"""One-off MRP Version backfill; dry-run by default, never writes to the source.

Run with the target bench's env/bin/python. Example:
  env/bin/python apps/essdee_yrp/scripts/backfill_finishing_plan_status_since.py \
    --source-bench /path/to/frappe-15 --source-site mrp.site \
    --target-bench /path/to/frappe-16 --target-site erp.site --apply

Existing timestamps are preserved, as are plans whose ERP status has changed
since migration. Run after the target has migrated the fp_status_since field.
This is intentionally a standalone operation, not a Frappe migration patch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from essdee_yrp.migration.transformers import find_finishing_plan_status_since


def plan_backfill(targets, history):
	"""Build an idempotent update list without inventing dates or overwriting live changes."""
	by_name = {row["name"]: row for row in history}
	counts = dict(
		source_plans=len(by_name),
		source_versions=sum(len(row.get("versions") or []) for row in history),
		target_plans=0,
		to_update=0,
		updated=0,
		unchanged=0,
		existing_preserved=0,
		source_missing=0,
		status_mismatch=0,
		no_matching_history=0,
		concurrent_change=0,
	)
	updates = []
	for target in targets:
		counts["target_plans"] += 1
		source = by_name.get(target["name"])
		if not source:
			counts["source_missing"] += 1
			continue
		source_status = source.get("fp_status")
		expected_status = "Ready for Audit" if source_status == "OCR Requested" else source_status
		if target.get("fp_status") != expected_status:
			counts["status_mismatch"] += 1
			continue
		since = find_finishing_plan_status_since(source["name"], source_status, source.get("versions"))
		if not since:
			counts["no_matching_history"] += 1
			continue
		if target.get("fp_status_since"):
			key = "unchanged" if str(target["fp_status_since"]) == since else "existing_preserved"
			counts[key] += 1
			continue
		updates.append({"name": target["name"], "fp_status": expected_status, "fp_status_since": since})
	counts["to_update"] = len(updates)
	return updates, counts


def main():
	parser = argparse.ArgumentParser(
		description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
	)
	parser.add_argument("--source-bench", type=Path, required=True)
	parser.add_argument("--source-site", required=True)
	parser.add_argument("--target-bench", type=Path, required=True)
	parser.add_argument("--target-site", required=True)
	parser.add_argument(
		"--apply", action="store_true", help="Commit target updates (default only reports counts)"
	)
	args = parser.parse_args()
	for site in (args.source_site, args.target_site):
		if not re.fullmatch(r"[A-Za-z0-9_.-]+", site):
			parser.error("Site names must be plain names without directory separators")
	source_bench, target_bench = args.source_bench.resolve(), args.target_bench.resolve()
	if (source_bench, args.source_site) == (target_bench, args.target_site):
		parser.error("Source and target must be different sites")
	bridge = Path(__file__).resolve().with_name("f15_source_bridge.py")
	result = subprocess.run(
		[
			str(source_bench / "env/bin/python"),
			str(bridge),
			"--source-bench",
			str(source_bench),
			"--source-site",
			args.source_site,
			"finishing-plan-status-history",
		],
		check=True,
		text=True,
		capture_output=True,
	)
	history = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
	if any(row.get("kind") != "finishing_plan_status_history" for row in history):
		raise RuntimeError("Unexpected source history payload; no target writes were attempted")
	if not history:
		raise RuntimeError("Source returned no Finishing Plans; no target writes were attempted")

	import frappe

	os.chdir(target_bench / "sites")
	frappe.init(site=args.target_site, sites_path=str(target_bench / "sites"))
	frappe.connect()
	try:
		if not frappe.get_meta("SD YRP Finishing Plan").has_field("fp_status_since"):
			raise RuntimeError("Migrate the target fp_status_since field before running this script")
		targets = frappe.get_all(
			"SD YRP Finishing Plan", fields=["name", "fp_status", "fp_status_since"], limit_page_length=0
		)
		updates, counts = plan_backfill(targets, history)
		if args.apply:
			for update in updates:
				# Lock and recheck so a concurrently changed plan keeps its live timestamp.
				current = frappe.db.sql(
					"SELECT fp_status, fp_status_since FROM `tabSD YRP Finishing Plan` WHERE name=%s FOR UPDATE",
					update["name"],
					as_dict=True,
				)
				if not current or current[0].fp_status != update["fp_status"] or current[0].fp_status_since:
					counts["concurrent_change"] += 1
					continue
				frappe.db.set_value(
					"SD YRP Finishing Plan",
					update["name"],
					"fp_status_since",
					update["fp_status_since"],
					update_modified=False,
				)
				counts["updated"] += 1
			frappe.db.commit()
		else:
			frappe.db.rollback()
		print(
			json.dumps(
				{
					"apply": args.apply,
					"source_site": args.source_site,
					"target_site": args.target_site,
					**counts,
				},
				sort_keys=True,
			)
		)
	except BaseException:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
