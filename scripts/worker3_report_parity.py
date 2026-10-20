"""Read-only MRP/ERP parity for Lot Consumption, Lot Wise Stock Ageing and Sewing SCR.

Run: env/bin/python apps/essdee_yrp/scripts/worker3_report_parity.py --output PATH
Only DocType renames and SCR's missing cells (rendered as zero) are normalized.
SCR compares all visible headers, colour order, quantities and group metadata;
the ERP-only balance_headers key is renderer metadata and is reported separately.
Report row order, all stock values, columns and chart data are compared directly.
"""

import argparse
import importlib
import json
import os
import subprocess
from pathlib import Path

CASES = [
	(
		"C1_a",
		"lot_consumption_report",
		dict(lot="C0925-57/1", start_date="2026-08-01", end_date="2026-09-30", item_group="Purchase"),
	),
	(
		"C1_b",
		"lot_consumption_report",
		dict(lot="JB2627-015", start_date="2026-08-01", end_date="2026-09-30", item_group="Products"),
	),
	(
		"C2_a",
		"lot_wise_stock_ageing",
		dict(
			lot="C0925-57/1",
			to_date="2026-09-30",
			range1=30,
			range2=60,
			range3=90,
			show_warehouse_wise_stock=0,
		),
	),
	(
		"C2_b",
		"lot_wise_stock_ageing",
		dict(
			lot="JB2627-015",
			to_date="2026-09-30",
			range1=30,
			range2=60,
			range3=90,
			show_warehouse_wise_stock=1,
			warehouse="S-0172",
			parent_item="535473 - LADIES CREAM XMAS DOGS AOP B",
		),
	),
	# Live-evidence lots JB2627-020 and F0826-22/2 W PJ 1 have no plans in either
	# local snapshot. These two local lots reproduce the same absent-AQL case.
	("C3_a", "scr", dict(supplier="S-0172", lot="JB2627-016")),
	("C3_b", "scr", dict(supplier="S-0172", lot="F0826-22 W-D/N 2")),
]
DOCTYPE_MAP = {
	"Stock Ledger Entry": "YRP Stock Ledger Entry",
	"Lot": "SD YRP Lot",
	"Item Variant": "Item",
	"Stock Entry": "YRP Stock Entry",
	"Lot Transfer": "SD YRP Lot Transfer",
	"Delivery Challan": "YRP Delivery Challan",
	"Goods Received Note": "YRP Goods Received Note",
}


def write(path, value):
	path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def export(side, output):
	import frappe

	bench = Path("/home/anas/pilot/benches") / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("SET SESSION TRANSACTION READ ONLY")
	try:
		for case, slug, filters in CASES:
			if slug == "scr":
				path = (
					"production_api.production_api.doctype.sewing_plan.sewing_plan"
					if side == "source"
					else "essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan.sd_yrp_sewing_plan"
				)
				value = importlib.import_module(path).get_scr_data(**filters)
			else:
				name = slug if side == "source" else "sd_yrp_" + slug
				prefix = (
					"production_api.mrp_stock.report" if side == "source" else "essdee_yrp.essdee_yrp.report"
				)
				result = importlib.import_module(f"{prefix}.{name}.{name}").execute(frappe._dict(filters))
				value = dict(columns=result[0], rows=result[1], extras=result[2:])
			write(output / f"{case}.{side}.json", value)
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
	return value


def scr_view(value):
	headers = value["headers"]
	return {
		"status": value["status"],
		"primary_values": value["primary_values"],
		"headers": headers,
		"colours": value["colours"],
		"is_set_item": value["is_set_item"],
		"set_attr": value["set_attr"],
		"item": value["item"],
		"data": {
			colour: {
				**{key: val for key, val in group.items() if key not in ("values", "type_wise_total")},
				"values": {
					size: {h: values.get(h, 0) for h in headers} for size, values in group["values"].items()
				},
				"totals": {h: group["type_wise_total"].get(h, 0) for h in headers},
			}
			for colour, group in value["data"].items()
		},
	}


def compare(output):
	summary = []
	for case, slug, filters in CASES:
		source = json.loads((output / f"{case}.source.json").read_text())
		target = json.loads((output / f"{case}.target.json").read_text())
		if slug == "scr":
			left, right = scr_view(source), scr_view(target)
			differences = []
			for colour, group in left["data"].items():
				for size, values in {**group["values"], "TOTAL": group["totals"]}.items():
					other = right["data"].get(colour, {})
					other = (
						other.get("totals", {}) if size == "TOTAL" else other.get("values", {}).get(size, {})
					)
					for header, value in values.items():
						if value != other.get(header):
							differences.append(
								dict(
									colour=colour, size=size, column=header, mrp=value, erp=other.get(header)
								)
							)
			row = dict(
				case=case,
				filters=filters,
				equal=left == right,
				differences=differences,
				source_rows=sum(len(g["values"]) for g in source["data"].values()),
				target_rows=sum(len(g["values"]) for g in target["data"].values()),
				extra_target_headers=[h for h in target["headers"] if h not in source["headers"]],
			)
			row["extra_api_metadata"] = sorted(target.keys() - source.keys())
			row["columns_equal"] = source["headers"] == target["headers"]
			row["colour_order_equal"] = source["colours"] == target["colours"]
		else:
			left, right = normalize(source), normalize(target)
			row = dict(
				case=case,
				filters=filters,
				equal=left == right,
				source_rows=len(left["rows"]),
				target_rows=len(right["rows"]),
				rows_equal=left["rows"] == right["rows"],
				columns_equal=left["columns"] == right["columns"],
				extras_equal=left["extras"] == right["extras"],
			)
			if slug == "lot_consumption_report":
				fields = ("item_variant", "valuation_rate", "quantity", "item_group", "item_name", "lot")
				row["grouped_values_equal"] = [{k: r[k] for k in fields} for r in left["rows"]] == [
					{k: r[k] for k in fields} for r in right["rows"]
				]
				voucher_fields = (
					"stock_ledger_entry",
					"voucher_type",
					"voucher_no",
					"from_warehouse",
					"to_warehouse",
				)
				row["different_voucher_rows"] = sum(
					any(a[k] != b[k] for k in voucher_fields)
					for a, b in zip(left["rows"], right["rows"], strict=False)
				)
			if not row["rows_equal"]:
				row["first_differences"] = [
					dict(index=i, mrp=a, erp=b)
					for i, (a, b) in enumerate(zip(left["rows"], right["rows"], strict=False))
					if a != b
				][:2]
		summary.append(row)
	write(output / "summary.json", summary)
	print(json.dumps(summary, indent=2))
	return all(row["equal"] for row in summary)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--output", type=Path, default=Path("/home/anas/report-build/port/parity/worker3_stock_sewing/after")
	)
	parser.add_argument("--export", choices=["source", "target"])
	args = parser.parse_args()
	args.output = args.output.resolve()
	args.output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, args.output)
		return
	for side, bench in (("source", "frappe-15"), ("target", "frappe-16")):
		subprocess.run(
			[
				f"/home/anas/pilot/benches/{bench}/env/bin/python",
				str(Path(__file__).resolve()),
				"--export",
				side,
				"--output",
				str(args.output),
			],
			check=True,
		)
	raise SystemExit(0 if compare(args.output) else 1)


if __name__ == "__main__":
	main()
