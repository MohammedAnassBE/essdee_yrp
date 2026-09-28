"""Essdee Lot/IPD adapters for the base YRP Process Cost DocType."""
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value

import frappe
from yrp.attribute_values import get_mapping_document
from frappe import _

from yrp.utils import update_if_string_instance


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_attributes(doctype, txt, searchfield, start, page_len, filters):
	if doctype != 'Item Attribute':
		return []
	filters = frappe._dict(filters or {})
	if not filters.item or not filters.lot or not filters.process:
		return []
	_check_process_cost_permissions(
		item=filters.item,
		lot=filters.lot,
		process_name=filters.process,
	)

	ipd_name = _resolve_ipd_name(filters.item, filters.lot, filters.process)
	if not ipd_name:
		return []
	frappe.has_permission('YRP Item Production Detail', "read", doc=ipd_name, throw=True)
	ipd = frappe.get_cached_doc('YRP Item Production Detail', ipd_name)
	process_name = filters.process
	attributes = []
	if ipd.get("is_cloth_item"):
		attributes = [row.attribute for row in ipd.get("item_attributes") or []]
	elif ipd.cutting_process == process_name:
		attributes = [ipd.stiching_attribute, ipd.packing_attribute]
	elif ipd.stiching_process == process_name:
		attributes = [ipd.packing_attribute, ipd.primary_item_attribute]
		if ipd.is_set_item:
			attributes.append(ipd.set_item_attribute)
	elif ipd.packing_process == process_name:
		attributes = [ipd.primary_item_attribute]
	elif not frappe.db.get_value('YRP Process', process_name, "is_group"):
		for row in ipd.get("ipd_processes") or []:
			if row.process_name != process_name:
				continue
			stage = _attribute_value(row.get("in_stage")) or row.get("stage")
			if stage == _attribute_value(ipd.stiching_in_stage):
				attributes = [ipd.stiching_attribute, ipd.packing_attribute]
			elif stage == _attribute_value(ipd.stiching_out_stage):
				attributes = [ipd.packing_attribute, ipd.primary_item_attribute]
			else:
				attributes = [ipd.primary_item_attribute]
			break
	else:
		item = frappe.get_cached_doc('Item', filters.item)
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
	for_link=0,
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

	ipd_name = _resolve_ipd_name(item, lot, process_name)
	if not ipd_name:
		frappe.throw(_("Lot {0} has no Item Production Detail.").format(lot))
	frappe.has_permission('YRP Item Production Detail', "read", doc=ipd_name, throw=True)
	ipd = frappe.get_cached_doc('YRP Item Production Detail', ipd_name)
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
			'YRP Item Item Attribute',
			{
				"parent": ipd_name,
				"parenttype": 'YRP Item Production Detail',
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
		mapping_doc = get_mapping_document(mapping, cached=True)
		values = [_attribute_value(row.attribute_value) for row in mapping_doc.get("values") or []]

	return [
		{"attribute_value": attribute_db.link(value, attribute) if frappe.utils.cint(for_link) else value, "price": 0, "min_order_qty": 0}
		for value in dict.fromkeys(value for value in values if value)
	]


def _check_process_cost_permissions(*, item=None, lot=None, process_name=None):
	frappe.has_permission('YRP Process Cost', "read", throw=True)
	for doctype, name in (
		('Item', item),
		('SD YRP Lot', lot),
		('YRP Process', process_name),
	):
		if name:
			frappe.has_permission(doctype, "read", doc=name, throw=True)


def _resolve_ipd_name(item, lot, process_name):
	if process_name and frappe.db.get_value("YRP Process", process_name, "is_cloth_process"):
		from essdee_yrp.api.work_order import _get_work_order_selection_context

		context = _get_work_order_selection_context(lot, process_name, check_permission=False)
		matches = [row for row in context["options"] if row["item"] == item]
		if len(matches) != 1:
			frappe.throw(_("Select a cloth Item configured for this Lot and Process."))
		return matches[0]["production_detail"]
	return attribute_db.get_value("SD YRP Lot", lot, "production_detail")


def before_validate(doc, method=None):
	if not doc.get("lot") or not doc.get("process_name"):
		return
	if frappe.db.get_value("YRP Process", doc.process_name, "is_cloth_process"):
		_resolve_ipd_name(doc.item, doc.lot, doc.process_name)
	else:
		# Preserve the previous garment Lot fetch while allowing an explicit
		# cloth Item for processes that use the Lot's separate cloth IPDs.
		doc.item = attribute_db.get_value("SD YRP Lot", doc.lot, "item")
		if doc.item:
			doc.uom = frappe.db.get_value("Item", doc.item, "stock_uom")
