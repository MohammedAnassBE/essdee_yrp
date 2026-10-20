"""Read-only MRP/ERP Audit Pending parity, including the persisted status clock.

Run with frappe-16/env/bin/python scripts/audit_pending_finishing_parity.py
--output /absolute/evidence/path. Each export uses its bench's interpreter and
a READ ONLY database transaction. No source or target rows are changed.
"""
import argparse
import importlib
import json
import math
import os
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BENCHES = Path("/home/anas/pilot/benches")
KNOWN_PLAN = "FP-2627-00051"


def write_json(path, value):
	path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def compare_payloads(source, target):
	differences = []
	queues = {}
	for queue, left in source["queues"].items():
		right = target["queues"].get(queue, {})
		left_rows = {r["name"]: r for r in left["plans"]}
		right_rows = {r["name"]: r for r in right.get("plans", [])}
		checks = {"summary_equal": left["summary"] == right.get("summary"),
			"plan_names_equal": left_rows.keys() == right_rows.keys(),
			"dates_and_ages_equal_on_shared_plans": all(
				all(left_rows[n].get(f) == right_rows[n].get(f) for f in ("fp_status", "status_since", "age_days"))
				for n in left_rows.keys() & right_rows.keys()),
			"plans_compared": len(left_rows.keys() & right_rows.keys()),
			"mrp_summary": left["summary"], "erp_summary": right.get("summary")}
		if not checks["summary_equal"]:
			differences.append({"queue": queue, "field": "summary", "mrp": left["summary"], "erp": right.get("summary")})
		if not checks["plan_names_equal"]:
			differences.append({"queue": queue, "mrp_only": sorted(left_rows.keys() - right_rows.keys()), "erp_only": sorted(right_rows.keys() - left_rows.keys())})
		fields = ("fp_status", "status_since", "age_days", "total_cut", "sewing_received", "packed", "dispatched")
		for name in sorted(left_rows.keys() & right_rows.keys()):
			for field in fields:
				a, b = left_rows[name].get(field), right_rows[name].get(field)
				# SQL Float sums can differ below their display/storage precision.
				equal = math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9) if field in (
					"total_cut", "sewing_received", "packed", "dispatched"
				) and isinstance(a, (int, float)) and isinstance(b, (int, float)) else a == b
				if not equal:
					differences.append({"queue": queue, "plan": name, "field": field, "mrp": a, "erp": b})
		queues[queue] = checks
	for name in sorted(source["status_dates"].keys() | target["status_dates"].keys()):
		a, b = source["status_dates"].get(name), target["status_dates"].get(name)
		if a != b:
			differences.append({"plan": name, "field": "persisted_status_date", "mrp": a, "erp": b})
	for name in sorted(source["pending"].keys() | target["pending"].keys()):
		a, b = source["pending"].get(name), target["pending"].get(name)
		if a != b:
			differences.append({"plan": name, "field": "pending_breakdown", "mrp": a, "erp": b})
	return {"equal": not differences, "queues": queues,
		"source_plan_count": len(source["status_dates"]), "target_plan_count": len(target["status_dates"]),
		"status_dates_compared": len(source["status_dates"].keys() & target["status_dates"].keys()),
		"matching_status_dates": sum(v == target["status_dates"].get(n) for n, v in source["status_dates"].items()),
		"pending_equal": source["pending"] == target["pending"],
		"pending_plans_compared": list(source["pending"]), "differences": differences}


def export(side, output, as_of):
	import frappe
	from frappe.utils import get_datetime

	bench = BENCHES / ("frappe-15" if side == "mrp" else "frappe-16")
	os.chdir(bench / "sites")
	frappe.init(site="mrp3.site" if side == "mrp" else "erp-migration-test.site")
	frappe.connect()
	frappe.set_user("Administrator")
	frappe.db.sql("SET SESSION TRANSACTION READ ONLY")
	try:
		module = importlib.import_module(
			"production_api.production_api.page.audit_pending_finishing_plans.audit_pending_finishing_plans"
			if side == "mrp" else "essdee_yrp.accounts.audit_pending"
		)
		with patch.object(module, "now_datetime", return_value=get_datetime(as_of)):
			queues = {name: module.get_dashboard_data(show_partially_dispatched=partial)
				for name, partial in (("default", False), ("partial", True))}
		if side == "mrp":
			plans = frappe.get_all("Finishing Plan", fields=["name", "fp_status"], limit_page_length=0)
			versions = frappe.get_all("Version", filters={"ref_doctype": "Finishing Plan"},
				fields=["docname", "creation", "data"], limit_page_length=0)
			dates = module._find_status_since(plans, versions)
			plan_names = list(dict.fromkeys([KNOWN_PLAN] + [r["name"] for r in queues["default"]["plans"][:5]]))
			write_json(output / "pending-plan-names.json", plan_names)
		else:
			plans = frappe.get_all("SD YRP Finishing Plan", fields=["name", "fp_status", "fp_status_since"], limit_page_length=0)
			dates = {p.name: p.fp_status_since for p in plans if p.fp_status_since}
			plan_names = json.loads((output / "pending-plan-names.json").read_text())
		status_dates = {p.name: {"fp_status": p.fp_status or "", "status_since": str(dates[p.name]) if p.name in dates else None} for p in plans}
		pending = {name: module.get_pending_breakdown(name) for name in plan_names}
		write_json(output / f"{side}.json", {"as_of": as_of, "queues": queues, "status_dates": status_dates, "pending": pending})
	finally:
		frappe.db.rollback()
		frappe.destroy()


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--export", choices=("mrp", "erp"))
	parser.add_argument("--as-of", default=datetime.now().isoformat(sep=" ", timespec="seconds"))
	parser.add_argument("--compare-only", action="store_true")
	args = parser.parse_args()
	args.output = args.output.resolve()
	args.output.mkdir(parents=True, exist_ok=True)
	if args.export:
		export(args.export, args.output, args.as_of)
		return
	if not args.compare_only:
		for side, version in (("mrp", "frappe-15"), ("erp", "frappe-16")):
			subprocess.run([str(BENCHES / version / "env/bin/python"), str(Path(__file__).resolve()),
				"--output", str(args.output), "--as-of", args.as_of, "--export", side], check=True)
	source, target = [json.loads((args.output / f"{side}.json").read_text()) for side in ("mrp", "erp")]
	result = compare_payloads(source, target)
	known = source["pending"].get(KNOWN_PLAN)
	if known:
		result["known_plan"] = {"plan": KNOWN_PLAN,
			"status_since": source["status_dates"][KNOWN_PLAN]["status_since"],
			"rejected": {p["name"]: next(c["total"] for c in p["categories"] if c["key"] == "rejected") for p in known["parts"]}}
		assert result["known_plan"]["status_since"].startswith("2026-05-15"), result["known_plan"]
		assert result["known_plan"]["rejected"] == {"Top": 6.0, "Bottom": 7.0}, result["known_plan"]
	write_json(args.output / "summary.json", result)
	print(json.dumps(result, indent=2))
	raise SystemExit(0 if result["equal"] else 1)


if __name__ == "__main__":
	main()
