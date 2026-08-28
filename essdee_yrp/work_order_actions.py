"""Essdee Desk actions for submitted Work Orders.

The F15 ``production_api`` form exposed a set of operational shortcuts which
are not part of the generic YRP Work Order.  This module restores those
Essdee-owned actions without making button visibility the security boundary.
Every mutating endpoint reloads the Work Order and rechecks permission/state.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from yrp.stock.save_stock_items import group_items_for_ui
from yrp.utils import get_variant_attr_details, update_if_string_instance


def _processes(process_name: str | None) -> list[str]:
	if not process_name:
		return []
	process = frappe.get_cached_doc("Process", process_name)
	if not process.get("is_group"):
		return [process_name]
	return [
		row.process_name
		for row in process.get("process_details") or []
		if row.process_name
	]


def _open_submitted_work_order(work_order: str, permission: str = "read"):
	doc = frappe.get_doc("Work Order", work_order)
	doc.check_permission(permission)
	if doc.docstatus != 1 or doc.open_status != "Open":
		frappe.throw(
			_("Work Order {0} must be submitted and open.").format(
				frappe.bold(doc.name)
			)
		)
	return doc


def _can_create(doctype: str) -> bool:
	return bool(frappe.has_permission(doctype, ptype="create"))


@frappe.whitelist()
def get_work_order_action_context(work_order: str) -> dict:
	"""Return state and permission-filtered actions for the Desk form."""

	doc = frappe.get_doc("Work Order", work_order)
	doc.check_permission("read")
	is_open = doc.docstatus == 1 and doc.open_status == "Open"
	can_write = bool(doc.has_permission("write"))
	processes = _processes(doc.process_name)
	ipd = (
		frappe.get_cached_doc("Item Production Detail", doc.production_detail)
		if doc.production_detail
		else None
	)
	is_cutting = bool(ipd and ipd.cutting_process in processes)
	item_bom_processes = {
		row.process_name for row in (ipd.get("item_bom") or []) if row.process_name
	} if ipd else set()

	sewing_plan = frappe.db.get_value(
		"Sewing Plan", {"work_order": doc.name}, "name"
	)
	can_create_sewing_plan = False
	if is_open and "System Manager" in frappe.get_roles(frappe.session.user):
		from essdee_yrp.sewing.plan import _should_have_sewing_plan

		can_create_sewing_plan = bool(
			sewing_plan
			or (
				_can_create("Sewing Plan")
				and _should_have_sewing_plan(doc)
			)
		)
	material_issue_warehouse = None
	if is_open and doc.supplier:
		from yrp.yrp.doctype.delivery_challan.delivery_challan import (
			_get_warehouse_for_supplier,
		)

		material_issue_warehouse = _get_warehouse_for_supplier(doc.supplier)

	return {
		"is_open": is_open,
		"is_cutting": is_cutting,
		"can_calculate_pieces": bool(
			doc.docstatus == 1
			and can_write
			and "System Manager" in frappe.get_roles(frappe.session.user)
		),
		"can_change_delivery_date": is_open and can_write,
		"can_change_item": bool(
			is_open
			and can_write
			and not doc.get("is_rework")
			and item_bom_processes.intersection(processes)
		),
		"can_make_material_issue": is_open and _can_create("Stock Entry"),
		"material_issue_warehouse": material_issue_warehouse,
		"can_make_cutting_plan": is_open and is_cutting and _can_create("Cutting Plan"),
		"can_make_delivery_challan": is_open and _can_create("Delivery Challan"),
		"can_make_goods_received_note": is_open and _can_create("Goods Received Note"),
		"can_make_recut": bool(
			is_open and not doc.get("is_rework") and _can_create("WO Recut")
		),
		"can_create_sewing_plan": can_create_sewing_plan,
		"sewing_plan": sewing_plan,
	}


def _enable_zero_pending_excess_in_editor(item_details):
	"""Remove only the Vue quantity cap for completed normal deliverables.

	Base YRP deliberately returns zero-pending Work Order deliverables so an
	operator can dispatch excess stock. Its Delivery Challan editor also uses
	``pending_quantity`` as the HTML/input maximum, which otherwise clamps those
	rows back to zero. Keep the flat defaults authoritative and clear only the
	grouped editor value; submit reloads the real pending quantity under the Work
	Order lock before updating it.
	"""

	for group in item_details or []:
		for item in group.get("items") or []:
			values = item.get("values") or {}
			if not isinstance(values, dict):
				continue
			for value in values.values():
				if not isinstance(value, dict) or "pending_quantity" not in value:
					continue
				if flt(value.get("pending_quantity")) <= 0:
					value["pending_quantity"] = None
	return item_details


@frappe.whitelist()
def get_delivery_challan_defaults(
	work_order: str,
	posting_date: str | None = None,
	posting_time: str | None = None,
) -> dict:
	"""Prepare one unsaved DC from an open Work Order without browser races."""

	doc = _open_submitted_work_order(work_order)
	frappe.has_permission("Delivery Challan", "create", throw=True)
	from yrp.yrp.doctype.delivery_challan.delivery_challan import (
		get_work_order_defaults,
	)

	defaults = get_work_order_defaults(
		doc.name,
		posting_date=posting_date,
		posting_time=posting_time,
	)
	defaults["item_details"] = _enable_zero_pending_excess_in_editor(
		defaults.get("item_details") or []
	)
	defaults.update(
		{
			"work_order": doc.name,
			"lot": doc.lot,
			"includes_packing": doc.get("includes_packing"),
			"from_address": doc.delivery_address,
			"from_address_details": doc.delivery_address_details,
			"supplier_address": doc.supplier_address,
			"supplier_address_details": doc.supplier_address_details,
		}
	)
	return defaults


@frappe.whitelist()
def get_goods_received_note_defaults(
	work_order: str, delivery_challan: str | None = None
) -> dict:
	"""Prepare one unsaved GRN from an open Work Order without browser races."""

	doc = _open_submitted_work_order(work_order)
	frappe.has_permission("Goods Received Note", "create", throw=True)
	from essdee_yrp.overrides.goods_received_note import (
		get_work_order_defaults,
	)

	defaults = get_work_order_defaults(doc.name, delivery_challan)
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	if not default_received_type:
		default_received_type = frappe.db.get_value(
			"Received Type", {"is_default": 1}, "name"
		)
	items = [
		row
		for row in (defaults.get("items") or [])
		if flt(row.get("quantity")) > 0
		or not row.get("received_type")
		or row.get("received_type") == default_received_type
	]
	defaults["items"] = items
	defaults["item_details"] = group_items_for_ui(items, "Goods Received Note")
	defaults.update(
		{
			"against": "Work Order",
			"against_id": doc.name,
			"delivery_challan": delivery_challan or "",
			"supplier_address": doc.supplier_address,
			"supplier_address_display": doc.supplier_address_details,
			"delivery_address": doc.delivery_address,
			"delivery_address_display": doc.delivery_address_details,
			"lot": doc.lot,
			"includes_packing": doc.get("includes_packing"),
		}
	)
	return defaults


@frappe.whitelist()
def get_wo_recut_defaults(work_order: str) -> dict:
	"""Return an editable, zero-quantity SKU matrix for a new WO Recut.

	The source Work Order's calculated items define the allowed garment SKUs.
	Quantities intentionally start at zero so merely opening the form cannot
	accidentally copy the full Work Order quantity into a recut request.
	"""

	doc = _open_submitted_work_order(work_order)
	frappe.has_permission("WO Recut", "create", throw=True)
	if doc.get("is_rework"):
		frappe.throw(_("A WO Recut cannot be created from a rework Work Order."))

	rows = []
	for index, row in enumerate(doc.get("work_order_calculated_items") or []):
		if not row.item_variant or flt(row.quantity) <= 0:
			continue
		rows.append(
			{
				"item_variant": row.item_variant,
				"qty": 0,
				"table_index": row.table_index or 0,
				"row_index": (
					row.row_index
					if row.row_index not in (None, "")
					else f"recut-{index}"
				),
			}
		)

	if not rows:
		frappe.throw(
			_("Work Order {0} has no calculated SKU items for recut.").format(
				frappe.bold(doc.name)
			)
		)

	return {
		"lot": doc.lot,
		"item_details": group_items_for_ui(rows, "Work Order Deliverables"),
	}


def _item_bom_rows(doc, ipd, processes):
	return [
		row
		for row in ipd.get("item_bom") or []
		if row.process_name in processes
	]


def _variant_identity(item_variant: str) -> tuple[str, str]:
	variant = frappe.get_cached_doc("Item Variant", item_variant)
	attributes = ", ".join(
		f"{row.attribute}: {row.attribute_value}"
		for row in sorted(
			variant.get("attributes") or [], key=lambda row: row.attribute
		)
	)
	return variant.item, attributes


def _row_reference_reason(row_name: str) -> str | None:
	dc = frappe.db.sql(
		"""
		SELECT dci.parent
		FROM `tabDelivery Challan Item` dci
		INNER JOIN `tabDelivery Challan` dc ON dc.name = dci.parent
		WHERE dci.ref_doctype = 'Work Order Deliverables'
		  AND dci.ref_docname = %(row_name)s
		  AND dc.docstatus = 1
		LIMIT 1
		""",
		{"row_name": row_name},
		as_dict=True,
	)
	if dc:
		return _("referenced by Delivery Challan {0}").format(dc[0].parent)
	grn = frappe.db.sql(
		"""
		SELECT gri.parent
		FROM `tabGoods Received Note Item` gri
		INNER JOIN `tabGoods Received Note` grn ON grn.name = gri.parent
		WHERE gri.ref_doctype = 'Work Order Deliverables'
		  AND gri.ref_docname = %(row_name)s
		  AND grn.docstatus = 1
		LIMIT 1
		""",
		{"row_name": row_name},
		as_dict=True,
	)
	if grn:
		return _("referenced by Goods Received Note {0}").format(grn[0].parent)
	return None


def _row_eligibility(row) -> tuple[bool, str | None]:
	if round(flt(row.qty), 3) != round(flt(row.pending_quantity), 3):
		return False, _("already delivered (pending {0} of {1})").format(
			flt(row.pending_quantity, 3), flt(row.qty, 3)
		)
	if flt(row.get("stock_update")):
		return False, _("already consumed in a Goods Received Note")
	if flt(row.get("cancelled_quantity")):
		return False, _("has cancelled quantity")
	if row.get("grn_detail_no"):
		return False, _("linked to a Goods Received Note")
	reason = _row_reference_reason(row.name)
	return (not reason), reason


def _work_order_demands(doc) -> list[dict]:
	demands = []
	for row in doc.get("work_order_calculated_items") or []:
		if not row.item_variant or flt(row.quantity) <= 0:
			continue
		demands.append(
			{
				"item_variant": row.item_variant,
				"qty": flt(row.quantity),
				"attrs": get_variant_attr_details(row.item_variant),
				"table_index": row.table_index,
				"row_index": row.row_index,
				"set_combination": row.set_combination or "{}",
			}
		)
	return demands


def _expected_accessories(doc, ipd, processes) -> list[dict]:
	from essdee_yrp.garment_work_order import _accessory_rows, _aggregate_rows

	lot = frappe.get_cached_doc("Lot", doc.lot)
	return _aggregate_rows(
		_accessory_rows(ipd, lot, _work_order_demands(doc), processes)
	)


def _change_item_context(doc, selected=None) -> dict:
	processes = _processes(doc.process_name)
	ipd = frappe.get_cached_doc("Item Production Detail", doc.production_detail)
	bom_rows = _item_bom_rows(doc, ipd, processes)
	bom_by_name = {row.name: row for row in bom_rows}
	selected = set(selected or bom_by_name)
	unknown = sorted(selected.difference(bom_by_name))
	selected_templates = {
		bom_by_name[name].item for name in selected if name in bom_by_name
	}
	selection_by_template = defaultdict(list)
	for name in selected:
		if name in bom_by_name:
			selection_by_template[bom_by_name[name].item].append(name)

	cloth_templates = {
		row.cloth for row in ipd.get("cloth_detail") or [] if row.cloth
	}
	current_by_template = defaultdict(list)
	for row in doc.get("deliverables") or []:
		if not row.get("is_calculated") or not row.item_variant:
			continue
		if update_if_string_instance(row.get("set_combination")):
			continue
		template, attributes = _variant_identity(row.item_variant)
		if template == doc.item or template in cloth_templates:
			continue
		if template not in selected_templates:
			continue
		eligible, reason = _row_eligibility(row)
		current_by_template[template].append(
			{
				"row_name": row.name,
				"old_variant": row.item_variant,
				"old_qty": flt(row.qty, 3),
				"old_uom": row.uom,
				"attributes": attributes,
				"eligible": eligible,
				"reason": reason,
			}
		)

	expected_by_template = defaultdict(list)
	for row in _expected_accessories(doc, ipd, processes):
		template, attributes = _variant_identity(row["item_variant"])
		if template in selected_templates:
			expected_by_template[template].append(
				{
					"new_variant": row["item_variant"],
					"new_qty": flt(row["qty"], 3),
					"new_uom": row.get("uom"),
					"attributes": attributes,
				}
			)

	changes = []
	for template in sorted(selected_templates):
		current = current_by_template.get(template, [])
		expected = expected_by_template.get(template, [])
		selection_id = (selection_by_template.get(template) or [None])[0]
		expected_by_variant = {
			row["new_variant"]: row for row in expected
		}
		matching_variants = {
			row["old_variant"] for row in current
		}.intersection(expected_by_variant)
		for old in current:
			if old["old_variant"] not in matching_variants:
				continue
			changes.append(
				{
					**old,
					**expected_by_variant[old["old_variant"]],
					"selection_id": selection_id,
					"item": template,
					"action": "unchanged",
					"eligible": False,
					"reason": _("already matches recalculation"),
				}
			)

		remaining_current = [
			row for row in current if row["old_variant"] not in matching_variants
		]
		remaining_expected = [
			row
			for variant, row in expected_by_variant.items()
			if variant not in matching_variants
		]
		remaining_current_variants = {
			row["old_variant"] for row in remaining_current
		}
		if len(remaining_current_variants) == len(remaining_expected) == 1:
			new = remaining_expected[0]
			for old in remaining_current:
				changes.append(
					{
						**old,
						**new,
						"selection_id": selection_id,
						"item": template,
						"action": "replace" if old["eligible"] else "blocked",
					}
				)
			continue
		if not remaining_current and not remaining_expected:
			continue

		reason = (
			_("No existing Work Order row was found.")
			if not remaining_current
			else _("No recalculated Item BOM row was found.")
			if not remaining_expected
			else _("Multiple rows are ambiguous; recalculate this Work Order in draft instead.")
		)
		for old in remaining_current or [{"row_name": selection_id, "old_variant": "", "old_qty": 0, "old_uom": ""}]:
			changes.append(
				{
					**old,
					"selection_id": selection_id,
					"item": template,
					"new_variant": "",
					"new_qty": 0,
					"new_uom": "",
					"action": "blocked",
					"eligible": False,
					"reason": old.get("reason") or reason,
				}
			)

	return {
		"supported": bool(bom_rows),
		"changes": changes,
		"skipped": [
			{"row_name": name, "reason": _("not an Item BOM row for this Work Order process")}
			for name in unknown
		],
		"bom_rows": bom_rows,
	}


@frappe.whitelist()
def get_wo_bom_accessory_items(work_order: str) -> dict:
	doc = _open_submitted_work_order(work_order, "write")
	if doc.get("is_rework"):
		frappe.throw(_("Change Item is not available on a rework Work Order."))
	context = _change_item_context(doc, selected=[])
	if not context["supported"]:
		return {
			"supported": False,
			"message": _("This Work Order's process has no recalculable Item BOM rows."),
			"items": [],
		}
	return {
		"supported": True,
		"items": [
			{
				"row_name": row.name,
				"branch": row.process_name,
				"item": row.item,
				"item_variant": row.item,
				"attributes": _("Attribute Mapping") if row.based_on_attribute_mapping else "",
				"qty": flt(row.qty_of_bom_item, 3),
				"uom": row.uom,
				"eligible": True,
				"reason": None,
			}
			for row in context["bom_rows"]
		],
	}


@frappe.whitelist()
def get_wo_bom_accessory_change_preview(work_order: str, selected) -> dict:
	doc = _open_submitted_work_order(work_order, "write")
	selected = frappe.parse_json(selected) if isinstance(selected, str) else selected
	return _change_item_context(doc, selected=selected or [])


@frappe.whitelist()
def apply_bom_accessory_changes(work_order: str, selected) -> dict:
	doc = _open_submitted_work_order(work_order, "write")
	selected = frappe.parse_json(selected) if isinstance(selected, str) else selected
	selected = set(selected or [])
	context = _change_item_context(doc, selected=selected)
	applied = []
	skipped = list(context.get("skipped") or [])
	for change in context.get("changes") or []:
		if change.get("selection_id") not in selected:
			continue
		if change.get("action") != "replace" or not change.get("eligible"):
			skipped.append(
				{
					"row_name": change.get("row_name"),
					"old_variant": change.get("old_variant"),
					"reason": change.get("reason"),
				}
			)
			continue
		frappe.db.set_value(
			"Work Order Deliverables",
			change["row_name"],
			"item_variant",
			change["new_variant"],
		)
		doc.add_comment(
			"Comment",
			_("Change Item: {0} → {1} (quantity retained: {2})").format(
				change["old_variant"], change["new_variant"], change["old_qty"]
			),
		)
		applied.append(change)
	return {"applied": applied, "skipped": skipped}
