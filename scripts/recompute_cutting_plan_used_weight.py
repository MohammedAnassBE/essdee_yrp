"""One-off: recompute SD YRP Cutting Plan cloth used/balance weights from Label Printed LaySheets.

Bundle generation used to persist the LaySheet's cloth usage on the plan and label printing then
added it again, so a printed LaySheet counted twice. Expected usage follows MRP/calc semantics:
Label Printed LaySheet cloth (weight - balance) and accessory cloth, plus submitted Recut panels.
Only V2/V3 plans are checked. No document is saved; only the two child-row fields are written.

Run from the bench directory:
	bench --site <site> console
	>>> exec(open("apps/essdee_yrp/scripts/recompute_cutting_plan_used_weight.py").read())
	>>> run()  # dry run, prints mismatched rows
	>>> run(cutting_plans=["CP-2610-00007"])  # limit to plans
	>>> run(since="2026-10-01")  # plans with a LaySheet printed since a date
	>>> run(dry_run=False)  # writes and commits
"""

import frappe
from frappe.utils import flt
from yrp.attribute_links import value as attribute_value


def cloth_key(colour, cloth_type, dia):
	return (attribute_value(colour), cloth_type, attribute_value(dia))


def get_expected_used_weights(cutting_plan):
	used = {}

	def add(key, weight):
		used[key] = used.get(key, 0) + flt(weight)

	laysheets = frappe.get_all(
		"SD YRP Cutting LaySheet",
		filters={"cutting_plan": cutting_plan, "status": "Label Printed"},
		pluck="name",
	)
	for name in laysheets:
		laysheet = frappe.get_doc("SD YRP Cutting LaySheet", name)
		for row in laysheet.cutting_laysheet_details:
			add(
				cloth_key(row.colour, row.cloth_type, row.actual_dia),
				flt(row.weight) - flt(row.balance_weight),
			)
		for row in laysheet.cutting_laysheet_accessory_details:
			add(cloth_key(row.colour, row.cloth_type, row.actual_dia), row.weight)

	recuts = frappe.get_all(
		"SD YRP Recut and Print Panel",
		filters={"cutting_plan": cutting_plan, "docstatus": 1},
		pluck="name",
	)
	for name in recuts:
		for row in frappe.get_doc("SD YRP Recut and Print Panel", name).recut_and_print_panel_details:
			add(cloth_key(row.colour, row.cloth_type, row.dia), row.weight)
	return used


def get_cutting_plans(cutting_plans=None, since=None):
	filters = {"docstatus": 1, "version": ["in", ("V2", "V3")]}
	if cutting_plans:
		filters["name"] = ["in", cutting_plans]
	if since:
		printed = frappe.get_all(
			"SD YRP Cutting LaySheet",
			filters={"status": "Label Printed", "printed_time": [">=", since], "cutting_plan": ["is", "set"]},
			pluck="cutting_plan",
			distinct=True,
		)
		filters["name"] = ["in", sorted(set(printed) & set(cutting_plans or printed))]
	return frappe.get_all("SD YRP Cutting Plan", filters=filters, pluck="name", order_by="creation")


def get_mismatches(cutting_plan):
	expected = get_expected_used_weights(cutting_plan)
	rows = frappe.get_all(
		"SD YRP Cutting Plan Cloth Detail",
		filters={"parent": cutting_plan, "parenttype": "SD YRP Cutting Plan"},
		fields=["name", "colour", "cloth_type", "dia", "weight", "used_weight"],
	)
	mismatches = []
	for row in rows:
		used_weight = flt(expected.get(cloth_key(row.colour, row.cloth_type, row.dia)), 3)
		if abs(used_weight - flt(row.used_weight, 3)) > 0.001:
			mismatches.append((row, used_weight))
	return mismatches


def run(dry_run=True, cutting_plans=None, since=None):
	changed = 0
	for cutting_plan in get_cutting_plans(cutting_plans, since):
		for row, used_weight in get_mismatches(cutting_plan):
			changed += 1
			print(
				f"{cutting_plan}\t{attribute_value(row.colour)}\t{row.cloth_type}\t{attribute_value(row.dia)}"
				f"\tstored {flt(row.used_weight, 3)} -> {used_weight}"
			)
			if not dry_run:
				frappe.db.set_value(
					"SD YRP Cutting Plan Cloth Detail",
					row.name,
					{"used_weight": used_weight, "balance_weight": flt(flt(row.weight) - used_weight, 3)},
					update_modified=False,
				)
	if dry_run:
		frappe.db.rollback()
	else:
		frappe.db.commit()
	print(f"{changed} row(s) {'would change' if dry_run else 'updated'}")
