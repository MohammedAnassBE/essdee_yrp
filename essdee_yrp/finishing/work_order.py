"""Essdee lifecycle hooks for packing Work Orders and Finishing Plans."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.rebuild import (
	get_configured_cutting_process,
	get_process_work_orders,
)
from essdee_yrp.finishing.state import get_finishing_plan_dict, get_finishing_plan_list
from essdee_yrp.finishing.status import apply_auto_fp_status
from yrp.stock.utils import get_last_sle_rate
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	get_ipd_primary_values,
)


def on_submit(doc, method=None):
	if not doc.get("includes_packing"):
		return
	if doc.get("is_rework"):
		return
	if not doc.get("is_internal_unit"):
		return
	_transfer_alternative_stock(doc)
	create_or_refresh_finishing_plan(doc)
	from essdee_yrp.finishing.box_sticker import auto_create_box_sticker_print

	auto_create_box_sticker_print(doc)


def on_cancel(doc, method=None):
	if not doc.get("includes_packing"):
		return
	if doc.get("is_internal_unit"):
		from essdee_yrp.finishing.box_sticker import cancel_box_sticker_prints

		cancel_box_sticker_prints(doc)
	finishing_plan = frappe.db.get_value(
		'SD YRP Finishing Plan', {"work_order": doc.name}, "name"
	)
	if finishing_plan:
		frappe.delete_doc('SD YRP Finishing Plan', finishing_plan, ignore_permissions=True)
	if doc.get("is_internal_unit"):
		_reverse_alternative_stock(doc)


def create_or_refresh_finishing_plan(work_order):
	work_order = (
		frappe.get_doc('YRP Work Order', work_order)
		if isinstance(work_order, str)
		else work_order
	)
	existing = frappe.db.get_value(
		'SD YRP Finishing Plan', {"work_order": work_order.name}, "name"
	)
	finishing_rows, rework_rows, grn_rows, incomplete_grns = _finishing_rows(
		work_order
	)
	if existing:
		finishing_plan = frappe.get_doc('SD YRP Finishing Plan', existing)
		_operational_merge(finishing_plan, finishing_rows, grn_rows)
		finishing_plan.set("finishing_plan_reworked_details", rework_rows)
	else:
		finishing_plan = frappe.new_doc('SD YRP Finishing Plan')
		finishing_plan.naming_series = _default_naming_series('SD YRP Finishing Plan')
		finishing_plan.lot = work_order.lot
		finishing_plan.work_order = work_order.name
		finishing_plan.item = work_order.item
		finishing_plan.production_detail = work_order.production_detail
		finishing_plan.pieces_per_box = frappe.db.get_value(
			'YRP Item Production Detail', work_order.production_detail, "packing_combo"
		)
		finishing_plan.finishing_process = frappe.db.get_single_value(
			'SD YRP MRP Settings', "finishing_inward_process"
		)
		if not finishing_plan.finishing_process:
			frappe.throw(_("Set Finishing Inward Process in MRP Settings"))
		finishing_plan.incomplete_transfer_grn_list = frappe.as_json(incomplete_grns)
		finishing_plan.incomplete_transfer_dc_list = "{}"
		finishing_plan.set("finishing_plan_details", finishing_rows)
		finishing_plan.set("finishing_plan_reworked_details", rework_rows)
		finishing_plan.set("finishing_plan_grn_details", grn_rows)
	apply_auto_fp_status(finishing_plan)
	finishing_plan.save(ignore_permissions=True)
	return finishing_plan.name


def update_submitted_alternative_work_order(source_plan, work_order, rows):
	"""Merge a later alternative-Lot top-up into a submitted packing WO."""
	old_deliverables = {
		_row_key(row): row for row in work_order.get("deliverables") or []
	}
	deltas = []
	for row in rows["deliverables"]:
		key = _dict_row_key(row)
		old = old_deliverables.get(key)
		old_quantity = flt(old.qty) if old else 0
		delta = flt(row["qty"]) - old_quantity
		if delta > 0:
			deltas.append({**row, "qty": delta})
	_merge_submitted_child(
		work_order, "deliverables", 'YRP Work Order Deliverables', rows["deliverables"]
	)
	_merge_submitted_child(
		work_order, "receivables", 'YRP Work Order Receivables', rows["receivables"]
	)
	_merge_submitted_child(
		work_order,
		"work_order_calculated_items",
		'YRP Work Order Calculated Item',
		rows["calculated_items"],
		quantity_field="quantity",
	)
	frappe.db.set_value(
		'YRP Work Order',
		work_order.name,
		{
			"total_quantity": rows["total_quantity"],
			"planned_quantity": rows["total_quantity"],
		},
	)
	_transfer_alternative_stock(work_order, rows=deltas, source_plan=source_plan)
	create_or_refresh_finishing_plan(work_order.name)


def _finishing_rows(work_order):
	default_received = frappe.db.get_single_value(
		'YRP YRP Stock Settings', "default_received_type"
	)
	default_rejected = frappe.db.get_single_value(
		'YRP YRP Stock Settings', "default_rejected_received_type"
	)
	items = {}
	for row in work_order.get("work_order_calculated_items") or []:
		key = _row_key(row)
		items.setdefault(
			key,
			{
				"inward_quantity": 0,
				"delivered_quantity": 0,
				"received_types": {},
				"cutting_qty": 0,
				"accepted_qty": 0,
				"rework_qty": 0,
				"rejected_qty": 0,
			},
		)

	finishing_process = frappe.db.get_single_value(
		'SD YRP MRP Settings', "finishing_inward_process"
	)
	if not finishing_process:
		frappe.throw(_("Set Finishing Inward Process in MRP Settings"))
	incomplete_grns = {}
	for name in get_process_work_orders(finishing_process, work_order.lot):
		upstream = frappe.get_doc('YRP Work Order', name)
		for row in upstream.get("work_order_calculated_items") or []:
			key = _row_key(row)
			if key not in items:
				continue
			items[key]["delivered_quantity"] += flt(row.received_qty)
			items[key]["inward_quantity"] += flt(row.delivered_quantity)
			received_types = update_if_string_instance(row.received_type_json) or {}
			for received_type, quantity in received_types.items():
				items[key]["received_types"][received_type] = (
					items[key]["received_types"].get(received_type, 0) + flt(quantity)
				)
				if received_type == default_received:
					items[key]["accepted_qty"] += flt(quantity)
				elif received_type == default_rejected:
					items[key]["rejected_qty"] += flt(quantity)
				else:
					items[key]["rework_qty"] += flt(quantity)
		if upstream.get("is_internal_unit"):
			for grn in frappe.get_all(
				'YRP Goods Received Note',
				filters={
					"against": 'YRP Work Order',
					"against_id": name,
					"docstatus": 1,
					"transfer_complete": 0,
				},
				pluck="name",
			):
				incomplete_grns[grn] = True

	cutting_process = get_configured_cutting_process(
		production_detail=work_order.production_detail,
		lot=work_order.lot,
	)
	for name in get_process_work_orders(cutting_process, work_order.lot):
		for row in frappe.get_doc('YRP Work Order', name).get(
			"work_order_calculated_items"
		) or []:
			key = _row_key(row)
			if key in items:
				items[key]["cutting_qty"] += flt(row.received_qty)

	finishing_rows = []
	rework_rows = []
	for (variant, combination), values in items.items():
		set_combination = frappe.as_json(dict(combination))
		if values["rework_qty"] > 0:
			rework_rows.append(
				{
					"item_variant": variant,
					"set_combination": set_combination,
					"quantity": values["rework_qty"],
					"reworked_quantity": 0,
					"rejected_qty": 0,
				}
			)
		finishing_rows.append(
			{
				"item_variant": variant,
				"delivered_quantity": values["delivered_quantity"],
				"inward_quantity": values["inward_quantity"],
				"set_combination": set_combination,
				"received_type_json": frappe.as_json(values["received_types"]),
				"cutting_qty": values["cutting_qty"],
				"accepted_qty": values["accepted_qty"],
				"rejected_qty": values["rejected_qty"],
			}
		)

	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	grn_rows = []
	for size in get_ipd_primary_values(ipd.name):
		variant = get_or_create_variant(
			work_order.item,
			{
				ipd.primary_item_attribute: size,
				**({ipd.dependent_attribute: ipd.pack_out_stage} if ipd.dependent_attribute else {}),
			},
			dependent_attr=ipd.dependent_attribute_mapping,
		)
		grn_rows.append({"item_variant": variant, "quantity": 0, "dispatched": 0})
	return finishing_rows, rework_rows, grn_rows, incomplete_grns


def _operational_merge(finishing_plan, new_rows, grn_rows):
	existing = {_row_key(row): row for row in finishing_plan.finishing_plan_details}
	recomputed = {
		"delivered_quantity",
		"inward_quantity",
		"received_type_json",
		"cutting_qty",
		"accepted_qty",
		"rejected_qty",
	}
	for row in new_rows:
		old = existing.get(_dict_row_key(row))
		if old:
			for fieldname in recomputed:
				old.set(fieldname, row.get(fieldname))
		else:
			finishing_plan.append("finishing_plan_details", row)
	existing_grn = {row.item_variant for row in finishing_plan.finishing_plan_grn_details}
	for row in grn_rows:
		if row["item_variant"] not in existing_grn:
			finishing_plan.append("finishing_plan_grn_details", row)


def _transfer_alternative_stock(work_order, rows=None, source_plan=None):
	initial_transfer = rows is None
	transferred_lot = frappe.db.get_value(
		'SD YRP Lot', work_order.lot, "transferred_lot"
	)
	if not transferred_lot:
		return
	if initial_transfer and work_order.get("reduce_stock_entry"):
		return
	if source_plan is None:
		source_plan_name = frappe.db.get_value(
			'SD YRP Finishing Plan', {"lot": transferred_lot}, "name"
		)
		if not source_plan_name:
			frappe.throw(
				_("There is no Finishing Plan for parent Lot {0}").format(
					transferred_lot
				)
			)
		source_plan = frappe.get_doc('SD YRP Finishing Plan', source_plan_name)
	rows = rows if rows is not None else list(work_order.get("deliverables") or [])
	main_rows = [
		row
		for row in rows
		if flt(row.get("qty")) > 0
		and frappe.db.get_value('YRP Item Variant', row.get("item_variant"), "item")
		== work_order.item
	]
	if not main_rows:
		return
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		_get_warehouse_for_supplier,
	)

	warehouse = _get_warehouse_for_supplier(work_order.supplier)
	if not warehouse:
		frappe.throw(
			_("No active Warehouse found for supplier {0}").format(work_order.supplier)
		)
	received_type = frappe.db.get_single_value(
		'YRP YRP Stock Settings', "default_received_type"
	)
	source_items = []
	target_items = []
	plan_rows = get_finishing_plan_dict(source_plan)
	for row in main_rows:
		attributes = get_variant_attr_details(row.get("item_variant"))
		source_variant = get_or_create_variant(source_plan.item, attributes)
		combination = json_object(row.get("set_combination"))
		key = (source_variant, tuple(sorted(combination.items())))
		if key not in plan_rows:
			frappe.throw(
				_("No source Finishing row matches {0}").format(source_variant)
			)
		quantity = flt(row.get("qty"))
		plan_rows[key]["transferred_qty"] += quantity
		rate, _matched = get_last_sle_rate(
			source_variant,
			warehouse=warehouse,
			lot=source_plan.lot,
			received_type=received_type,
		)
		if flt(rate) <= 0:
			frappe.throw(
				_("No valuation rate for {0} in {1}").format(source_variant, warehouse)
			)
		source_items.append(
			{
				"item": source_variant,
				"qty": quantity,
				"uom": row.get("uom"),
				"rate": rate,
				"lot": source_plan.lot,
				"received_type": received_type,
				"set_combination": combination,
			}
		)
		target_items.append(
			{
				"item": row.get("item_variant"),
				"qty": quantity,
				"uom": row.get("uom"),
				"rate": rate,
				"lot": work_order.lot,
				"received_type": received_type,
				"set_combination": combination,
			}
		)
	issue = _make_stock_entry(
		"Material Issue", warehouse, None, work_order.name, source_items
	)
	receipt = _make_stock_entry(
		"Material Receipt", None, warehouse, work_order.name, target_items
	)
	if initial_transfer:
		work_order.db_set("reduce_stock_entry", issue)
		work_order.db_set("update_stock_entry", receipt)
	source_plan.set("finishing_plan_details", get_finishing_plan_list(plan_rows))
	source_plan.save(ignore_permissions=True)
	return issue, receipt


def _make_stock_entry(purpose, from_warehouse, to_warehouse, work_order, items):
	stock_entry = frappe.new_doc('YRP Stock Entry')
	stock_entry.update(
		{
			"purpose": purpose,
			"from_warehouse": from_warehouse,
			"to_warehouse": to_warehouse,
			"against": 'YRP Work Order',
			"against_id": work_order,
		}
	)
	for row in items:
		stock_entry.append("items", row)
	stock_entry.insert(ignore_permissions=True)
	stock_entry.submit()
	return stock_entry.name


def _reverse_alternative_stock(work_order):
	if not frappe.db.get_value('SD YRP Lot', work_order.lot, "transferred_lot"):
		return
	linked = frappe.get_all(
		'YRP Stock Entry',
		filters={
			"against": 'YRP Work Order',
			"against_id": work_order.name,
			"docstatus": 1,
			"purpose": ["in", ["Material Receipt", "Material Issue"]],
		},
		fields=["name", "purpose"],
		order_by="creation desc",
	)
	# Reverse receipts before their source issues so target stock is removed
	# before the source bucket is restored.
	linked.sort(key=lambda row: 0 if row.purpose == "Material Receipt" else 1)
	for row in linked:
		name = row.name
		stock_entry = frappe.get_doc('YRP Stock Entry', name)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()
	source_plan_name = frappe.db.get_value(
		'SD YRP Finishing Plan',
		{"lot": frappe.db.get_value('SD YRP Lot', work_order.lot, "transferred_lot")},
		"name",
	)
	if not source_plan_name:
		return
	source_plan = frappe.get_doc('SD YRP Finishing Plan', source_plan_name)
	plan_rows = get_finishing_plan_dict(source_plan)
	for row in work_order.get("deliverables") or []:
		if frappe.db.get_value('YRP Item Variant', row.item_variant, "item") != work_order.item:
			continue
		source_variant = get_or_create_variant(
			source_plan.item, get_variant_attr_details(row.item_variant)
		)
		combination = json_object(row.set_combination)
		key = (source_variant, tuple(sorted(combination.items())))
		if key in plan_rows:
			plan_rows[key]["transferred_qty"] = max(
				flt(plan_rows[key]["transferred_qty"]) - flt(row.qty), 0
			)
	source_plan.set("finishing_plan_details", get_finishing_plan_list(plan_rows))
	source_plan.save(ignore_permissions=True)


def _merge_submitted_child(
	parent, parentfield, child_doctype, new_rows, quantity_field="qty"
):
	existing = {_row_key(row): row for row in parent.get(parentfield) or []}
	for index, row in enumerate(new_rows):
		key = _dict_row_key(row)
		old = existing.get(key)
		if old:
			values = {quantity_field: row.get(quantity_field)}
			if old.meta.get_field("pending_quantity"):
				values["pending_quantity"] = flt(old.pending_quantity) + (
					flt(row.get(quantity_field)) - flt(old.get(quantity_field))
				)
			frappe.db.set_value(child_doctype, old.name, values)
			continue
		child = frappe.new_doc(child_doctype)
		child.update(row)
		child.parent = parent.name
		child.parenttype = 'YRP Work Order'
		child.parentfield = parentfield
		child.idx = index + 1
		child.insert(ignore_permissions=True)
	frappe.clear_document_cache('YRP Work Order', parent.name)


def _row_key(row):
	combination = json_object(row.get("set_combination"))
	return row.get("item_variant"), tuple(sorted(combination.items()))


def _dict_row_key(row):
	combination = json_object(row.get("set_combination"))
	return row.get("item_variant"), tuple(sorted(combination.items()))


def _default_naming_series(doctype):
	field = frappe.get_meta(doctype).get_field("naming_series")
	options = [line.strip() for line in (field.options or "").splitlines() if line.strip()]
	if not options:
		frappe.throw(_("Configure a Naming Series for {0}").format(doctype))
	return options[-1]
