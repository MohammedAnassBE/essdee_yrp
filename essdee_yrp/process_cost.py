"""Essdee Lot/IPD adapters for the base YRP Process Cost DocType."""

import frappe
from frappe import _

from yrp.utils import update_if_string_instance


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_attributes(doctype, txt, searchfield, start, page_len, filters):
	if doctype != "Item Attribute":
		return []
	filters = frappe._dict(filters or {})
	if not filters.item or not filters.lot or not filters.process:
		return []
	_check_process_cost_permissions(
		item=filters.item,
		lot=filters.lot,
		process_name=filters.process,
	)

	ipd_name = frappe.db.get_value("Lot", filters.lot, "production_detail")
	if not ipd_name:
		return []
	frappe.has_permission("Item Production Detail", "read", doc=ipd_name, throw=True)
	ipd = frappe.get_cached_doc("Item Production Detail", ipd_name)
	process_name = filters.process
	attributes = []
	if ipd.cutting_process == process_name:
		attributes = [ipd.stiching_attribute, ipd.packing_attribute]
	elif ipd.stiching_process == process_name:
		attributes = [ipd.packing_attribute, ipd.primary_item_attribute]
		if ipd.is_set_item:
			attributes.append(ipd.set_item_attribute)
	elif ipd.packing_process == process_name:
		attributes = [ipd.primary_item_attribute]
	elif not frappe.db.get_value("Process", process_name, "is_group"):
		for row in ipd.get("ipd_processes") or []:
			if row.process_name != process_name:
				continue
			if row.stage == ipd.stiching_in_stage:
				attributes = [ipd.stiching_attribute, ipd.packing_attribute]
			elif row.stage == ipd.stiching_out_stage:
				attributes = [ipd.packing_attribute, ipd.primary_item_attribute]
			else:
				attributes = [ipd.primary_item_attribute]
			break
	else:
		item = frappe.get_cached_doc("Item", filters.item)
		attributes = [row.attribute for row in item.get("attributes") or []]

	seen = set()
	return [
		[attribute]
		for attribute in attributes
		if attribute
		and attribute not in seen
		and not seen.add(attribute)
		and (not txt or txt.lower() in attribute.lower())
	]


@frappe.whitelist()
def get_pc_attribute_values(
	item=None,
	attribute=None,
	lot=None,
	process_name=None,
):
	"""Return IPD-mapped values for the selected Lot and process.

	Base YRP also invokes this endpoint from its generic form handler with only
	``item`` and ``attribute``. Returning ``None`` for that generic invocation
	prevents it from racing and replacing the Lot-specific rows populated by the
	Essdee Desk handler.
	"""
	if not lot:
		return None
	if not attribute:
		return []
	_check_process_cost_permissions(item=item, lot=lot, process_name=process_name)

	ipd_name = frappe.db.get_value("Lot", lot, "production_detail")
	if not ipd_name:
		frappe.throw(_("Lot {0} has no Item Production Detail.").format(lot))
	frappe.has_permission("Item Production Detail", "read", doc=ipd_name, throw=True)
	ipd = frappe.get_cached_doc("Item Production Detail", ipd_name)
	mapping = next(
		(
			row.mapping
			for row in (ipd.get("item_attributes") or [])
			if row.attribute == attribute and row.mapping
		),
		None,
	)
	if not mapping:
		mapping = frappe.db.get_value(
			"Item Item Attribute",
			{
				"parent": ipd_name,
				"parenttype": "Item Production Detail",
				"attribute": attribute,
			},
			"mapping",
		)
	if not mapping:
		return []

	values = []
	if attribute == ipd.stiching_attribute and process_name != ipd.cutting_process:
		embellishments = update_if_string_instance(ipd.get("emblishment_details_json")) or {}
		for panel in embellishments.get(process_name, {}) or {}:
			values.append(panel)
	else:
		mapping_doc = frappe.get_cached_doc("Item Item Attribute Mapping", mapping)
		values = [row.attribute_value for row in mapping_doc.get("values") or []]

	return [
		{"attribute_value": value, "price": 0, "min_order_qty": 0}
		for value in dict.fromkeys(value for value in values if value)
	]


def _check_process_cost_permissions(*, item=None, lot=None, process_name=None):
	frappe.has_permission("Process Cost", "read", throw=True)
	for doctype, name in (
		("Item", item),
		("Lot", lot),
		("Process", process_name),
	):
		if name:
			frappe.has_permission(doctype, "read", doc=name, throw=True)
