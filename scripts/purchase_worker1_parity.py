"""Read-only MRP/ERP parity for purchase cases C1-C4.

Run with either bench's Python; the parent runs fresh processes in both benches.
Only declared doctype renames are normalized. C1's user-approved blank-to-Accepted
default is reported separately from raw equality. Additional supplier-code columns
are checked against the original MRP location codes as well as for visibility.
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

BENCHES = Path("/home/anas/pilot/benches")
DEFAULT_OUT = Path("/home/anas/report-build/port/parity/fix/purchase_worker1")
REPORTS = {
	"C1": "jobwork_issued_items",
	"C2": "non_jobwork_issued_items",
	"C3": "non_grn_received_items",
	"C4": "purchase_order_itemwise",
}
CASES = [
	(f"{case}-{month}", slug, {"from_date": start, "to_date": end})
	for case, slug in REPORTS.items()
	if case != "C4"
	for month, start, end in [
		("sep", "2026-09-01", "2026-09-30"),
		("aug", "2026-08-01", "2026-08-31"),
	]
] + [
	(
		"C4-ordered-day",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-09-21",
			"to_date": "2026-09-21",
			"open_status": "Open",
			"status": "Ordered",
		},
	),
	(
		"C4-closed-sep",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"open_status": "Closed",
		},
	),
	(
		"C4-ordered-sep",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"open_status": "Open",
			"status": "Ordered",
		},
	),
	(
		"C4-closed-aug",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-08-01",
			"to_date": "2026-08-31",
			"open_status": "Closed",
		},
	),
	(
		"C4-ordered-aug",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-08-01",
			"to_date": "2026-08-31",
			"open_status": "Open",
			"status": "Ordered",
		},
	),
	(
		"C4-partial-sep",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"status": "Partially Delivered",
		},
	),
	(
		"C4-delivered-sep",
		REPORTS["C4"],
		{
			"date_based_on": "Posting Date",
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"status": "Delivered",
		},
	),
]


def child(side, out):
	sys.dont_write_bytecode = True
	import frappe

	bench = BENCHES / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	# Enforce source and target read-only behavior at the database boundary.
	frappe.db.sql("START TRANSACTION READ ONLY")
	try:
		for case, slug, filters in CASES:
			module_path = (
				f"production_api.production_api.report.{slug}.{slug}"
				if side == "source"
				else f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}"
			)
			columns, rows = importlib.import_module(module_path).execute(frappe._dict(filters))
			result = {"filters": filters, "columns": columns, "rows": rows}
			if side == "target" and case.startswith("C4"):
				from yrp.web_reports.jobs import run_web_report

				# Prevent the endpoint's unrelated housekeeping job from being enqueued.
				with patch("yrp.web_reports.jobs._enqueue_lazy_cleanup"):
					web = run_web_report("purchase-order-itemwise", dict(filters))
				result["web_columns"] = web["columns"]
				result["web_rows"] = [row for row in web["result"] if row and not row.get("is_total_row")]
			(out / f"{case}-{side}.json").write_text(frappe.as_json(result, indent=2))
	finally:
		frappe.db.rollback()
		frappe.destroy()


def canonical(rows, fields):
	renames = {
		"YRP Stock Entry": "Stock Entry",
		"YRP Work Order": "Work Order",
		"YRP Delivery Challan": "Delivery Challan",
		"SD YRP Finishing Plan": "Finishing Plan",
		"SD YRP Finishing Plan Dispatch": "Finishing Plan Dispatch",
		"YRP Goods Received Note": "Goods Received Note",
	}
	return [
		{
			field: renames.get(row.get(field), row.get(field))
			if field in {"against", "source_doctype"}
			else row.get(field)
			for field in fields
		}
		for row in rows
	]


def compare(source, target, case):
	column_fields = [column["fieldname"] for column in source["columns"]]
	fields = list(dict.fromkeys(column_fields + [key for row in source["rows"] for key in row]))
	left, right = canonical(source["rows"], fields), canonical(target["rows"], fields)
	counts = Counter()
	examples = {}
	for source_row, target_row in zip(left, right, strict=False):
		for field in fields:
			if source_row[field] != target_row[field]:
				counts[field] += 1
				examples.setdefault(field, {"mrp": source_row[field], "erp": target_row[field]})
	result = {
		"case": case,
		"filters": source["filters"],
		"mrp_rows": len(left),
		"erp_rows": len(right),
		"mrp_quantity": sum(row.get("quantity", row.get("qty", 0)) or 0 for row in left),
		"erp_quantity": sum(row.get("quantity", row.get("qty", 0)) or 0 for row in right),
		"full_rows_equal": left == right,
		"differing_cells": dict(counts),
		"examples": examples,
	}
	# Metadata link targets necessarily follow the migration's doctype mapping.
	target_fields = [column["fieldname"] for column in target["columns"]]
	result["column_order_matches"] = column_fields == [
		field for field in target_fields if field in column_fields
	]
	result["nonempty_samples"] = bool(left) and bool(right)

	def approved_received_default(a, b, field):
		return (
			case.startswith("C1")
			and field == "received_type"
			and a[field] in (None, "")
			and b[field] == "Accepted"
		)

	if not case.startswith("C4"):
		pairs = [("from_supplier", "from_location")]
		if case.startswith("C3"):
			pairs.append(("received_supplier", "received_location"))
		result["supplier_columns_visible"] = all(
			field in target_fields for field in ["supplier", *[pair[0] for pair in pairs]]
		)
		result["supplier_codes_equal"] = len(source["rows"]) == len(target["rows"]) and all(
			(a.get(original) or None) == (b.get(added) or None)
			for a, b in zip(source["rows"], target["rows"], strict=False)
			for added, original in pairs
		)
	result["scope_equal"] = (
		len(left) == len(right)
		and result["column_order_matches"]
		and result.get("supplier_columns_visible", True)
		and result.get("supplier_codes_equal", True)
		and all(
			a[field] == b[field] or approved_received_default(a, b, field)
			for a, b in zip(left, right, strict=False)
			for field in fields
		)
	)
	if "web_rows" in target:
		web = canonical(target["web_rows"], fields)
		result["web_rows"] = len(web)
		result["web_matches_desk"] = web == right
		result["web_matches_mrp"] = web == left
		result["scope_equal"] &= result["web_matches_mrp"]
		result["status_filter_equal"] = (
			len(left) == len(right)
			and all(
				{field: row[field] for field in fields if field != "uom"}
				== {field: actual[field] for field in fields if field != "uom"}
				for row, actual in zip(left, right, strict=False)
			)
			and result["web_matches_desk"]
		)
		if counts.get("uom"):
			result["remaining_uom_difference"] = (
				"MRP blank UOMs were defaulted during migration. The target lacks the original blank marker; "
				"the report continues to display the stored UOM."
			)
	return result


def run(out):
	out.mkdir(parents=True, exist_ok=True)
	for side, version in [("source", "frappe-15"), ("target", "frappe-16")]:
		bench = BENCHES / version
		subprocess.run(
			[str(bench / "env/bin/python"), str(Path(__file__).resolve()), "--side", side, "--out", str(out)],
			cwd=bench,
			check=True,
		)
	summary = [
		compare(
			json.loads((out / f"{case}-source.json").read_text()),
			json.loads((out / f"{case}-target.json").read_text()),
			case,
		)
		for case, _slug, _filters in CASES
	]
	(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
	print(json.dumps(summary, indent=2))
	return 0 if all(row["scope_equal"] and row["nonempty_samples"] for row in summary) else 1


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--side", choices=["source", "target"])
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
	args = parser.parse_args()
	if args.side:
		child(args.side, args.out)
	else:
		raise SystemExit(run(args.out))
