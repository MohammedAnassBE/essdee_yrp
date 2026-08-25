"""Small, deterministic state helpers shared by finishing workflow services."""

import frappe

from essdee_yrp.finishing.parsing import json_object
from yrp.utils import update_if_string_instance


DETAIL_FIELDS = (
	"cutting_qty",
	"inward_quantity",
	"delivered_quantity",
	"accepted_qty",
	"dc_qty",
	"lot_transferred",
	"ironing_excess",
	"reworked",
	"return_qty",
	"pack_return_qty",
	"return_dc_qty",
	"pack_dc_qty",
	"transferred_qty",
	"rejected_qty",
)


def get_finishing_plan_dict(doc):
	"""Index Finishing Plan Detail rows by variant and set combination.

	The key contract is retained from Frappe 15 because Stock Entry ironing
	excess rows use the same variant + combination identity.
	"""
	finishing_items = {}
	for row in doc.get("finishing_plan_details") or []:
		set_combination = json_object(row.get("set_combination"))
		key = (row.get("item_variant"), tuple(sorted(set_combination.items())))
		values = {fieldname: row.get(fieldname) or 0 for fieldname in DETAIL_FIELDS}
		values.update(
			{
				"received_types": update_if_string_instance(row.get("received_type_json")) or {},
				"set_combination": row.get("set_combination"),
			}
		)
		finishing_items[key] = values
	return finishing_items


def get_finishing_plan_list(finishing_items):
	"""Convert the indexed representation back to child-table dictionaries."""
	rows = []
	for (item_variant, _tuple_attributes), values in finishing_items.items():
		row = {
			"item_variant": item_variant,
			"set_combination": values["set_combination"],
			"received_type_json": frappe.json.dumps(values["received_types"]),
		}
		row.update({fieldname: values[fieldname] for fieldname in DETAIL_FIELDS})
		rows.append(row)
	return rows


def get_finishing_rework_dict(doc):
	"""Index Finishing Plan rework rows by variant and set combination."""
	rework_items = {}
	for row in doc.get("finishing_plan_reworked_details") or []:
		set_combination = json_object(row.get("set_combination"))
		key = (row.get("item_variant"), tuple(sorted(set_combination.items())))
		rework_items[key] = {
			"quantity": row.get("quantity") or 0,
			"reworked_quantity": row.get("reworked_quantity") or 0,
			"rejected_qty": row.get("rejected_qty") or 0,
			"set_combination": row.get("set_combination"),
		}
	return rework_items


def get_finishing_rework_list(rework_items):
	"""Convert the indexed rework representation back to child rows."""
	return [
		{
			"item_variant": item_variant,
			"set_combination": values["set_combination"],
			"quantity": values["quantity"],
			"reworked_quantity": values["reworked_quantity"],
			"rejected_qty": values["rejected_qty"],
		}
		for (item_variant, _tuple_attributes), values in rework_items.items()
	]
