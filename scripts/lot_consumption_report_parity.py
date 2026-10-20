"""Read-only, ordered MRP/ERP parity for the two Lot Consumption filter sets.

Run with the F16 bench Python; each export uses its site's own bench Python.
Only migrated DocType names are normalized. Voucher references, quantities,
warehouses, column definitions and row order must all match.
"""

import argparse
import datetime
import decimal
import importlib
import json
import os
import subprocess
from pathlib import Path

CASES = [
	("C1_a", dict(lot="C0925-57/1", start_date="2026-08-01", end_date="2026-09-30", item_group="Purchase")),
	("C1_b", dict(lot="JB2627-015", start_date="2026-08-01", end_date="2026-09-30", item_group="Products")),
]
VOUCHER_FIELDS = ("stock_ledger_entry", "voucher_type", "voucher_no", "from_warehouse", "to_warehouse")
DOCTYPE_MAP = {
	"Stock Ledger Entry": "YRP Stock Ledger Entry",
	"Lot": "SD YRP Lot",
	"Item Variant": "Item",
	"Stock Entry": "YRP Stock Entry",
	"Lot Transfer": "SD YRP Lot Transfer",
	"Delivery Challan": "YRP Delivery Challan",
	"Goods Received Note": "YRP Goods Received Note",
}


def json_default(value):
	if isinstance(value, decimal.Decimal):
		return float(value)
	if isinstance(value, (datetime.date, datetime.datetime)):
		return value.isoformat()
	raise TypeError(f"Cannot serialize {type(value).__name__}")


def write(path, value):
	path.write_text(json.dumps(value, default=json_default, indent=2, ensure_ascii=False) + "\n")


def normalize(value, key=None):
	if isinstance(value, dict):
		return {k: normalize(v, k) for k, v in value.items()}
	if isinstance(value, list):
		return [normalize(v) for v in value]
	if key in ("options", "voucher_type") and isinstance(value, str):
		return DOCTYPE_MAP.get(value, value)
	return value


def export(side, output):
	import frappe

	bench = Path("/home/anas/pilot/benches") / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.db.sql("SET TRANSACTION READ ONLY")
	try:
		module = importlib.import_module(
			"production_api.mrp_stock.report.lot_consumption_report.lot_consumption_report"
			if side == "source"
			else "essdee_yrp.essdee_yrp.report.sd_yrp_lot_consumption_report.sd_yrp_lot_consumption_report"
		)
		for case, filters in CASES:
			columns, rows, *extras = module.execute(frappe._dict(filters))
			write(output / f"{case}.{side}.json", dict(filters=filters, columns=columns, rows=rows, extras=extras))
	finally:
		frappe.db.rollback()
		frappe.destroy()


def compare_case(case, source, target):
	source, target = normalize(source), normalize(target)
	left, right = source["rows"], target["rows"]
	return dict(
		case=case,
		filters=source["filters"],
		source_rows=len(left),
		target_rows=len(right),
		rows_equal=left == right,
		columns_equal=source["columns"] == target["columns"],
		extras_equal=source["extras"] == target["extras"],
		different_voucher_rows=sum(
			any(a.get(k) != b.get(k) for k in VOUCHER_FIELDS)
			for a, b in zip(left, right)
		) + abs(len(left) - len(right)),
		first_differences=[
			dict(index=i, mrp=a, erp=b)
			for i, (a, b) in enumerate(zip(left, right))
			if a != b
		][:3],
	)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--export", choices=["source", "target"])
	parser.add_argument("--compare-only", action="store_true")
	parser.add_argument("--output", type=Path, default=Path("/home/anas/report-build/fix15/round3_c/after"))
	args = parser.parse_args()
	output = args.output.resolve()
	output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, output)
		return
	if not args.compare_only:
		for side, bench in [("source", "frappe-15"), ("target", "frappe-16")]:
			subprocess.run([
				f"/home/anas/pilot/benches/{bench}/env/bin/python", str(Path(__file__).resolve()),
				"--export", side, "--output", str(output),
			], check=True)
	summary = [compare_case(
		case,
		json.loads((output / f"{case}.source.json").read_text()),
		json.loads((output / f"{case}.target.json").read_text()),
	) for case, _filters in CASES]
	write(output / "summary.json", summary)
	print(json.dumps(summary, indent=2))
	raise SystemExit(0 if all(r["rows_equal"] and r["columns_equal"] and r["extras_equal"] for r in summary) else 1)


if __name__ == "__main__":
	main()
