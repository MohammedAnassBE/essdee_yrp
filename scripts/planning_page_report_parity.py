"""Read-only page/report parity runner; no migrations or source writes."""

import argparse
import fcntl
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path("/home/anas/report-build/port/parity")


def normalise_supplier(page):
	sizes = list(
		dict.fromkeys(
			size for item in page["items"] for lot in item["lots"] for size in lot["primary_values"]
		)
	)
	rows = []
	for item in page["items"]:
		for lot in item["lots"]:
			for index, group in enumerate(lot["rows"] + lot["totals"]):
				total = index >= len(lot["rows"])
				for kind in ["delivered", "received", "difference"]:
					dates = group.get("dates", {})
					prefix = {"delivered": "dc", "received": "grn"}.get(kind)
					rows.append(
						{
							"item": item["item"],
							"lot": lot["lot"],
							"colour": "Total" if total else group["colour"],
							"part": group.get("part"),
							"serial_no": None if total else index + 1,
							"type": kind.title(),
							"is_total": total,
							"total": group["totals"][kind],
							"first_date": dates.get("first_" + prefix + "_date") if prefix else None,
							"last_date": dates.get("last_" + prefix + "_date") if prefix else None,
							"diff_days": dates.get("diff_days") if kind == "delivered" else None,
							**{
								f"size_{i}": group["values"].get(size, {}).get(kind, 0)
								for i, size in enumerate(sizes)
							},
						}
					)
	return rows


def normalise_columns(page):
	lots = [lot for item in page["items"] for lot in item["lots"]]
	sizes = list(dict.fromkeys(size for lot in lots for size in lot["primary_values"]))
	columns = [
		("item", "Item", "Link"),
		("lot", "Lot", "Link"),
		("serial_no", "S.No", "Int"),
		("colour", "Colour", "Data"),
	]
	if any(lot["is_set_item"] for lot in lots):
		labels = list(dict.fromkeys(lot["set_attr"] or "Part" for lot in lots if lot["is_set_item"]))
		columns.append(("part", " / ".join(labels), "Data"))
	columns.append(("type", "Type", "Data"))
	columns.extend((f"size_{i}", size, "Float") for i, size in enumerate(sizes))
	columns.extend(
		[
			("total", "Total", "Float"),
			("first_date", "First Date", "Date"),
			("last_date", "Last Date", "Date"),
			("diff_days", "Diff", "Int"),
		]
	)
	return columns


CASES = [
	("C1-1", "sd_yrp_supplier_pending_report", {"supplier": "S-0171", "process": "Ironing and Packing"}),
	("C1-2", "sd_yrp_supplier_pending_report", {"supplier": "S-0172", "process": "Stitching"}),
	("C2-1", "sd_yrp_item_wise_pending_report", {}),
	("C2-2", "sd_yrp_item_wise_pending_report", {"warehouse": ["S-0056"]}),
	(
		"C3-1",
		"sd_yrp_datewise_item_packed",
		{"start_date": "2026-09-01 00:00:00", "end_date": "2026-09-30 23:59:59"},
	),
	(
		"C3-2",
		"sd_yrp_datewise_item_packed",
		{"start_date": "2026-10-01 00:00:00", "end_date": "2026-10-19 23:59:59"},
	),
]


def child(side):
	sys.dont_write_bytecode = True
	import frappe

	bench = Path("/home/anas/pilot/benches") / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	sys.path.insert(0, "/home/anas/pilot/benches/frappe-15/apps/essdee_sales")
	for case, slug, filters in CASES:
		result = {"filters": filters, "installed_apps": frappe.get_installed_apps()}
		if not case.startswith("C1"):
			result["source_oms_tables_present"] = {
				table: frappe.db.table_exists(table)
				for table in [
					"Order",
					"Order Item",
					"Packing Slip",
					"Packing Slip Item",
					"Tags Select",
					"Order Settings",
				]
			}
			result["oms_doctypes_present"] = {
				table: bool(frappe.db.exists("DocType", table))
				for table in result["source_oms_tables_present"]
			}
		try:
			if side == "source":
				if case.startswith("C1"):
					module = importlib.import_module(
						"production_api.production_api.page.supplier_pending_report.supplier_pending_report"
					)
					result["page"] = module.get_supplier_pending_report(**filters)
				elif case.startswith("C2"):
					module = importlib.import_module(
						"essdee_sales.sales_order_management.doctype.order.order"
					)
					result["page"] = module.get_all_pending_items(warehouse_list=filters.get("warehouse", []))
				else:
					module = importlib.import_module(
						"essdee_sales.sales_order_management.doctype.packing_slip.packing_slip"
					)
					result["page"] = module.make_datewise_pack_slip_report(**filters)
			else:
				if not case.startswith("C1"):
					native_doctype = "YRP Sales Order" if case.startswith("C2") else "YRP Packing Slip"
					result["native_target_schema"] = [
						field.fieldname for field in frappe.get_meta(native_doctype).fields
					]
					result["blocked"] = (
						"Source OMS transactions have no approved migration mapping; report withheld."
					)
					raise RuntimeError(result["blocked"])
				module = importlib.import_module(f"essdee_yrp.essdee_yrp.report.{slug}.{slug}")
				result["desk"] = module.execute(filters)
				if case.startswith("C1"):
					result["page"] = module.get_supplier_pending_report(**filters)
		except Exception as exc:
			result["error"] = f"{type(exc).__name__}: {exc}"
		OUT.mkdir(parents=True, exist_ok=True)
		(OUT / f"{case}-{side}.json").write_text(frappe.as_json(result, indent=2))
	frappe.db.rollback()
	frappe.destroy()


def run():
	for side, version in [("source", "frappe-15"), ("target", "frappe-16")]:
		bench = Path("/home/anas/pilot/benches") / version
		subprocess.run([str(bench / "env/bin/python"), __file__, "--side", side], cwd=bench, check=True)
	summary = []
	for case, slug, filters in CASES:
		source = json.loads((OUT / f"{case}-source.json").read_text())
		target = json.loads((OUT / f"{case}-target.json").read_text())
		entry = {"case": case, "report": slug, "filters": filters}
		if "error" in source or "error" in target:
			entry.update(equal=None, source_error=source.get("error"), target_error=target.get("error"))
		elif case.startswith("C1"):
			entry["page_equal"] = source["page"] == target["page"]
			source_rows = normalise_supplier(source["page"])
			(OUT / f"{case}-source-normalised.json").write_text(json.dumps(source_rows, indent=2) + "\n")
			(OUT / f"{case}-target-normalised.json").write_text(
				json.dumps(target["desk"][1], indent=2) + "\n"
			)
			entry["rows_equal"] = source_rows == target["desk"][1]
			entry["columns_equal"] = normalise_columns(source["page"]) == [
				tuple(column[key] for key in ("fieldname", "label", "fieldtype"))
				for column in target["desk"][0]
			]
			entry["equal"] = entry["rows_equal"] and entry["columns_equal"]
			entry["source_pending_rows"] = sum(
				len(lot["rows"]) for item in source["page"]["items"] for lot in item["lots"]
			)
			entry["desk_rows"] = len(target["desk"][1])
		else:
			entry["equal"] = None
			entry["reason"] = "OMS transaction mapping is absent; source parity is blocked."
		summary.append(entry)
	(OUT / "worker4-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
	print(json.dumps(summary, indent=2))
	return (
		1
		if any(entry["equal"] is False for entry in summary)
		else 2
		if any(entry["equal"] is None for entry in summary)
		else 0
	)


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--side")
	args = parser.parse_args()
	if args.side:
		child(args.side)
	else:
		OUT.mkdir(parents=True, exist_ok=True)
		with (OUT / "worker4.lock").open("w") as lock:
			fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
			raise SystemExit(run())
