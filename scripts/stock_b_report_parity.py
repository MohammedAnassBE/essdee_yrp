"""Compare Stock B reports against the read-only MRP snapshot."""

import argparse
import json
import subprocess
from pathlib import Path

CASES = {
	"stock_entry_report": [
		{"from_date": "2026-09-01", "to_date": "2026-09-01"},
		{
			"from_date": "2026-09-01",
			"to_date": "2026-09-07",
			"lot": "JB2627-015",
			"item": "535473 - LADIES CREAM XMAS DOGS AOP B",
			"from_warehouse": "S-0164",
			"to_warehouse": "S-0170",
		},
	],
	"stock_item_balance_difference": [
		{
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"warehouse": "S-0005",
			"lot": "F0826-21 W D/N 1",
		},
		{
			"from_date": "2026-08-01",
			"to_date": "2026-08-31",
			"parent_item": "Thermal Fabric",
			"warehouse": "S-0005",
			"remove_zero_diff": 1,
		},
	],
	"stock_reconciliation_report": [
		{"from_date": "2026-09-01", "to_date": "2026-09-30"},
		{
			"from_date": "2026-08-01",
			"to_date": "2026-09-30",
			"supplier": "S-0005",
			"item": "Thermal Fabric",
			"lot": "F0826-21 W D/N 1",
		},
	],
	"stock_update_report": [
		{"from_date": "2026-09-01", "to_date": "2026-09-30"},
		{
			"from_date": "2026-08-01",
			"to_date": "2026-09-30",
			"lot": "F0726-99",
			"item_variant": "Single Jersey Fabric-Black-76 Dia",
		},
	],
}

RUNNER = r"""
import importlib, json, sys, traceback
import frappe
site, side, cases_json = sys.argv[1:]
frappe.init(site=site)
frappe.connect()
frappe.db.sql("SET SESSION TRANSACTION READ ONLY")
results = {}
try:
	for report, cases in json.loads(cases_json).items():
		prefix = "production_api.mrp_stock.report." if side == "source" else "essdee_yrp.essdee_yrp.report."
		module_name = report if side == "source" else "sd_yrp_" + report
		results[report] = []
		for filters in cases:
			try:
				module = importlib.import_module(prefix + module_name + "." + module_name)
				result = module.execute(dict(filters))
				results[report].append({"filters": filters, "columns": result[0], "rows": result[1]})
			except Exception:
				results[report].append({"filters": filters, "error": traceback.format_exc()})
finally:
	frappe.db.rollback()
	frappe.destroy()
print("STOCK_B_JSON=" + json.dumps(results, default=str))
"""


def normalize(value):
	if isinstance(value, dict):
		return {key: normalize(val) for key, val in sorted(value.items())}
	if isinstance(value, list):
		return [normalize(val) for val in value]
	if isinstance(value, (int, float)):
		return round(value, 6)
	return value


def normalized_columns(columns, report):
	mapping = {
		"Item Variant": "Item",
		"Lot": "SD YRP Lot",
		"GRN Item Type": "YRP Received Type",
		"Stock Entry": "YRP Stock Entry",
		"Stock Reconciliation": "YRP Stock Reconciliation",
		"Stock Update": "YRP Stock Update",
	}
	if report != "stock_reconciliation_report":
		mapping["Supplier"] = "Warehouse"
	return [
		{
			**column,
			**({"options": mapping.get(column["options"], column["options"])} if "options" in column else {}),
		}
		for column in columns
	]


def snapshot(bench, site, side):
	result = subprocess.run(
		[str(bench / "env/bin/python"), "-c", RUNNER, site, side, json.dumps(CASES)],
		cwd=bench / "sites",
		capture_output=True,
		text=True,
		check=True,
	)
	return json.loads(result.stdout.split("STOCK_B_JSON=", 1)[1])


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--output", type=Path, default=Path("/home/anas/report-build/port/parity/stock_b"))
	args = parser.parse_args()
	args.output.mkdir(parents=True, exist_ok=True)
	source = snapshot(Path("/home/anas/pilot/benches/frappe-15"), "mrp3.site", "source")
	target = snapshot(Path("/home/anas/pilot/benches/frappe-16"), "erp-migration-test.site", "target")
	summary = []
	for report, cases in CASES.items():
		for index, filters in enumerate(cases):
			left, right = source[report][index], target[report][index]
			for side, payload in (("source", left), ("target", right)):
				(args.output / f"{report}_{index + 1}_{side}.json").write_text(
					json.dumps(payload, indent=2) + "\n"
				)
			left_rows = sorted(
				[normalize(row) for row in left.get("rows", [])],
				key=lambda row: json.dumps(row, sort_keys=True),
			)
			right_rows = sorted(
				[normalize(row) for row in right.get("rows", [])],
				key=lambda row: json.dumps(row, sort_keys=True),
			)
			entry = {
				"report": report,
				"case": index + 1,
				"filters": filters,
				"source_rows": len(left_rows),
				"target_rows": len(right_rows),
				"equal": "error" not in left and "error" not in right and left_rows == right_rows,
				"columns_equal": normalized_columns(left.get("columns", []), report)
				== right.get("columns", []),
			}
			if "error" in left or "error" in right:
				entry["errors"] = {
					side: payload["error"]
					for side, payload in (("source", left), ("target", right))
					if "error" in payload
				}
			if not entry["equal"] and "errors" not in entry:
				entry["source_only"] = [row for row in left_rows if row not in right_rows][:3]
				entry["target_only"] = [row for row in right_rows if row not in left_rows][:3]
			summary.append(entry)
	(args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
	print(json.dumps(summary, indent=2))
	return 0 if all(row["equal"] and row["columns_equal"] for row in summary) else 1


if __name__ == "__main__":
	raise SystemExit(main())
