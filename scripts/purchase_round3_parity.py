"""Read-only C1-C4 parity and explicit simulation of the unapplied UOM backfill.

Run with the frappe-16 Python. Source and target enforce READ ONLY transactions.
Actual output and simulated provenance output are recorded separately; exit 1
retains every real difference. No migration, schema or business data is written.
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
from itertools import zip_longest
from pathlib import Path
from unittest.mock import patch

from worker2_desk_report_parity import builder, report_definition

BENCHES = Path("/home/anas/pilot/benches")
CASES = [
	(
		"C1-sep",
		"Purchase Order Itemwise",
		dict(
			date_based_on="Posting Date",
			from_date="2026-09-01",
			to_date="2026-09-30",
			open_status="Open",
			status="Ordered",
		),
	),
	(
		"C1-aug",
		"Purchase Order Itemwise",
		dict(
			date_based_on="Posting Date", from_date="2026-08-01", to_date="2026-08-31", open_status="Closed"
		),
	),
	*[
		(case, name, filters)
		for prefix, name in [("C2", "PURCHASE ORDER"), ("C3", "PURCHASE ORDER - 13.02.2026")]
		for case, filters in [
			(prefix + "-all", {}),
			(prefix + "-supplier", {"supplier": "SRI SABAREE  YARNS"}),
		]
	],
	("C4-all", "Previous Month Pending Bills - Departmentwise", {}),
	("C4-accounts", "Previous Month Pending Bills - Departmentwise", {"assigned_to": "Accounts"}),
	("C4-yarn", "Previous Month Pending Bills - Departmentwise", {"assigned_to": "YARN"}),
]


def write(path, payload):
	path.write_text(json.dumps(payload, default=str, indent=2) + "\n")


def provenance_query(query, values, updates, existing_column):
	"""Overlay pending metadata while retaining any already applied markers."""
	token = "`tabPurchase Order Item`.`custom_mrp_report_uom`"
	values = dict(values or {})
	if token not in str(query):
		return query, values
	fallback = token if existing_column else "NULL"
	parts = []
	for i, update in enumerate(updates):
		parts.append(f"WHEN %(r3_name_{i})s THEN %(r3_marker_{i})s")
		values[f"r3_name_{i}"], values[f"r3_marker_{i}"] = update["name"], update["marker"]
	expression = (
		("CASE `tabPurchase Order Item`.`name` " + " ".join(parts) + " ELSE " + fallback + " END")
		if parts
		else fallback
	)
	return str(query).replace(token, expression), values


def child(side, out):
	import frappe

	bench = BENCHES / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("START TRANSACTION READ ONLY")
	try:
		bill_dt = "Vendor Bill Tracking" if side == "source" else "YRP Bill Tracking"
		evidence = dict(
			pos=frappe.get_all(
				"Purchase Order",
				filters={"name": ["in", ["PO-2627-1083", "YRP-PO-2026-00002"]]},
				fields=["name", "creation", "modified", "modified_by", "docstatus", "status", "open_status"]
				+ (["yrp_fulfillment_status"] if side == "target" else []),
			),
			pending_bills=frappe.get_all(
				bill_dt,
				filters=[
					["bill_date", "Timespan", "last month"],
					["form_status", "!=", "Closed"],
					["docstatus", "!=", 2],
				],
				fields=[
					"name",
					"bill_date",
					"assigned_to",
					"form_status",
					"docstatus",
					"modified",
					"modified_by",
				],
				order_by="name",
			),
			bill_history=frappe.get_all(
				"Vendor Bill Tracking Assignment Detail"
				if side == "source"
				else "YRP Bill Tracking Assignment Detail",
				filters={"parent": "VBT-10544"},
				fields=["name", "idx", "assigned_to", "assigned_on", "assigned_by", "action"],
				order_by="idx",
			),
		)
		if side == "source":
			source_rows = frappe.db.sql(
				"SELECT name,parent,item_variant,creation,modified,uom "
				'FROM `tabPurchase Order Item` WHERE uom IS NULL OR uom="" ORDER BY name',
				as_dict=True,
			)
			write(
				out / "source-uom.json",
				dict(source_site=frappe.local.site, doctype="Purchase Order Item", rows=source_rows),
			)
		else:
			from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order_itemwise.mrp_uom_provenance import (
				FIELD,
				apply_backfill,
			)

			plan = apply_backfill(str(out / "source-uom.json"))
			write(out / "backfill-dry-run.json", plan)
			versions = frappe.get_all(
				"Version",
				filters={"ref_doctype": "Purchase Order", "docname": "PO-2627-1083"},
				fields=["name", "creation", "owner", "data"],
				order_by="creation",
			)
			evidence["versions"] = [
				dict(
					name=r.name,
					creation=r.creation,
					owner=r.owner,
					changed=[
						c
						for c in json.loads(r.data).get("changed", [])
						if c[0] in {"docstatus", "status", "yrp_fulfillment_status", "approved_by"}
					],
				)
				for r in versions
			]
		write(out / f"evidence-{side}.json", evidence)
		for case, name, filters in CASES:
			if case.startswith("C1"):
				module = (
					"production_api.production_api.report.purchase_order_itemwise.purchase_order_itemwise"
					if side == "source"
					else "essdee_yrp.essdee_yrp.report."
					"sd_yrp_purchase_order_itemwise.sd_yrp_purchase_order_itemwise"
				)
				controller = importlib.import_module(module)
				columns, rows = controller.execute(frappe._dict(filters))
				result = dict(columns=columns, rows=rows)
				if side == "target":
					from yrp.web_reports.jobs import run_web_report

					with patch("yrp.web_reports.jobs._enqueue_lazy_cleanup"):
						web = run_web_report("purchase-order-itemwise", dict(filters))
					result["web_rows"] = [r for r in web["result"] if r and not r.get("is_total_row")]
					# Substitute a virtual metadata column in SELECT only. This uses
					# the real report query/projection without applying the schema patch.
					sql, has_column = frappe.db.sql, frappe.db.has_column
					existing_column = has_column("Purchase Order Item", FIELD)
					parent_only_save = False

					def overlay(query, values=None, **kwargs):
						if "`tabPurchase Order Item`.`" + FIELD + "`" in str(query):
							query, values = provenance_query(query, values, plan["updates"], existing_column)
							if parent_only_save:
								# Frappe advances child timestamps on an unrelated parent
								# save. Simulate the SELECT only; never update site rows.
								query = str(query).replace(
									"`tabPurchase Order Item`.`modified`", "'2099-01-01 00:00:00'"
								)
						return sql(query, values, **kwargs)

					def has_provenance(dt, field):
						return (
							True if (dt, field) == ("Purchase Order Item", FIELD) else has_column(dt, field)
						)

					with (
						patch.object(frappe.db, "sql", side_effect=overlay),
						patch.object(frappe.db, "has_column", side_effect=has_provenance),
					):
						result["simulated_rows"] = controller.execute(frappe._dict(filters))[1]
						with patch("yrp.web_reports.jobs._enqueue_lazy_cleanup"):
							web = run_web_report("purchase-order-itemwise", dict(filters))
						result["simulated_web_rows"] = [
							r for r in web["result"] if r and not r.get("is_total_row")
						]
						parent_only_save = True
						result["simulated_parent_only_save_rows"] = controller.execute(frappe._dict(filters))[
							1
						]
						with patch("yrp.web_reports.jobs._enqueue_lazy_cleanup"):
							web = run_web_report("purchase-order-itemwise", dict(filters))
						result["simulated_parent_only_save_web_rows"] = [
							r for r in web["result"] if r and not r.get("is_total_row")
						]
			else:
				report = report_definition(("SD YRP " if side == "target" else "") + name, side == "target")
				while report.report_type == "Custom Report":
					report = report_definition(report.reference_report, side == "target")
				columns, rows = (
					builder(report, filters)
					if report.report_type == "Report Builder"
					else report.execute_module(frappe._dict(filters))[:2]
				)
				result = dict(columns=columns, rows=rows)
			write(out / f"{case}-{side}.json", result)
	finally:
		frappe.db.rollback()
		frappe.destroy()


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--child", choices=["source", "target"])
	parser.add_argument("--out", type=Path, required=True)
	args = parser.parse_args()
	args.out.mkdir(parents=True, exist_ok=True)
	if args.child:
		child(args.child, args.out)
		return 0
	for side, bench in [("source", "frappe-15"), ("target", "frappe-16")]:
		subprocess.run(
			[
				str(BENCHES / bench / "env/bin/python"),
				str(Path(__file__).resolve()),
				"--child",
				side,
				"--out",
				str(args.out),
			],
			check=True,
		)
	summary = []
	for case, name, filters in CASES:
		a, b = [json.loads((args.out / f"{case}-{side}.json").read_text()) for side in ["source", "target"]]
		key = "assigned_to" if case.startswith("C4") else "name"
		x, y = [{r[key]: r for r in payload["rows"]} for payload in [a, b]]
		entry = dict(
			case=case,
			report=name,
			filters=filters,
			mrp_rows=len(a["rows"]),
			erp_rows=len(b["rows"]),
			actual_equal=a["rows"] == b["rows"],
			definitions="controller" if case.startswith("C1") else "staged Report JSON",
			differences=[
				dict(key=k, mrp=x.get(k), erp=y.get(k))
				for k in dict.fromkeys([*x, *y])
				if x.get(k) != y.get(k)
			],
		)
		entry["columns_equal"] = [
			{key: col.get(key) for key in ["fieldname", "label", "width"]} for col in a["columns"]
		] == [{key: col.get(key) for key in ["fieldname", "label", "width"]} for col in b["columns"]]
		if "simulated_rows" in b:
			# Itemwise can repeat the PO name. Preserve row positions instead of
			# collapsing those rows into a dictionary by parent identity.
			entry["differences"] = [
				dict(row=i, mrp=left, erp=right)
				for i, (left, right) in enumerate(zip_longest(a["rows"], b["rows"]))
				if left != right
			]
			entry["simulated_provenance_equal"] = a["rows"] == b["simulated_rows"]

			def visible(rows):
				return [{key: r.get(key) for key in a["rows"][0]} for r in rows]

			entry["web_matches_desk"] = visible(b["web_rows"]) == b["rows"]
			entry["simulated_web_matches_mrp"] = visible(b["simulated_web_rows"]) == a["rows"]
			entry["simulated_parent_only_save_equal"] = b["simulated_parent_only_save_rows"] == a["rows"]
			entry["simulated_parent_only_save_web_equal"] = (
				visible(b["simulated_parent_only_save_web_rows"]) == a["rows"]
			)
		summary.append(entry)
	write(args.out / "summary.json", summary)
	print(json.dumps([{k: v for k, v in r.items() if k != "differences"} for r in summary], indent=2))
	return (
		0
		if all(
			r["actual_equal"]
			and r["columns_equal"]
			and r.get("web_matches_desk", True)
			and r.get("simulated_parent_only_save_equal", True)
			and r.get("simulated_parent_only_save_web_equal", True)
			for r in summary
		)
		else 1
	)


if __name__ == "__main__":
	sys.exit(main())
