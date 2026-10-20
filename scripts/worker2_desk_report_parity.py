"""Compare worker 2 Desk reports against mrp3.site, without writing either site.

Run with frappe-16/env/bin/python scripts/worker2_desk_report_parity.py.
--staged uses Report JSON files without importing them; coordinator owns migration.
An exit code of 1 means real output differences remain, including data drift.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BENCHES = Path("/home/anas/pilot/benches")
REPORT_ROOT = BENCHES / "frappe-16/apps/essdee_yrp/essdee_yrp/essdee_yrp/report"
CASES = [
	("C1-1", "PURCHASE ORDER", {}),
	("C1-2", "PURCHASE ORDER", {"supplier": "SRI SABAREE  YARNS"}),
	("C2-1", "PURCHASE ORDER - 13.02.2026", {}),
	("C2-2", "PURCHASE ORDER - 13.02.2026", {"supplier": "SRI SABAREE  YARNS"}),
	("C1-cancelled", "PURCHASE ORDER", {"status": "Cancelled"}),
	("C1-draft", "PURCHASE ORDER", {"status": "Draft"}),
	("C2-cancelled", "PURCHASE ORDER - 13.02.2026", {"status": "Cancelled"}),
	("C2-draft", "PURCHASE ORDER - 13.02.2026", {"status": "Draft"}),
	("C3-1", "Previous Month Pending Bills - Departmentwise", {}),
	("C3-2", "Previous Month Pending Bills - Departmentwise", {"assigned_to": "Accounts"}),
	("C4-1", "IO Input Pending", {"supplier": "S-0172"}),
	("C4-2", "IO Input Pending", {"supplier": "S-0174"}),
]


def builder(report, filters):
	import frappe
	from frappe.desk import reportview

	settings = json.loads(report.json)
	args = frappe._dict(
		doctype=report.ref_doctype,
		fields=[f"`tab{dt}`.`{field}`" for field, dt in settings["fields"] if field != "_aggregate_column"],
		filters=[f[:4] for f in settings["filters"]]
		+ [[report.ref_doctype, k, "=", v] for k, v in filters.items()],
		order_by=settings["order_by"],
		page_length=settings["page_length"],
		start=0,
	)
	if settings.get("group_by"):
		args.update(
			group_by=settings["group_by"]["group_by"],
			aggregate_function=settings["group_by"]["aggregate_function"],
			aggregate_on_doctype=report.ref_doctype,
			aggregate_on_field="name",
			order_by="_aggregate_column desc",
		)
	reportview.validate_args(args)
	rows = reportview.execute(**args)
	columns = []
	for field, dt in settings["fields"]:
		if field == "docstatus":
			continue  # Report Builder keeps docstatus in data, but hides its column.
		df = frappe.get_meta(dt).get_field(field)
		label = "ID" if field == "name" else (df.label if df else field)
		columns.append(
			dict(fieldname=field, label=label, width=settings.get("column_widths", {}).get(field, 120))
		)
	return columns, rows


def report_definition(name, staged):
	import frappe

	if staged:
		slug = frappe.scrub(name)
		return frappe.get_doc(json.loads((REPORT_ROOT / slug / f"{slug}.json").read_text()))
	return frappe.get_doc("Report", name)


def child(side, out, staged):
	import frappe

	bench = BENCHES / ("frappe-15" if side == "source" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "source" else "erp-migration-test.site", sites_path=".")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("START TRANSACTION READ ONLY")
	try:
		for case, name, filters in CASES:
			result = dict(case=case, report=name, filters=filters, side=side)
			try:
				if side == "source" and case.startswith("C4"):
					from production_api.production_api.doctype.sewing_plan.sewing_plan import (
						get_io_input_pending_data,
					)

					page = get_io_input_pending_data(**filters)
					result.update(rows=page["rows"], totals=page["totals"])
				else:
					report = report_definition(
						("SD YRP " if side == "target" else "") + name, staged and side == "target"
					)
					result["report_type"] = report.report_type
					while report.report_type == "Custom Report":
						report = report_definition(report.reference_report, staged)
					if report.report_type == "Report Builder":
						columns, rows = builder(report, filters)
					else:
						# Execute the same standard controller that Desk dispatches to.
						columns, rows = report.execute_module(frappe._dict(filters))[:2]
					result.update(columns=columns, rows=rows)
				result["status"] = "executed"
			except Exception as exc:
				result.update(status="error", error=f"{type(exc).__name__}: {exc}")
			(out / f"{case}-{side}.json").write_text(json.dumps(result, default=str, indent=2) + "\n")
	finally:
		frappe.db.rollback()
		frappe.destroy()


def comparable_rows(payload, case):
	rows = [dict(row) for row in payload.get("rows", [])]
	if case.startswith("C4"):
		for row in rows:
			row.pop("serial_no", None)
	return rows


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--child", choices=["source", "target"])
	parser.add_argument("--staged", action="store_true")
	parser.add_argument("--out", type=Path, default=Path("/home/anas/report-build/port/parity/worker2/after"))
	args = parser.parse_args()
	args.out.mkdir(parents=True, exist_ok=True)
	if args.child:
		child(args.child, args.out, args.staged)
		return 0
	for side, bench in [("source", "frappe-15"), ("target", "frappe-16")]:
		cmd = [
			str(BENCHES / bench / "env/bin/python"),
			str(Path(__file__).resolve()),
			"--child",
			side,
			"--out",
			str(args.out),
		]
		if args.staged:
			cmd.append("--staged")
		subprocess.run(cmd, check=True)
	summary = []
	for case, name, filters in CASES:
		source, target = [
			json.loads((args.out / f"{case}-{s}.json").read_text()) for s in ("source", "target")
		]
		a, b = comparable_rows(source, case), comparable_rows(target, case)
		entry = dict(
			case=case,
			report=name,
			filters=filters,
			source_rows=len(a),
			target_rows=len(b),
			source_status=source["status"],
			target_status=target["status"],
			staged=args.staged,
		)
		if source["status"] != "executed" or target["status"] != "executed":
			entry.update(equal=False, source_error=source.get("error"), target_error=target.get("error"))
		else:
			columns_equal = True
			if case.startswith(("C1", "C2")):

				def select(cols):
					return [{k: c[k] for k in ("fieldname", "label", "width")} for c in cols]

				columns_equal = select(source["columns"]) == select(target["columns"])
			# Check order as well as values; a bag comparison can hide a sorting regression.
			entry.update(rows_equal=a == b, columns_equal=columns_equal, equal=a == b and columns_equal)
			key = (
				(lambda r: r["name"])
				if case.startswith(("C1", "C2"))
				else (
					(lambda r: r["assigned_to"])
					if case.startswith("C3")
					else (lambda r: (r["sewing_line"], r["lot"], r["item"]))
				)
			)
			x, y = {key(r): r for r in a}, {key(r): r for r in b}
			differing_keys = {k for k in dict.fromkeys([*x, *y]) if x.get(k) != y.get(k)}
			entry["differences"] = [
				dict(key=k, source=x.get(k), target=y.get(k))
				for k in dict.fromkeys([*x, *y])
				if k in differing_keys
			]
			entry["unchanged_records_equal_and_ordered"] = [
				row for row in a if key(row) not in differing_keys
			] == [row for row in b if key(row) not in differing_keys]
		summary.append(entry)
	(args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
	print(json.dumps(summary, indent=2))
	return 0 if all(row["equal"] for row in summary) else 1


if __name__ == "__main__":
	sys.exit(main())
