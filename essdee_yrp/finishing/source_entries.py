"""Ironing Excess and Old Lot entries of a Finishing Plan and the DC made from each."""

import frappe
from frappe import _
from frappe.utils import cstr, flt, now_datetime
from yrp.attribute_links import value as _attribute_value
from yrp.utils import update_if_string_instance

from essdee_yrp.finishing import views

SOURCE_LISTS = {
	"ironing_excess_list": ("YRP Stock Entry", "against_id"),
	"lot_transfer_list": ("SD YRP Lot Transfer", "finishing_plan"),
}
EXISTING_DC = "existing"
DC_FIELD = "finishing_source_entry"


def get_raw_entries(value) -> dict:
	"""Stored list as written: values are a datetime string (old) or a {datetime, dc} dict."""
	entries = update_if_string_instance(value) or {}
	if not isinstance(entries, dict):
		frappe.throw(_("Finishing source entry list must be a JSON object"))
	return entries


def normalize_entry(value) -> dict:
	if isinstance(value, dict):
		return {"datetime": cstr(value.get("datetime")), "dc": cstr(value.get("dc"))}
	return {"datetime": cstr(value), "dc": ""}


def get_entries(value) -> dict:
	return {name: normalize_entry(entry) for name, entry in get_raw_entries(value).items()}


def new_entry() -> dict:
	return {"datetime": now_datetime().strftime("%d-%m-%Y %H:%M:%S"), "dc": ""}


def get_entry_quantities(doc, rows, context=None) -> dict:
	"""Map source rows to the Create DC matrix shape: {colour: {size: qty}}."""
	context = context or views.get_ipd_context(doc)
	quantities = {}
	for row in rows:
		identity = views._row_identity(
			frappe._dict(item_variant=row.item, set_combination=row.set_combination), context
		)
		sizes = quantities.setdefault(_attribute_value(identity.colour), {})
		size = _attribute_value(identity.size)
		sizes[size] = flt(sizes.get(size)) + flt(row.qty)
	return quantities


def get_source_entries(doc, list_key) -> list[dict]:
	"""Submitted entries of one list with their DC marker and quantities for the /web tab."""
	doctype, _plan_field = SOURCE_LISTS[list_key]
	entries = get_entries(doc.get(list_key))
	if not entries:
		return []
	context = views.get_ipd_context(doc)
	result = []
	for name, entry in entries.items():
		source = frappe.get_doc(doctype, name)
		if source.docstatus != 1:
			continue
		rows = source.get("items") or []
		result.append(
			{
				"name": name,
				"doctype": doctype,
				"date": entry["datetime"],
				"dc": entry["dc"],
				"total_qty": sum(flt(row.qty) for row in rows),
				"quantities": get_entry_quantities(doc, rows, context),
			}
		)
	return result


def get_source_list_key(doc, source_entry) -> str:
	"""Return the list holding ``source_entry`` and fail if it already has a DC."""
	for list_key in SOURCE_LISTS:
		entries = get_entries(doc.get(list_key))
		if source_entry not in entries:
			continue
		if entries[source_entry]["dc"]:
			frappe.throw(
				_("A Delivery Challan is already linked to {0}: {1}").format(
					source_entry, entries[source_entry]["dc"]
				)
			)
		return list_key
	frappe.throw(_("{0} is not an Ironing Excess or Old Lot entry of {1}.").format(source_entry, doc.name))


def get_source_plan(source_entry):
	for list_key, (doctype, plan_field) in SOURCE_LISTS.items():
		plan = frappe.db.get_value(doctype, source_entry, plan_field)
		if plan:
			return plan, list_key
	frappe.throw(_("Finishing source entry {0} was not found.").format(source_entry))


def set_entry_dc(delivery_challan, *, cancelled):
	"""Write or clear the DC marker on the entry the DC was created from."""
	source_entry = delivery_challan.get(DC_FIELD)
	if not source_entry:
		return
	plan, list_key = get_source_plan(source_entry)
	finishing_doc = frappe.get_doc("SD YRP Finishing Plan", plan)
	entries = get_raw_entries(finishing_doc.get(list_key))
	if source_entry not in entries:
		if cancelled:
			return
		frappe.throw(_("{0} is no longer an entry of Finishing Plan {1}.").format(source_entry, plan))
	entry = normalize_entry(entries[source_entry])
	if cancelled:
		if entry["dc"] != delivery_challan.name:
			return
		entry["dc"] = ""
	else:
		if entry["dc"] and entry["dc"] != delivery_challan.name:
			frappe.throw(_("{0} already has Delivery Challan {1}.").format(source_entry, entry["dc"]))
		entry["dc"] = delivery_challan.name
	entries[source_entry] = entry
	finishing_doc.db_set(list_key, frappe.as_json(entries))
