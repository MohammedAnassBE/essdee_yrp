"""Run worker 3's read-only source/target report comparisons.

Run with the F16 bench Python. Child processes use each bench's own Python and
site. Normalisation compares every displayed column (including missing values),
rounds numeric values to six decimals, maps renamed doctypes, and ignores row
order. Full unmodified report rows and filters are retained alongside results.
"""

import argparse
import importlib
import json
import signal
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

BENCHES = {
	"source": Path("/home/anas/pilot/benches/frappe-15"),
	"target": Path("/home/anas/pilot/benches/frappe-16"),
}
SITES = {"source": "mrp3.site", "target": "erp-migration-test.site"}
CASES = {
	"stock_ledger": [
		{
			"from_date": "2026-09-01",
			"to_date": "2026-09-21",
			"warehouse": "S-0167",
			"parent_item": "ESSDEE GYM VEST",
		},
		{
			"from_date": "2026-08-01",
			"to_date": "2026-08-31",
			"warehouse": "S-0167",
			"item": "ESSDEE GYM VEST-90 cm",
			"received_type": "Accepted",
		},
	],
	"reserved_stock": [
		{
			"from_date": "2026-09-01",
			"to_date": "2026-09-21",
			"brand": "",
			"voucher_type": "Packing Slip",
			"warehouse": "S-0167",
		},
		{
			"from_date": "2026-08-01",
			"to_date": "2026-09-21",
			"brand": "",
			"voucher_type": "Packing Slip",
			"item_code": "T56203 Little Paws Shorts Set Half Sleeve-XL",
		},
		{
			"from_date": "2026-09-01",
			"to_date": "2026-09-21",
			"voucher_type": "Packing Slip",
			"warehouse": "S-0167",
		},
	],
	"fg_stock_with_lot": [
		{"filter_date": "2026-09-21", "warehouse": "S-0167"},
		{"filter_date": "2026-08-31", "warehouse": "S-0169"},
	],
	"lot_profit_comparison": [
		{"from_date": "2026-06-01", "to_date": "2026-09-21", "item": "JUNIOR GYM VEST"},
		{"from_date": "2026-01-01", "to_date": "2026-09-21", "lot": "F1225-33"},
	],
}
RENAMES = {
	"YRP Stock Entry": "Stock Entry",
	"YRP Stock Reconciliation": "Stock Reconciliation",
	"YRP Work Order": "Work Order",
	"YRP Goods Received Note": "Goods Received Note",
	"SD YRP FG Stock Entry": "FG Stock Entry",
	"SD YRP Packing Slip": "Packing Slip",
}


COLUMN_RENAMES = {
	"SD YRP Lot": "Lot",
	"YRP Received Type": "GRN Item Type",
	"YRP Stock Reservation Entry": "Stock Reservation Entry",
	"SD YRP FG Item Master": "FG Item Master",
	"Item Variant": "Item",
}


def normalized_columns(columns):
	return [
		{**column, "options": COLUMN_RENAMES.get(column.get("options"), column.get("options"))}
		for column in columns
	]


def normalized(columns, rows):
	fields = list(dict.fromkeys(column["fieldname"] for column in columns))

	def value(v):
		if isinstance(v, (int, float, Decimal)):
			return round(float(v), 6)
		return RENAMES.get(v, v) if isinstance(v, str) else v

	return sorted(
		json.dumps({field: value(row.get(field)) for field in fields}, sort_keys=True, default=str)
		for row in rows
	)


def child(side, slug, index, output, fg_stock_core=False):
	import frappe

	frappe.init(site=SITES[side], sites_path=str(BENCHES[side] / "sites"))
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("SET SESSION TRANSACTION READ ONLY")
	filters = dict(CASES[slug][index])
	package = (
		f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}"
		if side == "target"
		else f"production_api.{'product_development' if slug == 'lot_profit_comparison' else 'mrp_stock'}.report.{slug}.{slug}"
	)
	payload = {"side": side, "report": slug, "filters": filters}

	def timeout(*_args):
		raise TimeoutError("Report exceeded 180 seconds")

	signal.signal(signal.SIGALRM, timeout)
	signal.alarm(180)
	try:
		module = importlib.import_module(package)
		if fg_stock_core:
			rows = module.get_stock(frappe._dict(filters))
			columns = [
				{"fieldname": field}
				for field in ("lot", "stock", "item", "item_variant", "warehouse_name", "warehouse")
			]
			payload["scope"] = (
				"Local FG stock balances only; excludes external pricing and legacy allocations"
			)
		else:
			columns, rows = module.execute(frappe._dict(filters))[:2]
		payload.update(columns=columns, rows=rows, normalized=normalized(columns, rows), row_count=len(rows))
	except Exception as exc:
		# Avoid serialising API URLs, connection details, or credentials in errors.
		payload["error"] = type(exc).__name__
		if isinstance(exc, frappe.ValidationError):
			payload["message"] = str(exc)
	finally:
		signal.alarm(0)
		frappe.db.rollback()
		frappe.destroy()
	Path(output).write_text(json.dumps(payload, indent=2, default=str) + "\n")


def run(output, only_report=None, compare_only=False, fg_stock_core=False):
	output.mkdir(parents=True, exist_ok=True)
	summary = []
	for slug, cases in CASES.items():
		if only_report and slug != only_report:
			continue
		for index in range(len(cases)):
			results = {}
			for side, bench in BENCHES.items():
				path = output / f"{slug}_{index + 1}_{side}.json"
				if not compare_only:
					process = subprocess.run(
						[
							str(bench / "env/bin/python"),
							str(Path(__file__).resolve()),
							*(["--fg-stock-core"] if fg_stock_core else []),
							"--child",
							side,
							"--report",
							slug,
							"--case",
							str(index),
							"--output",
							str(path),
						],
						cwd=bench / "sites",
						capture_output=True,
						text=True,
						timeout=210,
					)
					if process.returncode:
						path.write_text(
							json.dumps({"error": "child process failed", "exit_code": process.returncode})
						)
				results[side] = json.loads(path.read_text())
			source, target = results["source"], results["target"]
			equal = (
				source.get("normalized") == target.get("normalized")
				if "normalized" in source and "normalized" in target
				else None
			)
			case = {
				"report": slug,
				"case": index + 1,
				"rows_equal": equal,
				"columns_equal": normalized_columns(source["columns"])
				== normalized_columns(target["columns"])
				if "columns" in source and "columns" in target
				else None,
				"source_rows": source.get("row_count"),
				"target_rows": target.get("row_count"),
				"source_error": source.get("error"),
				"target_error": target.get("error"),
			}
			if equal is False:
				a, b = Counter(source["normalized"]), Counter(target["normalized"])
				case.update(
					source_only=list((a - b).elements())[:5], target_only=list((b - a).elements())[:5]
				)
			summary.append(case)
			print(json.dumps(case), flush=True)
	summary_path = output / "summary.json"
	if only_report and summary_path.exists():
		previous = json.loads(summary_path.read_text())
		retained = [case for case in previous if case["report"] != only_report]
	else:
		retained = []
	summary_path.write_text(json.dumps(retained + summary, indent=2) + "\n")
	return (
		0
		if all(
			case["rows_equal"] is True
			and case["columns_equal"] is True
			and not case["source_error"]
			and not case["target_error"]
			for case in summary
		)
		else 1
	)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--compare-only", action="store_true", help="Compare saved outputs without running either site"
	)
	parser.add_argument(
		"--fg-stock-core", action="store_true", help="Compare local FG balances without external services"
	)
	parser.add_argument("--child", choices=BENCHES)
	parser.add_argument("--report", choices=CASES)
	parser.add_argument("--case", type=int)
	parser.add_argument("--output", default="/home/anas/report-build/port/parity/worker3")
	args = parser.parse_args()
	if args.child:
		child(args.child, args.report, args.case, args.output, args.fg_stock_core)
	else:
		output = Path(args.output) / "fg_stock_core" if args.fg_stock_core else Path(args.output)
		raise SystemExit(
			run(
				output,
				"fg_stock_with_lot" if args.fg_stock_core else args.report,
				args.compare_only,
				args.fg_stock_core,
			)
		)
