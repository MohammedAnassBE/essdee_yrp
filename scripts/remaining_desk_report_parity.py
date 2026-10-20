"""Read-only worker 5 parity cases; run with either bench's Python."""

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path("/home/anas/report-build/port/parity")
BENCHES = Path("/home/anas/pilot/benches")
CASES = [
	("C1-1", "Item Wise Pending Report", {}),
	("C1-2", "Item Wise Pending Report", {"warehouse": ["S-0056"]}),
	(
		"C2-1",
		"Datewise Item Packed",
		{"start_date": "2026-09-01 00:00:00", "end_date": "2026-09-30 23:59:59"},
	),
	(
		"C2-2",
		"Datewise Item Packed",
		{"start_date": "2026-10-01 00:00:00", "end_date": "2026-10-19 23:59:59"},
	),
	("C3-1", "PURCHASE ORDER", {}),
	("C3-2", "PURCHASE ORDER", {"supplier": "SRI SABAREE  YARNS"}),
	("C4-1", "PURCHASE ORDER - 13.02.2026", {}),
	("C4-2", "PURCHASE ORDER - 13.02.2026", {"supplier": "SRI SABAREE  YARNS"}),
	("C5-1", "Previous Month Pending Bills - Departmentwise", {}),
	("C5-2", "Previous Month Pending Bills - Departmentwise", {"assigned_to": "Accounts"}),
	("C6-1", "IO Input Pending", {"supplier": "S-0172"}),
	("C6-2", "IO Input Pending", {"supplier": "S-0174"}),
]


def builder(report_name, extra_filters):
	import frappe
	from frappe.desk import reportview

	report = frappe.get_doc("Report", report_name)
	settings = json.loads(report.json)
	fields = [f"`tab{dt}`.`{field}`" for field, dt in settings["fields"] if field != "_aggregate_column"]
	filters = [f[:4] for f in settings["filters"]]
	filters += [[report.ref_doctype, key, "=", value] for key, value in extra_filters.items()]
	group = settings.get("group_by")
	args = frappe._dict(
		doctype=report.ref_doctype,
		fields=fields,
		filters=filters,
		order_by=settings["order_by"],
		page_length=settings["page_length"],
		start=0,
	)
	if group:
		args.update(
			group_by=group["group_by"],
			aggregate_function=group["aggregate_function"],
			aggregate_on_doctype=report.ref_doctype,
			aggregate_on_field="name",
			order_by="_aggregate_column desc",
		)
	# Use each version's Report Builder aggregate adapter, as the Desk UI does.
	reportview.validate_args(args)
	return reportview.execute(**args)


def child(side):
	sys.dont_write_bytecode = True
	import frappe

	bench = BENCHES / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site", sites_path=".")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("START TRANSACTION READ ONLY")
	sys.path.insert(0, str(BENCHES / "frappe-15/apps/essdee_sales"))
	try:
		for case, report, filters in CASES:
			result = {"case": case, "report": report, "filters": filters, "side": side}
			try:
				if case.startswith(("C3", "C4", "C5")):
					result["rows"] = builder(("SD YRP " if side == "target" else "") + report, filters)
				elif side == "target":
					slug = frappe.scrub("SD YRP " + report)
					module = importlib.import_module(f"essdee_yrp.essdee_yrp.report.{slug}.{slug}")
					data = module.execute(target_filters(case, filters))
					result["columns"], result["rows"] = data[:2]
					if len(data) > 2:
						result["message"] = data[2]
				elif case.startswith("C1"):
					module = importlib.import_module(
						"essdee_sales.sales_order_management.doctype.order.order"
					)
					result["page"] = module.get_all_pending_items(warehouse_list=filters.get("warehouse", []))
				elif case.startswith("C2"):
					module = importlib.import_module(
						"essdee_sales.sales_order_management.doctype.packing_slip.packing_slip"
					)
					result["page"] = module.make_datewise_pack_slip_report(**filters)
				else:
					module = importlib.import_module(
						"production_api.production_api.doctype.sewing_plan.sewing_plan"
					)
					result["page"] = module.get_io_input_pending_data(**filters)
					result["rows"] = result["page"]["rows"]
				result["status"] = "executed"
			except Exception as exc:
				result.update(status="error", error=f"{type(exc).__name__}: {exc}")
			(OUT / f"worker5-{case}-{side}.json").write_text(json.dumps(result, default=str, indent=2) + "\n")
	finally:
		frappe.db.rollback()
		frappe.destroy()


def target_filters(case, filters):
	"""YRP Packing Slip filters whole posting dates; the source page takes datetimes."""
	if case.startswith("C2"):
		return {key: value[:10] for key, value in filters.items()}
	return filters


def sized_row(item, attributes, kind, sizes):
	attributes = {key: value for key, value in attributes.items() if value is not None}
	sizes = {key: float(value) for key, value in sizes.items() if value}
	return dict(item=item, attributes=attributes, type=kind, sizes=sizes)


def page_rows(page, case):
	"""Flatten the source OMS page matrix into one row per item group and kind."""
	kinds = ["Order", "Stock"] if page.get("show_stock") else ["Order"]
	rows = []
	for detail in page["data"]:
		order = {key: value for key, value in detail["qty"].items() if key != "stock"}
		stock = {
			key: value.get("val", 0) if isinstance(value, dict) else value
			for key, value in detail["qty"].get("stock", {}).items()
		}
		for kind, sizes in zip(kinds, [order, stock], strict=False):
			sizes = {("Quantity" if key == "default" else key): value for key, value in sizes.items()}
			rows.append(sized_row(detail["item_name"], detail["attribute_values"], kind, sizes))
	if case.startswith("C2"):
		for row in rows:
			row["type"] = None
	return rows


def matrix_rows(columns, rows):
	"""Read the Desk size matrix back into labelled attributes and sizes."""
	labels = {column["fieldname"]: column["label"] for column in columns}
	result = []
	for row in rows:
		attributes = {labels[key]: value for key, value in row.items() if key.startswith("secondary_")}
		sizes = {
			labels[key]: value for key, value in row.items() if key.startswith("size_") or key == "quantity"
		}
		result.append(sized_row(row["item"], attributes, row.get("type"), sizes))
	return result


def sort_rows(rows):
	return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str))


def compare(case, source, target):
	"""Compare successful executions; anything else is an execution error."""
	if source["status"] != "executed" or target["status"] != "executed":
		return dict(
			rows_equal=None,
			status="execution error",
			source_error=source.get("error"),
			target_error=target.get("error"),
		)
	if case.startswith(("C1", "C2")):
		a = sort_rows(page_rows(source["page"], case))
		b = sort_rows(matrix_rows(target["columns"], target["rows"]))
	else:
		a, b = normalise(source["rows"], case, "source"), normalise(target["rows"], case, "target")
	return dict(
		rows_equal=a == b,
		status="equal" if a == b else "mismatch pending fixing round",
		normalised={"source": a, "target": b},
	)


def exit_status(summary):
	return 0 if all(entry["rows_equal"] is True for entry in summary) else 1


def normalise(rows, case, side):
	result = []
	for row in rows:
		row = dict(row)
		if case.startswith("C6"):
			row.pop("serial_no", None)
		if side == "target" and case.startswith(("C3", "C4")):
			row["po_date"] = row.pop("transaction_date")
			row["status"] = {"Received": "Delivered", "Partially Received": "Partially Delivered"}.get(
				row.get("status"), row.get("status")
			)
			row["open_status"] = {"Close": "Closed"}.get(row.get("open_status"), row.get("open_status"))
		result.append(row)
	return sorted(result, key=lambda row: json.dumps(row, sort_keys=True, default=str))


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--child", choices=["source", "target"])
	args = parser.parse_args()
	if args.child:
		child(args.child)
		return
	OUT.mkdir(parents=True, exist_ok=True)
	for side, bench in [("source", "frappe-15"), ("target", "frappe-16")]:
		subprocess.run(
			[str(BENCHES / bench / "env/bin/python"), str(Path(__file__).resolve()), "--child", side],
			check=True,
		)
	summary = []
	for case, report, filters in CASES:
		source, target = [
			json.loads((OUT / f"worker5-{case}-{side}.json").read_text()) for side in ("source", "target")
		]
		entry = dict(
			case=case,
			report=report,
			filters=filters,
			source_status=source["status"],
			target_status=target["status"],
			source_rows=len(source.get("rows", [])),
			target_rows=len(target.get("rows", [])),
		)
		entry.update(compare(case, source, target))
		if "normalised" in entry:
			(OUT / f"worker5-{case}-normalised.json").write_text(
				json.dumps(entry.pop("normalised"), indent=2, default=str) + "\n"
			)
		summary.append(entry)
	(OUT / "worker5-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
	print(json.dumps(summary, indent=2))
	return exit_status(summary)


if __name__ == "__main__":
	sys.exit(main())
