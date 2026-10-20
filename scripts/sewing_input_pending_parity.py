"""Read-only IO parity for two suppliers, with exact Work Order drift evidence.

Run with frappe-16/env/bin/python. A raw mismatch always exits 1, even when the
same-eligibility diagnostic matches. The diagnostic only filters plan lists in
memory; it never changes Work Orders or data. It also exports Status Summary
with that scope for sewing_status_summary_parity.py --compare-only.
"""

import argparse
import importlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

SUPPLIERS = ["S-0172", "S-0174"]
BENCHES = Path("/home/anas/pilot/benches")


def write(path, value):
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def facts(erp, supplier):
	import frappe

	plan, wo = ("SD YRP Sewing Plan", "YRP Work Order") if erp else ("Sewing Plan", "Work Order")
	plans = frappe.db.sql(f"""select sp.name, sp.work_order, sp.lot, sp.item, sp.supplier,
		wo.supplier as wo_supplier, wo.docstatus, wo.open_status
		from `tab{plan}` sp join `tab{wo}` wo on wo.name = sp.work_order
		where sp.supplier = %(supplier)s order by sp.name""", {"supplier": supplier}, as_dict=True)
	quantities = frappe.db.sql(f"""select e.sewing_plan, e.input_type, e.work_station,
		sum(d.quantity) as quantity from `tab{plan} Entry Detail` e
		join `tab{plan} Detail` d on d.parent = e.name
		where e.sewing_plan in %(plans)s
		group by e.sewing_plan, e.input_type, e.work_station
		order by e.sewing_plan, e.input_type, e.work_station""",
		{"plans": [p.name for p in plans]}, as_dict=True) if plans else []
	return {"plans": plans, "quantities": quantities}


def export(side, output):
	import frappe

	erp = side == "erp"
	os.chdir(BENCHES / ("frappe-16" if erp else "frappe-15") / "sites")
	frappe.init(site="erp-migration-test.site" if erp else "mrp3.site")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("START TRANSACTION READ ONLY")
	try:
		payload = {}
		if erp:
			from essdee_yrp.essdee_yrp.report.sd_yrp_io_input_pending import sd_yrp_io_input_pending as io
			from essdee_yrp.sewing import read_models, reporting
			source = json.loads((output / "mrp-input.json").read_text())
		else:
			mrp = importlib.import_module("production_api.production_api.doctype.sewing_plan.sewing_plan")
		for supplier in SUPPLIERS:
			payload[supplier] = facts(erp, supplier)
			if erp:
				payload[supplier]["rows"] = io.execute({"supplier": supplier})[1]
				eligible = {p["name"] for p in source[supplier]["plans"] if p["open_status"] == "Open"}
				plans = [p for p in read_models._plans(supplier) if p.name in eligible]
				# Exercise the real query and assembly with an explicit, documented scope.
				with patch.object(io, "_plans", return_value=plans), patch.object(read_models, "_plans", return_value=plans):
					payload[supplier]["same_eligibility_rows"] = io.execute({"supplier": supplier})[1]
					if supplier == "S-0172":
						write(output / "same-eligibility-status" / "erp.json", reporting.status_summary(supplier))
			else:
				payload[supplier]["rows"] = mrp.get_io_input_pending_data(supplier)["rows"]
				if supplier == "S-0172":
					write(output / "same-eligibility-status" / "mrp.json", mrp.get_sp_status_summary(supplier))
		write(output / f"{side}-input.json", payload)
	finally:
		frappe.db.rollback()
		frappe.destroy()


def compare(output):
	a, b = [json.loads((output / f"{side}-input.json").read_text()) for side in ("mrp", "erp")]
	result = []
	for supplier in SUPPLIERS:
		left, right = a[supplier], b[supplier]
		clean = lambda rows: [{k: v for k, v in r.items() if k != "serial_no"} for r in rows]
		x, y = clean(left["rows"]), clean(right["rows"])
		lp, rp = [{r["name"]: r for r in side["plans"]} for side in (left, right)]
		changed = [name for name in sorted(lp.keys() | rp.keys()) if lp.get(name) != rp.get(name)]
		key = lambda r: (r["sewing_line"], r["lot"], r["item"])
		lx, rx = [{key(r): r for r in rows} for rows in (x, y)]
		result.append({
			"supplier": supplier, "mrp_rows": len(x), "erp_rows": len(y), "equal": x == y,
			"differences": [{"key": k, "mrp": lx.get(k), "erp": rx.get(k)}
				for k in sorted(lx.keys() | rx.keys()) if lx.get(k) != rx.get(k)],
			"plan_work_order_differences": [{"mrp": lp.get(n), "erp": rp.get(n)} for n in changed],
			"entry_quantities_equal": left["quantities"] == right["quantities"],
			"affected_plan_quantities": [r for r in left["quantities"] if r["sewing_plan"] in changed],
			"same_eligibility_diagnostic_equal": x == clean(right["same_eligibility_rows"]),
		})
	write(output / "input-summary.json", result)
	print(json.dumps(result, indent=2))
	return all(r["equal"] for r in result)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--export", choices=["mrp", "erp"])
	parser.add_argument("--compare-only", action="store_true")
	args = parser.parse_args()
	args.output = args.output.resolve()
	args.output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, args.output)
		return
	if not args.compare_only:
		for side, bench in (("mrp", "frappe-15"), ("erp", "frappe-16")):
			subprocess.run([str(BENCHES / bench / "env/bin/python"), str(Path(__file__).resolve()),
				"--export", side, "--output", str(args.output)], check=True)
	raise SystemExit(0 if compare(args.output) else 1)


if __name__ == "__main__":
	main()
