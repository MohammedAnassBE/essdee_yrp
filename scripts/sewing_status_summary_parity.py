"""Read-only Status Summary parity against the migrated MRP snapshot.

Run with either bench's env/bin/python. Both exports use read-only transactions.
Filters are applied after the supplier endpoint, as in Desk and /web. Only the
Lot DocType rename and blank cells are normalized. Column labels, order, colour
wrappers, quantities, dates, readiness and supplier grand totals are checked;
ERP aliases/renderer metadata are outside the visible MRP contract.
"""

import argparse
import importlib
import json
import os
import subprocess
from pathlib import Path

CASES = [
	{"case": "supplier", "supplier": "S-0172"},
	{"case": "supplier_lot", "supplier": "S-0172", "lot": "C0426-34/1"},
]
READINESS = ["Ready for Checking", "Ready for AQL", "Ready for Pre final", "Ready for Final Inspection"]


def write(path, value):
	path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def export(side, output):
	import frappe

	bench = Path("/home/anas/pilot/benches") / ("frappe-15" if side == "mrp" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "mrp" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("SET SESSION TRANSACTION READ ONLY")
	try:
		module = (
			"production_api.production_api.doctype.sewing_plan.sewing_plan"
			if side == "mrp"
			else "essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan.sd_yrp_sewing_plan"
		)
		write(output / f"{side}.json", importlib.import_module(module).get_sp_status_summary("S-0172"))
	finally:
		frappe.db.rollback()
		frappe.destroy()


def view(payload, side, filters):
	headers = [[{"Lot": "SD YRP Lot"}.get(h, h) for h in payload[k]]
		for k in ("header1", "header2", "header3")]
	rows = []
	for row in payload["data"][1:]:
		if filters.get("lot") and row["lot"] != filters["lot"]:
			continue
		if side == "mrp":
			colour = row.get("display_colour") or row.get("attr_details", {}).get(row.get("pack_attr"))
			part = row.get("attr_details", {}).get(row.get("set_attr")) if row.get("is_set_item") else ""
		else:
			colour, part = row.get("colour"), row.get("part")
		visible = {"Item": row["item"], "SD YRP Lot": row["lot"], "Colour": colour, "Part": part or ""}
		for h in headers[0][4:] + headers[1] + headers[2]:
			visible[h] = row.get(h) or (0 if h in headers[1] else "")
		rows.append(visible)
	return headers, rows


def compare(output, baseline=None):
	mrp, erp = [json.loads((output / f"{side}.json").read_text()) for side in ("mrp", "erp")]
	summary = []
	for filters in CASES:
		left_headers, left_rows = view(mrp, "mrp", filters)
		right_headers, right_rows = view(erp, "erp", filters)
		key = lambda row: tuple(row[h] for h in ("SD YRP Lot", "Item", "Colour", "Part"))
		left, right = sorted(left_rows, key=key), sorted(right_rows, key=key)
		left_groups, right_groups = {}, {}
		for row in left:
			left_groups.setdefault(key(row), []).append(row)
		for row in right:
			right_groups.setdefault(key(row), []).append(row)
		common = left_groups.keys() & right_groups.keys()
		comparable = sorted(k for k in common if len(left_groups[k]) == len(right_groups[k]) == 1)
		differences = []
		for identity in comparable:
			a, b = left_groups[identity][0], right_groups[identity][0]
			for h in dict.fromkeys([*a, *b]):
				if a.get(h) != b.get(h):
					differences.append({"row": key(a), "column": h, "mrp": a.get(h), "erp": b.get(h)})
		readiness = [d for d in differences if d["column"] in READINESS]
		work_orders = [r for r in erp["data"][1:] if not filters.get("lot") or r["lot"] == filters["lot"]]
		grand_totals = [
			{h: (payload.get("data") or [{}])[0].get(h) or 0 for h in headers[1]}
			for payload, headers in ((mrp, left_headers), (erp, right_headers))
		]
		# Lot-filtered tables compute their totals from visible rows in both clients.
		visible_totals = [
			{h: sum(row.get(h) or 0 for row in rows) for h in headers[1]}
			for rows, headers in ((left_rows, left_headers), (right_rows, right_headers))
		]
		result = {
			"filters": filters, "mrp_rows": len(left), "erp_rows": len(right),
			"columns_equal": left_headers == right_headers,
			"mrp_columns": left_headers,
			"erp_columns": right_headers,
			"grouped_rows_equal": left == right,
			"grand_totals_equal": grand_totals[0] == grand_totals[1],
			"mrp_grand_totals": grand_totals[0], "erp_grand_totals": grand_totals[1],
			"visible_totals_equal": visible_totals[0] == visible_totals[1],
			"row_order_equal": [key(r) for r in left_rows] == [key(r) for r in right_rows],
			"comparable_rows": len(comparable),
			"mrp_only_groups": sorted(left_groups.keys() - right_groups.keys()),
			"erp_only_groups": sorted(right_groups.keys() - left_groups.keys()),
			"duplicate_groups": sorted(k for k in common if len(left_groups[k]) != 1 or len(right_groups[k]) != 1),
			"readiness_differences": len(readiness),
			"readiness_equal_on_comparable_rows": bool(comparable) and not readiness,
			"readiness_rows_different": len({tuple(d["row"]) for d in readiness}),
			"shared_quantities_dates_equal": not any(d["column"] not in READINESS and d["column"] in left_headers[0] + left_headers[1] and d["column"] in right_headers[0] + right_headers[1] for d in differences),
			"erp_work_order_status_open": bool(work_orders) and all(r["work_order_status"] == "Open" for r in work_orders),
			"differences": differences,
		}
		result["equal"] = (bool(left_rows) and left_headers == right_headers and left_rows == right_rows
			and result["visible_totals_equal"] and (bool(filters.get("lot")) or result["grand_totals_equal"]))
		if baseline:
			previous = json.loads((baseline / "erp.json").read_text())
			def without_readiness(payload):
				labels = {*READINESS, "ready_for_checking", "ready_for_aql", "ready_for_pre_final", "ready_for_final_inspection"}
				return {**payload, "data": [{k: v for k, v in r.items() if k not in labels} for r in payload["data"]]}
			result["erp_non_readiness_output_unchanged"] = without_readiness(previous) == without_readiness(erp)
		summary.append(result)
	write(output / "summary.json", summary)
	print(json.dumps([{k: v for k, v in r.items() if k not in {"differences", "mrp_columns", "erp_columns"}} for r in summary], indent=2))
	return all(
		r["equal"] and r["erp_work_order_status_open"] and r.get("erp_non_readiness_output_unchanged", True)
		for r in summary
	)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--export", choices=["mrp", "erp"])
	parser.add_argument("--baseline", type=Path, help="Previous exports, to verify quantities/dates/ordering stayed unchanged")
	parser.add_argument("--compare-only", action="store_true", help="Compare existing exports without accessing either database")
	args = parser.parse_args()
	args.output = args.output.resolve()
	args.output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, args.output)
		return
	if args.compare_only:
		raise SystemExit(0 if compare(args.output, args.baseline) else 1)
	for side, bench in (("mrp", "frappe-15"), ("erp", "frappe-16")):
		subprocess.run([
			f"/home/anas/pilot/benches/{bench}/env/bin/python", str(Path(__file__).resolve()),
			"--export", side, "--output", str(args.output),
		], check=True)
	raise SystemExit(0 if compare(args.output, args.baseline) else 1)


if __name__ == "__main__":
	main()
