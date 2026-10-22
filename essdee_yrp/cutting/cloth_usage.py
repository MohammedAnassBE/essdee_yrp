import frappe
from frappe.utils import flt
from yrp.attribute_links import value as _attribute_value

PLAN_CLOTH_DETAIL = "SD YRP Cutting Plan Cloth Detail"


def recompute_cutting_plan_cloth_usage(cutting_plan):
	"""Set the plan's cloth and accessory used weight from its Label Printed LaySheets, each counted once.

	Matching follows apply_laysheet_to_parent (MRP update_cutting_plan): V2/V3 match cloth on the
	LaySheet's actual dia and accessory rows on (accessory, colour, cloth type, dia); V1 matches both
	on (colour, cloth type, dia). Submitted Recut and Print Panels add to cloth rows, as calc() does.
	"""
	is_v1 = frappe.db.get_value("SD YRP Cutting Plan", cutting_plan, "version") not in ("V2", "V3")
	cloth_used = get_laysheet_cloth_usage(cutting_plan, dia_field="dia" if is_v1 else "actual_dia")
	accessory_used = {}
	for row in get_laysheet_accessory_usage(cutting_plan):
		cloth_key = _key(row.colour, row.cloth_type, row.dia if is_v1 else row.actual_dia)
		accessory_key = cloth_key if is_v1 else (row.accessory, *_key(row.colour, row.cloth_type, row.dia))
		cloth_used[cloth_key] = cloth_used.get(cloth_key, 0) + flt(row.weight)
		accessory_used[accessory_key] = accessory_used.get(accessory_key, 0) + flt(row.weight)
	for key, weight in get_recut_cloth_usage(cutting_plan).items():
		cloth_used[key] = cloth_used.get(key, 0) + weight

	for row in frappe.get_all(
		PLAN_CLOTH_DETAIL,
		filters={"parent": cutting_plan, "parenttype": "SD YRP Cutting Plan"},
		fields=["name", "parentfield", "accessory", "colour", "cloth_type", "dia", "weight"],
	):
		key = _key(row.colour, row.cloth_type, row.dia)
		if row.parentfield == "cutting_plan_cloth_details":
			used_weight = flt(cloth_used.get(key))
			values = {"used_weight": used_weight, "balance_weight": flt(row.weight) - used_weight}
		else:
			accessory_key = key if is_v1 else (row.accessory, *key)
			values = {"used_weight": flt(accessory_used.get(accessory_key))}
		frappe.db.set_value(PLAN_CLOTH_DETAIL, row.name, values, update_modified=False)


def get_laysheet_cloth_usage(cutting_plan, dia_field):
	rows = frappe.db.sql(
		f"""
		SELECT detail.colour, detail.cloth_type, detail.`{dia_field}` AS dia,
			SUM(IFNULL(detail.weight, 0) - IFNULL(detail.balance_weight, 0)) AS weight
		FROM `tabSD YRP Cutting LaySheet Detail` detail
		JOIN `tabSD YRP Cutting LaySheet` laysheet ON laysheet.name = detail.parent
		WHERE laysheet.cutting_plan = %(plan)s AND laysheet.status = 'Label Printed'
			AND detail.parenttype = 'SD YRP Cutting LaySheet'
			AND detail.parentfield = 'cutting_laysheet_details'
		GROUP BY detail.colour, detail.cloth_type, detail.`{dia_field}`
		""",
		{"plan": cutting_plan},
		as_dict=True,
	)
	usage = {}
	for row in rows:
		key = _key(row.colour, row.cloth_type, row.dia)
		usage[key] = usage.get(key, 0) + flt(row.weight)
	return usage


def get_laysheet_accessory_usage(cutting_plan):
	return frappe.db.sql(
		"""
		SELECT accessory.accessory, accessory.colour, accessory.cloth_type, accessory.dia,
			accessory.actual_dia, SUM(IFNULL(accessory.weight, 0)) AS weight
		FROM `tabSD YRP Cutting LaySheet Accessory Detail` accessory
		JOIN `tabSD YRP Cutting LaySheet` laysheet ON laysheet.name = accessory.parent
		WHERE laysheet.cutting_plan = %(plan)s AND laysheet.status = 'Label Printed'
			AND accessory.parenttype = 'SD YRP Cutting LaySheet'
			AND accessory.parentfield = 'cutting_laysheet_accessory_details'
		GROUP BY accessory.accessory, accessory.colour, accessory.cloth_type, accessory.dia,
			accessory.actual_dia
		""",
		{"plan": cutting_plan},
		as_dict=True,
	)


def get_recut_cloth_usage(cutting_plan):
	rows = frappe.db.sql(
		"""
		SELECT detail.colour, detail.cloth_type, detail.dia, SUM(IFNULL(detail.weight, 0)) AS weight
		FROM `tabSD YRP Recut and Print Panel Detail` detail
		JOIN `tabSD YRP Recut and Print Panel` recut ON recut.name = detail.parent
		WHERE recut.cutting_plan = %(plan)s AND recut.docstatus = 1
			AND detail.parenttype = 'SD YRP Recut and Print Panel'
		GROUP BY detail.colour, detail.cloth_type, detail.dia
		""",
		{"plan": cutting_plan},
		as_dict=True,
	)
	usage = {}
	for row in rows:
		key = _key(row.colour, row.cloth_type, row.dia)
		usage[key] = usage.get(key, 0) + flt(row.weight)
	return usage


def _key(colour, cloth_type, dia):
	return (_attribute_value(colour), cloth_type, _attribute_value(dia))
