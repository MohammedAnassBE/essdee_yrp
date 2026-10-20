"""Compare Stock A Desk ports with the read-only MRP snapshot.

Run with the F16 bench Python. Each export uses its own bench Python and site.
"""

import argparse
import datetime
import decimal
import importlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from unittest.mock import patch

CASES = [
	("C1_a", "item_balance", {"lot": "C0925-57/1", "remove_zero_balance_item": 1}),
	(
		"C1_b",
		"item_balance",
		{
			"lot": "JB2627-015",
			"item": "535473 - LADIES CREAM XMAS DOGS AOP B",
			"warehouse": "S-0172",
			"received_type": "Accepted",
			"remove_zero_balance_item": 0,
		},
	),
	("C2_a", "item_conversion_report", {"from_date": "2026-09-01", "to_date": "2026-09-30"}),
	(
		"C2_b",
		"item_conversion_report",
		{
			"from_date": "2026-08-01",
			"to_date": "2026-09-30",
			"lot": "C0925-69",
			"from_item": "Tencel Siro Fabric",
			"to_item": "Tencel Roma Gold Fabric New",
		},
	),
	(
		"C3_a",
		"lot_consumption_report",
		{"lot": "C0925-57/1", "start_date": "2026-08-01", "end_date": "2026-09-30", "item_group": "Purchase"},
	),
	(
		"C3_b",
		"lot_consumption_report",
		{"lot": "JB2627-015", "start_date": "2026-08-01", "end_date": "2026-09-30", "item_group": "Products"},
	),
	(
		"C4_a",
		"lot_wise_stock_ageing",
		{
			"lot": "C0925-57/1",
			"to_date": "2026-09-30",
			"range1": 30,
			"range2": 60,
			"range3": 90,
			"show_warehouse_wise_stock": 0,
		},
	),
	(
		"C4_b",
		"lot_wise_stock_ageing",
		{
			"lot": "JB2627-015",
			"to_date": "2026-09-30",
			"range1": 30,
			"range2": 60,
			"range3": 90,
			"show_warehouse_wise_stock": 1,
			"warehouse": "S-0172",
			"parent_item": "535473 - LADIES CREAM XMAS DOGS AOP B",
		},
	),
]

DOCTYPE_MAP = {
	"Item Variant": "Item",
	"Lot": "SD YRP Lot",
	"GRN Item Type": "YRP Received Type",
	"Stock Ledger Entry": "YRP Stock Ledger Entry",
	"Item Conversion": "SD YRP Item Conversion",
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
	return str(value)


def write_json(path, value):
	path.write_text(json.dumps(value, default=json_default, indent=2, ensure_ascii=False) + "\n")


def export(side, output, selected):
	import frappe

	bench = Path("/home/anas/pilot/benches") / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.db.sql("SET TRANSACTION READ ONLY")
	try:
		names = [
			"Bottom Box 310mm X 215mm X65mm",
			"EE - 45204 Girls Capri Poster",
			"EE - 45204 Girls Capri Top Box",
			"Essdee Tag - Junior Girls ( Everyday Essentials)",
			"Printed Bopp Junior Small-Pink (65 Mic)",
			"Tag Bullet",
		]
		write_json(
			output / f"environment.{side}.json",
			{
				"site": frappe.local.site,
				"bin_report_roles": [
					row.role
					for row in frappe.get_meta("Bin" if side == "source" else "YRP Bin").permissions
					if row.report
				],
				"item_masters": frappe.get_all(
					"Item", filters={"name": ["in", names]}, fields=["name", "item_group", "brand"]
				),
				"settings": {
					"float_precision": frappe.db.get_single_value("System Settings", "float_precision"),
					"rounding_method": frappe.get_system_settings("rounding_method"),
				},
			},
		)
		for case, slug, filters in CASES:
			if selected and case not in selected:
				continue
			module_path = (
				f"production_api.mrp_stock.report.{slug}.{slug}"
				if side == "source"
				else f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}"
			)
			try:
				result = importlib.import_module(module_path).execute(frappe._dict(filters))
				value = {
					"site": frappe.local.site,
					"filters": filters,
					"columns": result[0],
					"rows": result[1],
					"extras": list(result[2:]),
					"settings": {
						"float_precision": frappe.db.get_single_value(
							"System Settings", "float_precision", cache=True
						),
						"rounding_method": frappe.get_system_settings("rounding_method"),
					},
				}
			except Exception:
				import traceback

				value = {"site": frappe.local.site, "filters": filters, "error": traceback.format_exc()}
			if side == "target" and slug == "lot_wise_stock_ageing" and not value.get("error"):
				source = json.loads((output / f"{case}.source.json").read_text())
				precision = source["settings"]["float_precision"]
				get_single_value = frappe.db.get_single_value
				get_system_settings = frappe.get_system_settings

				def aligned_setting(doctype, fieldname, *args, **kwargs):
					if (doctype, fieldname) == ("System Settings", "float_precision"):
						return precision
					return get_single_value(doctype, fieldname, *args, **kwargs)

				def aligned_system_setting(key=None):
					if key == "rounding_method":
						return source["settings"]["rounding_method"]
					return get_system_settings(key)

				with (
					patch.object(frappe.db, "get_single_value", side_effect=aligned_setting),
					patch.object(frappe, "get_system_settings", side_effect=aligned_system_setting),
				):
					aligned = importlib.import_module(module_path).execute(frappe._dict(filters))
				write_json(
					output / f"{case}.target.same_settings.json",
					{
						"settings": source["settings"],
						"columns": aligned[0],
						"rows": aligned[1],
						"extras": list(aligned[2:]),
					},
				)
			write_json(output / f"{case}.{side}.json", value)
			print(case, side, len(value.get("rows", [])), value.get("error", ""), flush=True)
	finally:
		frappe.db.rollback()
		frappe.destroy()


def normalize(value, key=None):
	if isinstance(value, dict):
		return {k: normalize(v, k) for k, v in value.items()}
	if isinstance(value, list):
		return [normalize(v) for v in value]
	if key in ("options", "voucher_type") and isinstance(value, str):
		return DOCTYPE_MAP.get(value, value)
	if isinstance(value, (float, int)):
		return round(value, 6)
	return value


def row_counter(rows):
	return Counter(json.dumps(normalize(row), sort_keys=True, ensure_ascii=False) for row in rows)


def compare(output, selected):
	summary = []
	for case, slug, filters in CASES:
		if selected and case not in selected:
			continue
		source = json.loads((output / f"{case}.source.json").read_text())
		target = json.loads((output / f"{case}.target.json").read_text())
		result = {"case": case, "report": "SD YRP " + slug.replace("_", " ").title(), "filters": filters}
		if source.get("error") or target.get("error"):
			result.update(
				rows_equal=False, source_error=source.get("error"), target_error=target.get("error")
			)
		else:
			src_rows, dst_rows = row_counter(source["rows"]), row_counter(target["rows"])
			result["source_settings"] = source.get("settings")
			result["target_settings"] = target.get("settings")
			if slug == "lot_wise_stock_ageing":
				aligned = json.loads((output / f"{case}.target.same_settings.json").read_text())
				result["same_settings_rows_equal"] = src_rows == row_counter(aligned["rows"])
				write_json(
					output / f"{case}.same_settings.diff.json",
					{
						"source_only": [
							json.loads(row) for row in (src_rows - row_counter(aligned["rows"])).elements()
						],
						"target_only": [
							json.loads(row) for row in (row_counter(aligned["rows"]) - src_rows).elements()
						],
					},
				)
			result.update(
				source_rows=len(source["rows"]),
				target_rows=len(target["rows"]),
				rows_equal=src_rows == dst_rows,
				columns_equal=normalize(source["columns"]) == normalize(target["columns"]),
				extras_equal=normalize(source["extras"]) == normalize(target["extras"]),
			)
			for side, document in (("source", source), ("target", target)):
				write_json(
					output / f"{case}.{side}.normalized.json",
					{
						"columns": normalize(document["columns"]),
						"rows": sorted(
							[normalize(row) for row in document["rows"]],
							key=lambda r: json.dumps(r, sort_keys=True),
						),
						"extras": normalize(document["extras"]),
					},
				)
			write_json(
				output / f"{case}.diff.json",
				{
					"source_only": [json.loads(row) for row in (src_rows - dst_rows).elements()],
					"target_only": [json.loads(row) for row in (dst_rows - src_rows).elements()],
				},
			)
		summary.append(result)
	write_json(output / "summary.json", summary)
	print(json.dumps(summary, indent=2))
	return all(row["rows_equal"] and row.get("columns_equal") and row.get("extras_equal") for row in summary)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--export", choices=["source", "target"])
	parser.add_argument("--output", type=Path, default=Path("/home/anas/report-build/port/parity/stock_a"))
	parser.add_argument("--case", action="append")
	parser.add_argument("--compare-only", action="store_true")
	args = parser.parse_args()
	args.output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, args.output, args.case)
		return
	if not args.compare_only:
		for side, bench in (("source", "frappe-15"), ("target", "frappe-16")):
			command = [
				f"/home/anas/pilot/benches/{bench}/env/bin/python",
				str(Path(__file__).resolve()),
				"--export",
				side,
				"--output",
				str(args.output),
			]
			for case in args.case or []:
				command.extend(["--case", case])
			subprocess.run(command, check=True)
	raise SystemExit(0 if compare(args.output, args.case) else 1)


if __name__ == "__main__":
	main()
