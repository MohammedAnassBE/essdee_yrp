"""Finishing-owned orchestration over base YRP DC, GRN, and Stock Entry."""

import frappe
from frappe.utils import flt, nowdate, nowtime

from essdee_yrp.dynamic_packing import (
	DYNAMIC_PACKING_VERSION,
	LEGACY_BATCH_TRACKING_VERSION,
	aggregate_batch_pieces,
	normalize_packing_batches,
)
from essdee_yrp.finishing.packing import (
	get_ipd_packing_config,
	prepare_dynamic_batch_dispatch,
)
from essdee_yrp.finishing.parsing import json_object
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item.item import (
	build_variant_attributes,
	get_or_create_variant,
)
from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	get_ipd_primary_values,
)
from yrp.yrp.doctype.supplier.supplier import get_primary_address


@frappe.whitelist()
def get_primary_values(lot=None, production_detail=None):
	ipd_name = production_detail or frappe.db.get_value("Lot", lot, "production_detail")
	if not ipd_name:
		frappe.throw("Item Production Detail is required")
	return get_ipd_primary_values(ipd_name)


@frappe.whitelist()
def create_grn(
	work_order,
	lot,
	item_name,
	data,
	delivery_location,
	actual_date,
	packing_batches=None,
):
	work_order_doc = frappe.get_doc("Work Order", work_order)
	work_order_doc.check_permission("read")
	_validate_work_order_context(work_order_doc, lot, item_name)
	ipd_name = frappe.db.get_value("Lot", lot, "production_detail")
	ipd_doc = frappe.get_cached_doc("Item Production Detail", ipd_name)
	dynamic_packing = bool(
		ipd_doc.based_on_other_attribute_mapping
		and ipd_doc.packing_mode == "Size Ratio Packing"
	)
	batch_rows = []
	if dynamic_packing:
		validate_dynamic_packing_transition(work_order, lot)
		config = get_ipd_packing_config(lot)
		batch_rows = normalize_packing_batches(
			packing_batches,
			get_ipd_primary_values(ipd_name),
			config.get("colours"),
			config.get("packing_combo"),
		)
		validate_dynamic_packing_availability(work_order, ipd_doc, batch_rows)
		size_quantities, total_boxes, total_pieces = aggregate_batch_pieces(batch_rows)
		uom = frappe.db.get_value("Lot", lot, "packing_uom")
	else:
		size_quantities = _normalize_size_quantities(data)
		total_boxes = sum(flt(quantity) for quantity in size_quantities.values())
		total_pieces = total_boxes * flt(ipd_doc.packing_combo)
		uom = frappe.db.get_value("Lot", lot, "uom")

	items = _build_packing_grn_items(
		work_order_doc,
		ipd_doc,
		lot,
		item_name,
		size_quantities,
		uom,
	)
	if not items:
		frappe.throw("Enter at least one packing quantity")

	grn = frappe.new_doc("Goods Received Note")
	grn.update(
		{
			"against": "Work Order",
			"against_id": work_order,
			"lot": lot,
			"actual_date": actual_date,
			"supplier": work_order_doc.supplier,
			"supplier_address": work_order_doc.supplier_address,
			"delivery_location": delivery_location,
			"delivery_address": get_primary_address(delivery_location),
			"supplier_document_no": "NA",
			"vehicle_no": "NA",
			"dc_no": "NA",
			"process_name": work_order_doc.process_name,
			"from_finishing": 1,
			"includes_packing": 1,
			"packing_calculation_version": (
				DYNAMIC_PACKING_VERSION if dynamic_packing else 0
			),
			"total_packing_boxes": total_boxes if dynamic_packing else 0,
			"total_packing_pieces": total_pieces if dynamic_packing else 0,
		}
	)
	grn.set("items", items)
	for batch in batch_rows:
		grn.append(
			"packing_batches",
			{
				"batch_id": batch["batch_id"],
				"colour": batch["colour"],
				"box_quantity": batch["box_quantity"],
				"dispatched_boxes": 0,
				"pieces_per_box": batch["pieces_per_box"],
				"total_pieces": batch["total_pieces"],
				"ratio_json": frappe.as_json(batch["ratio"]),
			},
		)
	grn.insert()
	grn.submit()
	return grn.name


def validate_dynamic_packing_availability(work_order, ipd_doc, batches):
	if not frappe.db.sql(
		"SELECT name FROM `tabWork Order` WHERE name = %s FOR UPDATE", work_order
	):
		frappe.throw(f"Work Order {work_order} does not exist")
	requested = {}
	for batch in batches:
		for size, pieces in batch["size_pieces"].items():
			key = (batch["colour"], size)
			requested[key] = requested.get(key, 0) + flt(pieces)

	work_order_doc = frappe.get_doc("Work Order", work_order)
	balances = {}
	for row in work_order_doc.get("work_order_calculated_items") or []:
		if frappe.get_cached_value("Item Variant", row.item_variant, "item") != ipd_doc.item:
			continue
		attributes = get_variant_attr_details(row.item_variant)
		colour = attributes.get(ipd_doc.packing_attribute)
		size = attributes.get(ipd_doc.primary_item_attribute)
		if not colour or not size:
			continue
		pending = max(flt(row.delivered_quantity) - flt(row.received_qty), 0)
		key = (colour, size)
		if ipd_doc.is_set_item:
			part = attributes.get(ipd_doc.set_item_attribute)
			if part:
				balances.setdefault(key, {})
				balances[key][part] = balances[key].get(part, 0) + pending
		else:
			balances[key] = flt(balances.get(key)) + pending

	for (colour, size), quantity in requested.items():
		balance = (
			balances.get((colour, size), {})
			if ipd_doc.is_set_item
			else balances.get((colour, size), 0)
		)
		available = min(balance.values()) if ipd_doc.is_set_item and balance else flt(balance)
		if quantity > available:
			frappe.throw(
				f"Packing ratio needs {quantity:g} pieces for {colour} / {size}, "
				f"but only {available:g} pieces are pending in Work Order {work_order}"
			)


def validate_dynamic_packing_transition(work_order, lot):
	legacy = frappe.db.sql(
		"""
			SELECT name
			FROM `tabGoods Received Note`
			WHERE against = 'Work Order'
				AND against_id = %s
				AND lot = %s
				AND docstatus = 1
				AND COALESCE(is_return, 0) = 0
				AND COALESCE(includes_packing, 0) = 1
				AND COALESCE(from_finishing, 0) = 1
				AND COALESCE(packing_calculation_version, 0) < %s
			LIMIT 1
		""",
		(work_order, lot, LEGACY_BATCH_TRACKING_VERSION),
	)
	if legacy:
		frappe.throw(
			"This Finishing Plan has fixed-ratio GRNs that have not been migrated "
			"to packing batches. Run the legacy packing GRN migration first."
		)


def _build_packing_grn_items(
	work_order_doc,
	ipd_doc,
	lot,
	item_name,
	size_quantities,
	uom,
):
	stage = ipd_doc.pack_out_stage
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	items = []
	for row_index, (size, quantity) in enumerate(size_quantities.items()):
		if flt(quantity) <= 0:
			continue
		variant = get_or_create_variant(
			item_name,
			build_variant_attributes(
				{ipd_doc.primary_item_attribute: size}, stage, ipd_doc.name
			),
		)
		receivables = [
			row
			for row in work_order_doc.receivables
			if row.item_variant == variant and flt(row.pending_quantity) > 0
		]
		if not receivables:
			frappe.throw(
				f"Work Order {work_order_doc.name} has no packing receivable for {variant}"
			)
		remaining = flt(quantity)
		for receivable in receivables:
			allocated = min(remaining, flt(receivable.pending_quantity))
			if allocated <= 0:
				continue
			items.append(
				{
					"item_variant": variant,
					"lot": lot,
					"quantity": allocated,
					"uom": uom or receivable.uom,
					"received_type": default_received_type,
					"ref_doctype": "Work Order Receivables",
					"ref_docname": receivable.name,
					"table_index": receivable.table_index,
					"row_index": receivable.row_index or str(row_index),
					"set_combination": receivable.set_combination or "{}",
				}
			)
			remaining -= allocated
			if remaining <= 0.001:
				break
		if remaining > 0.001:
			frappe.throw(
				f"Work Order {work_order_doc.name} has only {flt(quantity) - remaining:g} "
				f"packing quantity pending for {variant}, not {flt(quantity):g}"
			)
	return items


def _normalize_size_quantities(data):
	data = update_if_string_instance(data) or {}
	if not isinstance(data, dict):
		frappe.throw("Packing quantity must be a size-to-quantity object")
	return {size: flt(quantity) for size, quantity in data.items() if flt(quantity) > 0}


def _normalize_dispatch_quantities(data):
	"""Read the legacy dispatch grid's nested ``cur_dispatch`` values."""
	data = update_if_string_instance(data) or {}
	if not isinstance(data, dict):
		frappe.throw("Dispatch quantity must be a size-to-quantity object")
	quantities = {}
	for size, value in data.items():
		value = update_if_string_instance(value)
		quantity = flt(value.get("cur_dispatch")) if isinstance(value, dict) else flt(value)
		if quantity < 0:
			frappe.throw(f"Dispatch quantity cannot be negative for {size}")
		if quantity > 0:
			quantities[size] = quantity
	return quantities


def _validate_legacy_dispatch_balance(finishing_doc, ipd, quantities):
	available_by_size = {}
	for row in finishing_doc.get("finishing_plan_grn_details") or []:
		attributes = get_variant_attr_details(row.item_variant)
		size = attributes.get(ipd.primary_item_attribute)
		if not size:
			continue
		available_by_size[size] = available_by_size.get(size, 0) + max(
			flt(row.quantity) - flt(row.dispatched), 0
		)
	for size, quantity in quantities.items():
		available = flt(available_by_size.get(size))
		if quantity > available + 1e-6:
			frappe.throw(
				f"Only {available:g} boxes are available to dispatch for {size}, "
				f"not {quantity:g}"
			)


@frappe.whitelist()
def create_delivery_challan(
	data,
	item_name,
	work_order,
	lot,
	from_location,
	vehicle_no,
	fp_name,
	actual_date,
):
	payload = update_if_string_instance(data) or {}
	selected_type = payload.get("selected_type")
	work_order_doc = frappe.get_doc("Work Order", work_order)
	work_order_doc.check_permission("read")
	_validate_work_order_context(work_order_doc, lot, item_name)
	selected = get_delivery_challan_item_list(
		lot,
		item_name,
		payload.get("items") or {},
		is_loose_piece=selected_type == "return_qty",
	)
	items = []
	for row in work_order_doc.deliverables:
		combination = json_object(row.set_combination)
		key = (row.item_variant, tuple(sorted(combination.items())))
		if key not in selected:
			continue
		items.append(
			{
				"item_variant": row.item_variant,
				"qty": selected[key]["qty"],
				"delivered_quantity": selected[key]["qty"],
				"uom": row.uom,
				"rate": flt(row.get("rate")),
				"ref_doctype": "Work Order Deliverables",
				"ref_docname": row.name,
				"table_index": row.table_index,
				"row_index": row.row_index,
				"set_combination": row.set_combination or "{}",
				"lot": lot,
			}
		)
	if not items:
		frappe.throw("Select at least one quantity for Delivery Challan")

	delivery_challan = frappe.new_doc("Delivery Challan")
	delivery_challan.update(
		{
			"work_order": work_order,
			"lot": lot,
			"from_location": from_location,
			"from_address": get_primary_address(from_location),
			"actual_date": actual_date,
			"vehicle_no": vehicle_no,
			"supplier": work_order_doc.supplier,
			"supplier_address": get_primary_address(work_order_doc.supplier),
			"from_finishing": 1,
			"loose_piece_dc": 1 if selected_type == "return_qty" else 0,
			"pack_piece_dc": 1 if selected_type == "pack_return" else 0,
		}
	)
	delivery_challan.set("items", items)
	delivery_challan.insert()
	delivery_challan.submit()
	return delivery_challan.name


def get_delivery_challan_item_list(
	lot, item_name, data, is_loose_piece=False
):
	ipd_name = frappe.db.get_value("Lot", lot, "production_detail")
	ipd = frappe.get_cached_doc("Item Production Detail", ipd_name)
	items = {}
	payload = data.get("data", {}).get("data", {}) if isinstance(data, dict) else {}
	for colour_row in payload.values():
		if not colour_row.get("check_value"):
			continue
		for size, values in (colour_row.get("values") or {}).items():
			quantity_field = "return_qty" if is_loose_piece else "balance_dc"
			quantity = flt(values.get(quantity_field))
			if quantity <= 0:
				continue
			attributes = {
				ipd.primary_item_attribute: size,
				ipd.packing_attribute: colour_row.get("colour"),
			}
			if ipd.is_set_item:
				attributes[ipd.set_item_attribute] = colour_row.get("part")
			variant = get_or_create_variant(
				item_name,
				build_variant_attributes(
					attributes, ipd.stiching_out_stage, ipd_name
				),
			)
			combination = update_if_string_instance(
				colour_row.get("set_combination")
			) or {}
			key = (variant, tuple(sorted(combination.items())))
			entry = items.setdefault(key, {"set_combination": combination, "qty": 0})
			entry["qty"] += quantity
	return items


@frappe.whitelist()
def return_items(data, work_order, lot, item_name, popup_values, is_pack=False):
	payload = update_if_string_instance(data) or {}
	popup = update_if_string_instance(popup_values) or {}
	work_order_doc = frappe.get_doc("Work Order", work_order)
	work_order_doc.check_permission("read")
	_validate_work_order_context(work_order_doc, lot, item_name)
	ipd = frappe.get_cached_doc("Item Production Detail", work_order_doc.production_detail)
	quantity_field = "pack_return" if frappe.utils.cint(is_pack) else "return_qty"
	selected = {}
	for row_index, colour_row in enumerate(
		(payload.get("data", {}).get("data", {}) or {}).values()
	):
		for size, values in (colour_row.get("values") or {}).items():
			quantity = flt(values.get(quantity_field))
			if quantity <= 0:
				continue
			attributes = {
				ipd.primary_item_attribute: size,
				ipd.packing_attribute: colour_row.get("colour"),
			}
			if ipd.is_set_item:
				attributes[ipd.set_item_attribute] = colour_row.get("part")
			variant = get_or_create_variant(
				item_name,
				build_variant_attributes(attributes, ipd.stiching_out_stage, ipd.name),
			)
			combination = update_if_string_instance(
				colour_row.get("set_combination")
			) or {}
			key = (variant, tuple(sorted(combination.items())))
			entry = selected.setdefault(
				key,
				{
					"quantity": 0,
					"set_combination": combination,
					"row_index": str(row_index),
				},
			)
			entry["quantity"] += quantity

	items = []
	for (variant, combination_tuple), values in selected.items():
		deliverable = next(
			(
				row
				for row in work_order_doc.deliverables
				if row.item_variant == variant
				and tuple(
					sorted(json_object(row.set_combination).items())
				) == combination_tuple
			),
			None,
		)
		items.append(
			{
				"item_variant": variant,
				"lot": lot,
				"quantity": values["quantity"],
				"uom": frappe.db.get_value("Item", item_name, "default_unit_of_measure"),
				"received_type": popup.get("received_type"),
				"ref_doctype": "Work Order Deliverables",
				"ref_docname": deliverable.name if deliverable else None,
				"table_index": 0,
				"row_index": values["row_index"],
				"set_combination": values["set_combination"],
			}
		)
	if not items:
		frappe.throw("Select at least one return quantity")

	grn = frappe.new_doc("Goods Received Note")
	grn.update(
		{
			"against": "Work Order",
			"is_return": 1,
			"is_rework": 0,
			"includes_packing": work_order_doc.includes_packing,
			"against_id": work_order,
			"lot": lot,
			"process_name": work_order_doc.process_name,
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"delivery_date": nowdate(),
			"is_internal_unit": 0,
			"is_manual_entry": 0,
			"delivery_location": popup.get("delivery_location"),
			"supplier": popup.get("from_location"),
			"vehicle_no": popup.get("vehicle_no"),
			"supplier_document_no": "NA",
			"dc_no": "NA",
			"is_pack": frappe.utils.cint(is_pack),
			"supplier_address": get_primary_address(popup.get("from_location")),
			"delivery_address": get_primary_address(popup.get("delivery_location")),
			"from_finishing": 1,
		}
	)
	grn.set("items", items)
	grn.insert()
	grn.submit()
	return grn.name


@frappe.whitelist()
def convert_to_loose_piece_items(data, work_order, lot, item_name, from_location):
	"""Record the F15 loose-piece conversion as an auditable DC + return GRN.

	Both documents use the same Work Order deliverable identity. Their stock
	movements offset one another, while the Finishing adapter moves the selected
	quantity from the normal inward bucket to the loose-piece return bucket.
	"""
	payload = update_if_string_instance(data) or {}
	work_order_doc = frappe.get_doc("Work Order", work_order)
	work_order_doc.check_permission("read")
	_validate_work_order_context(work_order_doc, lot, item_name)
	if not from_location:
		frappe.throw("From Location is required")

	delivery_challan = create_delivery_challan(
		{
			"selected_type": "return_qty",
			"items": payload,
		},
		item_name,
		work_order,
		lot,
		from_location,
		"NA",
		frappe.db.get_value("Finishing Plan", {"work_order": work_order}, "name"),
		nowdate(),
	)
	goods_received_note = return_items(
		payload,
		work_order,
		lot,
		item_name,
		{
			"from_location": from_location,
			"delivery_location": from_location,
			"vehicle_no": "NA",
			"received_type": frappe.db.get_single_value(
				"YRP Stock Settings", "default_received_type"
			),
		},
	)
	return {
		"delivery_challan": delivery_challan,
		"goods_received_note": goods_received_note,
	}


@frappe.whitelist()
def create_stock_entry(
	data,
	item_name,
	doc_name,
	lot,
	from_location,
	to_location,
	goods_value,
	vehicle_no,
	colour_details=None,
	packing_batch_dispatches=None,
):
	finishing_doc = frappe.get_doc("Finishing Plan", doc_name)
	finishing_doc.check_permission("read")
	if finishing_doc.lot != lot or finishing_doc.item != item_name:
		frappe.throw("Finishing Plan, Lot, and Item do not match")
	from essdee_yrp.finishing.packing import get_finishing_packing_summary

	packing_summary = get_finishing_packing_summary(finishing_doc)
	requests = update_if_string_instance(packing_batch_dispatches) or []
	if packing_summary.dynamic_ratio_packing and not requests:
		frappe.throw("Select packing batches and box quantities for this dispatch")
	if not packing_summary.dynamic_ratio_packing and requests:
		frappe.throw("Packing batches are not valid for the legacy fixed-ratio flow")
	dynamic_dispatches = (
		prepare_dynamic_batch_dispatch(finishing_doc, requests) if requests else []
	)
	ipd = frappe.get_cached_doc("Item Production Detail", finishing_doc.production_detail)
	items = []
	if dynamic_dispatches:
		grouped = {}
		for batch in dynamic_dispatches:
			for size, quantity in batch["stock_quantities"].items():
				key = (size, batch["stock_uom"])
				grouped[key] = grouped.get(key, 0) + flt(quantity)
		for (size, uom), quantity in grouped.items():
			items.append(
				{
					"item": get_or_create_variant(
						item_name,
						build_variant_attributes(
							{ipd.primary_item_attribute: size},
							ipd.pack_out_stage,
							ipd.name,
						),
					),
					"qty": quantity,
					"uom": uom,
					"lot": lot,
					"set_combination": "{}",
				}
			)
	else:
		quantities = _normalize_dispatch_quantities(data)
		if not quantities:
			frappe.throw("Enter at least one dispatch quantity")
		_validate_legacy_dispatch_balance(finishing_doc, ipd, quantities)
		for size, quantity in quantities.items():
			items.append(
				{
					"item": get_or_create_variant(
						item_name,
						build_variant_attributes(
							{ipd.primary_item_attribute: size},
							ipd.pack_out_stage,
							ipd.name,
						),
					),
					"qty": quantity,
					"uom": frappe.db.get_value("Lot", lot, "uom"),
					"lot": lot,
					"set_combination": "{}",
				}
			)

	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.update(
		{
			"purpose": "Material Issue",
			"against": "Finishing Plan",
			"against_id": doc_name,
			"from_warehouse": from_location,
			"transfer_supplier": to_location,
			"vehicle_no": vehicle_no,
			"additional_amount": goods_value,
			"packing_batch_dispatch_json": (
				frappe.as_json(dynamic_dispatches) if dynamic_dispatches else None
			),
			"dispatch_colour_details": (
				frappe.as_json(
					[
						{
							"lot": lot,
							"item": item_name,
							"grid": update_if_string_instance(colour_details),
						}
					]
				)
				if colour_details
				else None
			),
		}
	)
	for row in items:
		row["received_type"] = default_received_type
		stock_entry.append("items", row)
	_populate_stock_rates(stock_entry, from_location)
	stock_entry.insert()
	stock_entry.submit()
	return stock_entry.name


@frappe.whitelist()
def create_material_receipt(data, item_name, lot, ipd, doc_name, location):
	payload = update_if_string_instance(data) or {}
	finishing_doc = frappe.get_doc("Finishing Plan", doc_name)
	finishing_doc.check_permission("read")
	ipd_doc = frappe.get_cached_doc("Item Production Detail", ipd)
	items = []
	for colour_row in (payload.get("data", {}).get("data", {}) or {}).values():
		for size, values in (colour_row.get("values") or {}).items():
			quantity = flt(values.get("ironing_dc"))
			if quantity <= 0:
				continue
			attributes = {
				ipd_doc.primary_item_attribute: size,
				ipd_doc.packing_attribute: colour_row.get("colour"),
			}
			if ipd_doc.is_set_item:
				attributes[ipd_doc.set_item_attribute] = colour_row.get("part")
			items.append(
				{
					"item": get_or_create_variant(
						item_name,
						build_variant_attributes(
							attributes, ipd_doc.stiching_out_stage, ipd
						),
					),
					"qty": quantity,
					"lot": lot,
					"uom": frappe.db.get_value(
						"Item", item_name, "default_unit_of_measure"
					),
					"set_combination": update_if_string_instance(
						colour_row.get("set_combination")
					),
				}
			)
	if not items:
		frappe.throw("Select at least one ironing excess quantity")
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.update(
		{
			"purpose": "Material Receipt",
			"against": "Finishing Plan",
			"against_id": doc_name,
			"to_warehouse": location,
			"transfer_supplier": location,
		}
	)
	for row in items:
		row["received_type"] = default_received_type
		stock_entry.append("items", row)
	_populate_stock_rates(stock_entry, location, require_positive=True)
	stock_entry.insert()
	stock_entry.submit()
	return stock_entry.name


@frappe.whitelist()
def cancel_document(doctype, docname):
	if doctype not in (
		"Delivery Challan",
		"Goods Received Note",
		"Stock Entry",
		"Lot Transfer",
	):
		frappe.throw("This document type cannot be cancelled from Finishing Plan")
	doc = frappe.get_doc(doctype, docname)
	doc.check_permission("cancel")
	doc.cancel()


def _validate_work_order_context(work_order_doc, lot, item_name):
	if work_order_doc.docstatus != 1 or work_order_doc.open_status == "Close":
		frappe.throw(f"Work Order {work_order_doc.name} must be submitted and open")
	if work_order_doc.lot != lot:
		frappe.throw(f"Work Order {work_order_doc.name} does not belong to Lot {lot}")
	if item_name and work_order_doc.item != item_name:
		frappe.throw(f"Work Order {work_order_doc.name} does not belong to Item {item_name}")


def _populate_stock_rates(stock_entry, warehouse, *, require_positive=False):
	"""Apply YRP's dimension-aware last valuation rate to programmatic rows."""
	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.stock.utils import get_last_sle_rate

	dimension_fields = get_dimension_fieldnames()
	for row in stock_entry.get("items") or []:
		dimensions = {fieldname: row.get(fieldname) for fieldname in dimension_fields}
		rate, _matched_bucket = get_last_sle_rate(
			row.item,
			warehouse=warehouse,
			**dimensions,
		)
		row.rate = flt(rate)
		if require_positive and row.rate <= 0:
			frappe.throw(
				f"No valuation rate is available for {row.item}; "
				"create the source valuation before receiving ironing excess"
			)
