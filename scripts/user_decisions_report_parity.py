"""Read-only snapshot proof for the 2026-10-20 C1-C4 user decisions.

Run with frappe-16/env/bin/python. Exports use each site's own Python and a
read-only transaction. MRP voucher representatives and UOMs remain visible in
the evidence; the accepted differences are checked separately from exact parity.
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from lot_consumption_report_parity import normalize

BENCHES = Path("/home/anas/pilot/benches")
CASES = [
	*(
		("C1-" + lot, "time_and_action_summary", {"lot": lot})
		for lot in ("C0425-01", "34178", "36224")
	),
	("C1-all-lots", "time_and_action_summary", {}),
	("C1-unknown-lot", "time_and_action_summary", {"lot": "_Missing Summary Lot"}),
	("C2-C4-accessories", "lot_consumption_report", {"lot": "C0925-57/1", "start_date": "2026-08-01", "end_date": "2026-09-30", "item_group": "Purchase"}),
	("C2-C4-products", "lot_consumption_report", {"lot": "JB2627-015", "start_date": "2026-08-01", "end_date": "2026-09-30", "item_group": "Products"}),
	*(
		("C3-" + month, "purchase_order_itemwise", {"date_based_on": "Posting Date", "from_date": start, "to_date": end, "open_status": "Open", "status": "Ordered"})
		for month, start, end in (("aug", "2026-08-01", "2026-08-31"), ("sep", "2026-09-01", "2026-09-30"))
	),
]


def source_summary_scan_proof(filters):
	"""Check every MRP inner representative, not just the final outer MAX."""
	import frappe

	condition = "AND B.lot=%(lot)s" if filters.get("lot") else ""
	candidates = f"""
		FROM `tabTime and Action Detail` A
		JOIN `tabTime and Action` B ON B.name=A.parent
		JOIN `tabAction` C ON C.name=A.action
		WHERE C.`default`=1 {condition}
	"""
	inner = f"SELECT B.lot, A.action, MIN(A.completed) completed, A.actual_date {candidates} GROUP BY B.lot,A.action"
	mrp = frappe.db.sql(inner, filters, as_dict=True)
	ranked = frappe.db.sql(f"""
		SELECT lot, action, MIN(completed) completed,
			MAX(CASE WHEN representative_rank=1 THEN actual_date END) actual_date
		FROM (
			SELECT B.lot, A.action, A.completed, A.actual_date,
				ROW_NUMBER() OVER (PARTITION BY B.lot,A.action ORDER BY B.name,A.name) representative_rank
			{candidates}
		) ranked GROUP BY lot,action
	""", filters, as_dict=True)
	return dict(plan=frappe.db.sql("EXPLAIN " + inner, filters, as_dict=True),
		groups=len(mrp), representatives_equal=mrp == ranked)


def export(side, output):
	sys.dont_write_bytecode = True
	import frappe

	bench = BENCHES / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("START TRANSACTION READ ONLY")
	try:
		for case, slug, filters in CASES:
			area = "essdee_production" if slug == "time_and_action_summary" else "mrp_stock" if slug == "lot_consumption_report" else "production_api"
			path = f"production_api.{area}.report.{slug}.{slug}" if side == "source" else f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}"
			module = importlib.import_module(path)
			columns, rows, *extras = module.execute(frappe._dict(filters))
			result = dict(filters=filters, columns=columns, rows=rows, extras=extras)
			if side == "source" and slug == "time_and_action_summary":
				result["scan_proof"] = source_summary_scan_proof(filters)
			if side == "target" and slug == "lot_consumption_report":
				# Independent ordered ledger scan verifies both representative and sum.
				ledger = frappe.db.sql("""
					SELECT name, item, valuation_rate, qty, voucher_no, voucher_type, warehouse,
						posting_date, posting_time
					FROM `tabYRP Stock Ledger Entry`
					WHERE lot=%(lot)s AND posting_date BETWEEN %(start_date)s AND %(end_date)s
					AND qty < 0 AND is_cancelled=0
					AND voucher_type IN ('YRP Stock Entry', 'SD YRP Lot Transfer', 'YRP Delivery Challan', 'YRP Goods Received Note')
					ORDER BY posting_date, posting_time, voucher_no, name
				""", filters, as_dict=True)
				buckets = {}
				for entry in ledger:
					bucket = buckets.setdefault((entry.item, entry.valuation_rate), dict(first=entry, quantity=0))
					# Ledger quantities are DECIMAL in MariaDB; avoid float-addition
					# noise in this independent Python sum.
					bucket["quantity"] += Decimal(str(entry.qty))
				result["earliest_voucher_rule"] = all(
					(row.stock_ledger_entry, row.voucher_no, row.voucher_type, row.from_warehouse, row.quantity)
					== (buckets[(row.item_variant, row.valuation_rate)]["first"].name,
						buckets[(row.item_variant, row.valuation_rate)]["first"].voucher_no,
						buckets[(row.item_variant, row.valuation_rate)]["first"].voucher_type,
						buckets[(row.item_variant, row.valuation_rate)]["first"].warehouse,
						float(buckets[(row.item_variant, row.valuation_rate)]["quantity"]))
					for row in rows
				)
			if side == "target" and slug == "purchase_order_itemwise":
				stored = frappe.get_all("Purchase Order Item", filters={"parent": ["in", list({r.name for r in rows})]}, fields=["parent", "item_code", "lot", "uom"])
				result["erp_uom_preserved"] = all(any(
					(r.name, r.item_variant, r.lot, r.uom) == (item.parent, item.item_code, item.lot, item.uom)
					for item in stored
				) for r in rows)
			if side == "target" and slug != "time_and_action_summary":
				from frappe.desk.query_report import run
				from yrp.web_reports.jobs import run_web_report

				name = "SD YRP " + ("Lot Consumption Report" if slug == "lot_consumption_report" else "Purchase Order Itemwise")
				with patch("yrp.web_reports.jobs._enqueue_lazy_cleanup"):
					web = run_web_report(slug.replace("_", "-"), filters)
					desk = run(name, filters=filters, ignore_prepared_report=True, are_default_filters=True)
				result["web_desk_equal"] = web["columns"] == desk["columns"] and web["result"] == desk["result"]
			(output / f"{case}.{side}.json").write_text(frappe.as_json(result, indent=2) + "\n")
	finally:
		frappe.db.rollback()
		frappe.destroy()


def compare(case, slug, source, target):
	source, target = normalize(source), normalize(target)
	# Time-and-Action's link doctype also migrated; values and grouping stay exact.
	for column in source["columns"]:
		if column.get("options") == "Action":
			column["options"] = "SD YRP Action"
	ignored = {"uom"} if slug == "purchase_order_itemwise" else {"stock_ledger_entry", "voucher_type", "voucher_no", "from_warehouse", "to_warehouse"} if slug == "lot_consumption_report" else set()
	# Compare every source field in order; no rounding, sorting or deduplication.
	fields = list(dict.fromkeys(key for row in source["rows"] for key in row if key not in ignored))
	project = lambda rows: [{key: row.get(key) for key in fields} for row in rows]
	result = dict(case=case, filters=source["filters"], mrp_rows=len(source["rows"]), erp_rows=len(target["rows"]),
		rows_equal=source["rows"] == target["rows"],
		accepted_fields_equal=project(source["rows"]) == project(target["rows"]),
		columns_equal=source["columns"] == target["columns"], extras_equal=source["extras"] == target["extras"],
		accepted_differences=sorted(ignored),
		**{key: target[key] for key in ("earliest_voucher_rule", "erp_uom_preserved", "web_desk_equal") if key in target})
	if slug == "time_and_action_summary":
		result["sewing_date"] = next((row["actual_date"] for row in target["rows"] if row["action"] == "SEWING"), None)
		result["representatives_equal"] = source["scan_proof"]["representatives_equal"]
		result["representative_groups"] = source["scan_proof"]["groups"]
	result["passed"] = all(result[key] for key in ("accepted_fields_equal", "columns_equal", "extras_equal", "earliest_voucher_rule", "erp_uom_preserved", "web_desk_equal", "representatives_equal") if key in result)
	return result


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--export", choices=("source", "target"))
	parser.add_argument("--output", type=Path, default=Path("/home/anas/report-build/fix15/user_decisions_2026_10_20"))
	args = parser.parse_args()
	output = args.output.resolve()
	output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, output)
		return
	for side, bench in (("source", "frappe-15"), ("target", "frappe-16")):
		subprocess.run([str(BENCHES / bench / "env/bin/python"), str(Path(__file__).resolve()), "--export", side, "--output", str(output)], check=True)
	summary = [compare(case, slug, json.loads((output / f"{case}.source.json").read_text()), json.loads((output / f"{case}.target.json").read_text())) for case, slug, _ in CASES]
	(output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
	print(json.dumps(summary, indent=2))
	raise SystemExit(0 if all(row["passed"] for row in summary) else 1)


if __name__ == "__main__":
	main()
