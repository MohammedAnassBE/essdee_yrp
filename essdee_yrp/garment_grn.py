"""Garment-process GRN consumption rows.

Production API treated an ordinary, non-group embellishment process (for
example Printing: Cut -> Cut) as a one-to-one conversion: every received panel
also consumes the same panel variant from the supplier warehouse.  Base YRP
owns the stock posting; this Essdee hook supplies that company-specific
``grn_deliverables`` calculation before submission.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from essdee_yrp.fabric_grn import QTY_TOLERANCE, populate_grn_deliverables


@frappe.whitelist()
def get_grn_calculation_context(goods_received_note):
	"""Return the saved Work Order demand as an editable GRN matrix.

	Production API's Calculate button did not calculate from the current stock
	balance or from arbitrary Lot rows. It replayed the exact
	``work_order_calculated_items`` saved when the Work Order was built. Keep that
	lineage here and use the F16 garment calculator for the resulting outputs.
	"""
	grn = frappe.get_doc('YRP Goods Received Note', goods_received_note)
	grn.check_permission("read")
	work_order, ipd = _validate_grn_calculation(grn)
	context = _calculated_item_context(work_order, ipd)
	context.update(
		{
			"default_received_type": frappe.db.get_single_value(
				'YRP YRP Stock Settings', "default_received_type"
			),
			"modified": cstr(grn.modified),
		}
	)
	return context


@frappe.whitelist()
def calculate_grn_receivables(
	goods_received_note,
	rows,
	received_type,
	modified=None,
):
	"""Replace one Received-Type split with outputs for selected WO demand.

	Other Received-Type quantities already entered on the draft are retained.
	The saved draft is rebuilt from authoritative Work Order Receivable rows so
	item/UOM/reference/dimension metadata cannot be supplied by the browser.
	"""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	grn = frappe.get_doc('YRP Goods Received Note', goods_received_note)
	grn.check_permission("write")
	work_order, ipd = _validate_grn_calculation(grn)
	if modified and cstr(grn.modified) != cstr(modified):
		frappe.throw(
			_("{0} was modified after the Calculate dialog opened. Reload and try again.").format(
				grn.name
			),
			frappe.TimestampMismatchError,
		)
	if not received_type or not frappe.db.exists('YRP Received Type', received_type):
		frappe.throw(_("Select a valid Received Type."))

	demands = _validated_grn_demands(work_order, ipd, rows)
	if not demands:
		frappe.throw(_("Enter a quantity greater than zero for at least one row."))
	from essdee_yrp.garment_work_order import calculate_garment_process_rows

	lot = frappe.get_cached_doc('SD YRP Lot', work_order.lot)
	_inputs, outputs = calculate_garment_process_rows(
		ipd, lot, work_order.process_name, demands
	)
	if not outputs:
		frappe.throw(_("The Work Order calculation did not produce any receivables."))

	desired_by_receivable = {}
	for output in outputs:
		quantity = flt(output.get("qty"))
		if quantity <= 0:
			continue
		target = _match_calculated_receivable(work_order, output)
		desired_by_receivable[target.name] = (
			flt(desired_by_receivable.get(target.name)) + quantity
		)

	from yrp.stock.dimensions import apply_dimension_defaults
	from yrp.stock.save_stock_items import group_items_for_ui
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		_apply_dimension_values_to_rows,
		_get_production_group_dimensions,
	)
	from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
		_pending_receivable_rows,
	)

	delivery_challan = (
		frappe.get_doc('YRP Delivery Challan', grn.delivery_challan)
		if grn.delivery_challan
		else None
	)
	canonical_rows = _pending_receivable_rows(
		work_order,
		existing_rows=grn.get("items") or [],
		delivery_challan=delivery_challan,
	)
	canonical_rows = _include_calculated_receivable_rows(
		canonical_rows,
		work_order,
		desired_by_receivable,
		received_type,
	)
	canonical_rows = _apply_calculated_receivable_quantities(
		canonical_rows,
		desired_by_receivable,
		received_type,
	)
	_apply_dimension_values_to_rows(
		canonical_rows, _get_production_group_dimensions(work_order)
	)
	apply_dimension_defaults(canonical_rows)

	# Keep the same one-logical-SKU/size layout used when a GRN is first opened.
	from essdee_yrp.overrides.goods_received_note import (
		normalize_cutting_grn_row_indexes,
	)

	canonical_rows = normalize_cutting_grn_row_indexes(canonical_rows)
	item_details = group_items_for_ui(canonical_rows, 'YRP Goods Received Note')
	grn.item_details = frappe.as_json(item_details)
	grn.save()
	return {
		"name": grn.name,
		"received_type": received_type,
		"received_rows": len(canonical_rows),
		"total_quantity": sum(flt(row.get("quantity")) for row in canonical_rows),
	}


def _validate_grn_calculation(grn):
	if grn.docstatus != 0:
		frappe.throw(_("Calculate can update only a draft Goods Received Note."))
	if grn.get("against") != 'YRP Work Order' or not grn.get("against_id"):
		frappe.throw(_("Calculate is available only for a Work Order Goods Received Note."))
	if any(
		grn.get(fieldname)
		for fieldname in (
			"is_return",
			"is_rework",
			"additional_grn",
			"includes_packing",
			"cutting_laysheet",
			"cut_panel_movement",
			"from_closed_wo_sewing_details",
		)
	):
		frappe.throw(_("Calculate is not available for this Goods Received Note mode."))

	work_order = frappe.get_doc('YRP Work Order', grn.against_id)
	if work_order.docstatus != 1 or work_order.get("open_status") == "Close":
		frappe.throw(_("Work Order {0} must be submitted and open.").format(work_order.name))
	if not work_order.get("work_order_calculated_items"):
		frappe.throw(_("Work Order {0} has no saved calculated items.").format(work_order.name))
	if not work_order.get("production_detail") or not work_order.get("lot"):
		frappe.throw(_("Work Order {0} is missing its Lot or Item Production Detail.").format(work_order.name))
	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	if ipd.get("is_cloth_item"):
		frappe.throw(_("Use the fabric receipt flow for a cloth Work Order."))
	return work_order, ipd


def _calculated_item_context(work_order, ipd):
	from yrp.utils import get_variant_attr_details
	from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
		get_ipd_primary_values,
	)

	primary_values = list(get_ipd_primary_values(ipd.name) or [])
	display_attributes = []
	matrix_rows = []
	matrix_rows_by_key = {}
	flat_rows = []
	for index, source in enumerate(work_order.get("work_order_calculated_items") or []):
		quantity = flt(source.get("quantity"))
		if not source.get("item_variant") or quantity <= 0:
			continue
		attributes = get_variant_attr_details(source.item_variant)
		visible_attributes = {
			key: value
			for key, value in attributes.items()
			if key != ipd.get("dependent_attribute")
		}
		flat_rows.append(
			{
				"source_row": source.name,
				"item_variant": source.item_variant,
				"attributes": visible_attributes,
				"available_qty": quantity,
				"qty": quantity,
				"table_index": source.get("table_index"),
				"row_index": source.get("row_index"),
			}
		)
		for attribute in visible_attributes:
			if attribute != ipd.get("primary_item_attribute") and attribute not in display_attributes:
				display_attributes.append(attribute)

		group_key = (
			cstr(source.get("table_index")),
			cstr(source.get("row_index") if source.get("row_index") not in (None, "") else index),
		)
		matrix_row = matrix_rows_by_key.get(group_key)
		if matrix_row is None:
			matrix_row = {
				"attributes": {
					key: value
					for key, value in visible_attributes.items()
					if key != ipd.get("primary_item_attribute")
				},
				"values": {},
			}
			matrix_rows_by_key[group_key] = matrix_row
			matrix_rows.append(matrix_row)

		primary_value = visible_attributes.get(ipd.get("primary_item_attribute")) or "default"
		if primary_value not in primary_values:
			primary_values.append(primary_value)
		matrix_row["values"][primary_value] = {
			"source_row": source.name,
			"item_variant": source.item_variant,
			"available_qty": quantity,
			"qty": quantity,
		}

	return {
		"primary_attribute": ipd.get("primary_item_attribute"),
		"primary_values": primary_values,
		"display_attributes": display_attributes,
		"matrix_rows": matrix_rows,
		"rows": flat_rows,
	}


def _validated_grn_demands(work_order, ipd, rows):
	from yrp.utils import get_variant_attr_details

	calculated = {
		row.name: row for row in work_order.get("work_order_calculated_items") or []
	}
	demands = []
	seen = set()
	for incoming in rows or []:
		source_name = incoming.get("source_row")
		if not source_name or source_name in seen:
			frappe.throw(_("Each calculated Work Order row may be selected only once."))
		seen.add(source_name)
		source = calculated.get(source_name)
		if not source:
			frappe.throw(_("Unknown Work Order Calculated Item row {0}.").format(source_name))
		quantity = flt(incoming.get("qty"))
		if quantity <= 0:
			continue
		available = flt(source.get("quantity"))
		if quantity > available + QTY_TOLERANCE:
			frappe.throw(
				_("Quantity {0} exceeds calculated quantity {1} for {2}.").format(
					quantity, available, source.item_variant
				)
			)
		if frappe.db.get_value('YRP Item Variant', source.item_variant, "item") != ipd.item:
			frappe.throw(_("Item Variant {0} does not belong to IPD {1}.").format(source.item_variant, ipd.name))
		demands.append(
			{
				"item_variant": source.item_variant,
				"qty": quantity,
				"attrs": get_variant_attr_details(source.item_variant),
				"table_index": cint(source.get("table_index")),
				"row_index": cint(source.get("row_index")),
				"set_combination": source.get("set_combination") or "{}",
			}
		)
	return demands


def _match_calculated_receivable(work_order, output):
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json

	candidates = [
		row
		for row in work_order.get("receivables") or []
		if row.item_variant == output.get("item_variant")
		and _normal_json(row.get("set_combination"))
		== _normal_json(output.get("set_combination"))
	]
	for fieldname in ("table_index", "row_index"):
		value = output.get(fieldname)
		if value in (None, ""):
			continue
		exact = [row for row in candidates if cstr(row.get(fieldname)) == cstr(value)]
		if exact:
			candidates = exact
	if len(candidates) != 1:
		frappe.throw(
			_("Calculated output {0} matches {1} Work Order Receivable rows; expected exactly one.").format(
				output.get("item_variant"), len(candidates)
			)
		)
	return candidates[0]


def _apply_calculated_receivable_quantities(rows, desired_by_receivable, received_type):
	result = []
	for source in rows or []:
		row = frappe._dict(source)
		if (row.get("received_type") or "") == (received_type or ""):
			row.quantity = flt(desired_by_receivable.get(row.get("ref_docname")))
			row.stock_qty = row.quantity * (flt(row.get("conversion_factor")) or 1)
		if flt(row.get("quantity")) > 0:
			result.append(row)
	return result


def _include_calculated_receivable_rows(
	rows, work_order, desired_by_receivable, received_type
):
	"""Add selected output rows even when their current WO pending is zero.

	Calculate is a draft-entry aid, not a submit gate.  The base pending-row
	builder deliberately omits fully received outputs, but the owner may still
	recalculate the draft and let the authoritative Work Order/pending/input
	checks report at Submit.  All row identity and item metadata still come from
	the saved Work Order Receivable, never from the browser.
	"""
	result = [frappe._dict(row) for row in rows or []]
	existing = {
		(row.get("ref_docname"), row.get("received_type") or "")
		for row in result
	}
	selected_type = received_type or ""
	for target in work_order.get("receivables") or []:
		if target.name not in desired_by_receivable:
			continue
		if (target.name, selected_type) in existing:
			continue
		base_row_index = (
			target.row_index
			if target.row_index not in (None, "")
			else target.idx - 1
		)
		row = frappe._dict(
			item_variant=target.item_variant,
			quantity=0,
			uom=target.uom,
			pending_quantity=flt(target.pending_quantity),
			max_receivable_quantity=max(flt(target.pending_quantity), 0),
			ref_doctype='YRP Work Order Receivables',
			ref_docname=target.name,
			table_index=target.table_index,
			row_index=(
				f"{base_row_index}::{received_type}"
				if received_type
				else base_row_index
			),
			set_combination=target.set_combination,
			rate=target.cost,
		)
		if received_type:
			row.received_type = received_type
		result.append(row)
		existing.add((target.name, selected_type))
	return result


def before_validate(doc, method=None):
	if _is_stitching_garment_grn(doc):
		populate_grn_deliverables(doc, calculate_stitching_consumption_plan(doc))
	elif _is_identity_garment_grn(doc):
		populate_grn_deliverables(doc, calculate_identity_consumption_plan(doc))


def calculate_stitching_consumption_plan(doc):
	"""Calculate exact panel/accessory inputs for each received Stitching row."""
	if not _is_stitching_garment_grn(doc):
		return []

	from essdee_yrp.fabric_grn import _allocate_to_work_order_deliverables
	from essdee_yrp.garment_work_order import calculate_garment_process_rows
	from yrp.utils import get_variant_attr_details

	work_order = frappe.get_doc('YRP Work Order', doc.against_id)
	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	lot = frappe.get_cached_doc('SD YRP Lot', work_order.lot)
	receivables = {row.name: row for row in work_order.get("receivables") or []}
	required_rows = []
	for received in doc.get("items") or []:
		quantity = flt(received.get("quantity"))
		if quantity <= 0:
			continue
		source = _find_receivable(receivables, received, work_order.name)
		if quantity > flt(source.get("pending_quantity")) + QTY_TOLERANCE:
			frappe.throw(
				_("Work Order {0} has only {1} pending for received row {2}, but the GRN requires {3}.").format(
					work_order.name,
					flt(source.get("pending_quantity"), 6),
					received.item_variant,
					flt(quantity, 6),
				)
			)
		demands = [
			{
				"item_variant": source.item_variant,
				"qty": quantity,
				"attrs": get_variant_attr_details(source.item_variant),
				"table_index": source.get("table_index"),
				"row_index": source.get("row_index"),
				"set_combination": source.get("set_combination") or "{}",
			}
		]
		inputs, _outputs = calculate_garment_process_rows(
			ipd, lot, work_order.process_name, demands
		)
		for row in inputs:
			required_rows.append(
				{
					**row,
					"goods_received_note_item": received.name,
					"received_item_variant": received.item_variant,
				}
			)

	return _allocate_to_work_order_deliverables(
		required_rows, work_order, doc, exact_business_key=True
	)


def calculate_identity_consumption_plan(doc):
	"""Map each received embellishment row to its exact inputs and WO rows.

	The panel itself is an identity input, but garment Work Orders can also carry
	process-owned accessories (for example a fusing sticker).  Those accessories
	are calculated from the same saved Work Order demand and apportioned across
	that demand's outputs, so partial receipts consume a deterministic fraction
	without counting the accessory once per panel.
	"""
	if not _is_identity_garment_grn(doc):
		return []

	from yrp.stock.utils import get_conversion_factor, get_stock_balance
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

	work_order = frappe.get_doc('YRP Work Order', doc.against_id)
	# ``is_calculated`` describes how a Work Order row was populated; it does
	# not change whether the submitted row is a valid stock source.  Migrated
	# and manually-added deliverables can legitimately have it unset, and an
	# identity garment GRN must still consume the exact matching panel row.
	deliverables = list(work_order.get("deliverables") or [])
	remaining_by_deliverable = {
		row.name: max(
			flt(row.qty) - flt(row.pending_quantity) - flt(row.stock_update), 0
		)
		for row in deliverables
	}
	rows = []
	for received in doc.get("items") or []:
		quantity = flt(received.get("quantity"))
		if quantity <= 0:
			continue
		source = _find_deliverable(deliverables, received, work_order.name)
		available = flt(remaining_by_deliverable.get(source.name))
		if quantity > available + QTY_TOLERANCE:
			frappe.throw(
				_(
					"Work Order {0} has only {1} available for identity input {2}, "
					"but received row {3} requires {4}."
				).format(
					work_order.name,
					flt(max(available, 0), 6),
					received.item_variant,
					received.idx,
					flt(quantity, 6),
				)
			)
		conversion = get_conversion_factor(source.item_variant, source.uom)
		factor = flt(conversion.get("conversion_factor")) or 1
		dimensions = _stock_dimension_values(work_order, source)
		_balance, balance_rate = get_stock_balance(
			source.item_variant,
			doc.from_warehouse,
			posting_date=doc.posting_date,
			posting_time=doc.posting_time,
			with_valuation_rate=True,
			**dimensions,
		)
		rows.append(
			{
				"goods_received_note_item": received.name,
				"received_item_variant": received.item_variant,
				"item_variant": source.item_variant,
				"quantity": quantity,
				"stock_qty": flt(quantity * factor, 6),
				"uom": source.uom,
				"stock_uom": conversion.get("stock_uom") or source.uom,
				"conversion_factor": factor,
				"work_order_deliverable": source.name,
				"valuation_rate": flt(
					source.get("valuation_rate") or source.get("rate") or balance_rate
				),
				"dimensions": dimensions,
				"set_combination": received.get("set_combination") or {},
			}
		)
		remaining_by_deliverable[source.name] = available - quantity

	rows.extend(_calculate_identity_accessory_plan(doc, work_order))
	return rows


def _calculate_identity_accessory_plan(doc, work_order):
	"""Return mapped non-garment inputs for an identity garment receipt.

	The saved Work Order remains the stock authority.  Its calculated demand is
	replayed one row at a time only to recover the output-to-accessory route that
	was used when the Work Order was built.  Replaying one demand at a time also
	keeps size/colour-specific accessories separate.
	"""
	from essdee_yrp.fabric_grn import _allocate_to_work_order_deliverables
	from essdee_yrp.garment_work_order import calculate_garment_process_rows
	from yrp.utils import get_variant_attr_details
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json

	calculated = [
		row
		for row in work_order.get("work_order_calculated_items") or []
		if row.item_variant and flt(row.quantity) > 0
	]
	receivables = {row.name: row for row in work_order.get("receivables") or []}
	if not calculated or not receivables:
		return []

	variant_parent = {}

	def get_parent_item(item_variant):
		if item_variant not in variant_parent:
			variant_parent[item_variant] = frappe.db.get_value(
				'YRP Item Variant', item_variant, "item"
			)
		return variant_parent[item_variant]

	accessory_variants = {
		row.item_variant
		for row in work_order.get("deliverables") or []
		if row.item_variant
		and row.get("is_calculated")
		and get_parent_item(row.item_variant) != work_order.item
	}
	if not accessory_variants:
		return []

	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	lot = frappe.get_cached_doc('SD YRP Lot', work_order.lot)
	routes = []
	for source in calculated:
		demand = {
			"item_variant": source.item_variant,
			"qty": flt(source.quantity),
			"attrs": get_variant_attr_details(source.item_variant),
			"table_index": source.get("table_index"),
			"row_index": source.get("row_index"),
			"set_combination": source.get("set_combination") or "{}",
		}
		inputs, outputs = calculate_garment_process_rows(
			ipd, lot, work_order.process_name, [demand]
		)
		accessories = [
			row for row in inputs if row.get("item_variant") in accessory_variants
		]
		positive_outputs = [row for row in outputs if flt(row.get("qty")) > 0]
		# Keep routes that legitimately require no accessory too. Another size or
		# colour in the same Work Order may own the accessory variant; receiving
		# this output must resolve to its empty route instead of being rejected as
		# unmapped.
		if positive_outputs:
			routes.append(
				{
					"accessories": accessories,
					"outputs": positive_outputs,
					"total_output_qty": sum(
						flt(row.get("qty")) for row in positive_outputs
					),
				}
			)

	def output_matches(receivable, output):
		if receivable.item_variant != output.get("item_variant"):
			return False
		if _normal_json(receivable.get("set_combination")) != _normal_json(
			output.get("set_combination")
		):
			return False
		receivable_index = receivable.get("table_index")
		output_index = output.get("table_index")
		return bool(
			receivable_index in (None, "")
			or output_index in (None, "")
			or str(receivable_index) == str(output_index)
		)

	required = []
	for received in doc.get("items") or []:
		quantity = flt(received.get("quantity"))
		if quantity <= 0:
			continue
		receivable = _find_receivable(receivables, received, work_order.name)
		variant_routes = [
			route
			for route in routes
			if any(
				receivable.item_variant == output.get("item_variant")
				for output in route["outputs"]
			)
		]
		# Migrated/manual Work Orders may carry an exact identity panel row that
		# was not generated from a calculated garment demand. The panel remains a
		# valid stock input, but there is no authoritative accessory route to
		# infer. Calculated variants still fail closed below on an ambiguous or
		# mismatched combination/index.
		if not variant_routes:
			continue
		matching_routes = [
			route
			for route in variant_routes
			if any(output_matches(receivable, output) for output in route["outputs"])
		]
		if len(matching_routes) != 1:
			frappe.throw(
				_(
					"Received embellishment row {0} matches {1} calculated accessory routes in Work Order {2}; expected exactly one."
				).format(received.idx, len(matching_routes), work_order.name)
			)
		route = matching_routes[0]
		share = quantity / flt(route["total_output_qty"])
		for accessory in route["accessories"]:
			accessory_qty = flt(accessory.get("qty")) * share
			if accessory_qty <= QTY_TOLERANCE:
				continue
			required.append(
				{
					"goods_received_note_item": received.name,
					"received_item_variant": received.item_variant,
					"item_variant": accessory["item_variant"],
					"qty": flt(accessory_qty, 6),
					"uom": accessory.get("uom"),
					"set_combination": accessory.get("set_combination") or "{}",
				}
			)

	if not required:
		return []
	return _allocate_to_work_order_deliverables(
		required, work_order, doc, exact_business_key=True
	)


def _is_identity_garment_grn(grn):
	if grn.get("against") != 'YRP Work Order' or not grn.get("against_id"):
		return False
	if (
		grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("includes_packing")
		or grn.get("cutting_laysheet")
	):
		return False

	work_order = frappe.get_cached_doc('YRP Work Order', grn.against_id)
	if not work_order.get("production_detail") or not work_order.get("process_name"):
		return False
	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	if ipd.get("is_cloth_item"):
		return False
	if work_order.process_name in {
		ipd.get("cutting_process"),
		ipd.get("stiching_process"),
		ipd.get("packing_process"),
	}:
		return False
	if frappe.db.get_value('YRP Process', work_order.process_name, "is_group"):
		return False

	process_row = next(
		(
			row
			for row in (ipd.get("ipd_processes") or [])
			if row.get("process_name") == work_order.process_name
		),
		None,
	)
	return bool(process_row)


def _is_stitching_garment_grn(grn):
	"""Return whether this is the regular configured Stitching receipt route."""
	if grn.get("against") != 'YRP Work Order' or not grn.get("against_id"):
		return False
	if (
		grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("includes_packing")
		or grn.get("cutting_laysheet")
		or grn.get("from_closed_wo_sewing_details")
	):
		return False

	work_order = frappe.get_cached_doc('YRP Work Order', grn.against_id)
	if not work_order.get("production_detail") or not work_order.get("process_name"):
		return False
	ipd = frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
	return bool(
		not ipd.get("is_cloth_item")
		and ipd.get("stiching_process")
		and work_order.process_name == ipd.stiching_process
	)


def _find_receivable(receivables, received, work_order_name):
	"""Resolve and validate the exact Work Order output owned by a GRN row."""
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json

	if received.get("ref_doctype") not in (None, "", 'YRP Work Order Receivables'):
		frappe.throw(
			_("Received row {0} is not linked to a Work Order Receivable.").format(
				received.idx
			)
		)
	source = receivables.get(received.get("ref_docname"))
	if not source:
		frappe.throw(
			_("Received row {0} is not owned by Work Order {1}. Reload the GRN from that Work Order.").format(
				received.idx, work_order_name
			)
		)
	if (
		source.item_variant != received.item_variant
		or (received.get("uom") and source.get("uom") != received.get("uom"))
		or _normal_json(source.get("set_combination"))
		!= _normal_json(received.get("set_combination"))
	):
		frappe.throw(
			_("Received row {0} does not match Work Order Receivable {1}.").format(
				received.idx, source.name
			)
		)
	# A Work Order receivable owns one pending output quantity, while the GRN
	# editor may split that quantity into any configured Received Type.  The
	# selected output bucket therefore must not be forced back to the receivable
	# template's default type.  Lot remains part of the production identity.
	for fieldname in ("lot",):
		value = received.get(fieldname)
		if value and source.get(fieldname) != value:
			frappe.throw(
				_("Received row {0} {1} does not match Work Order Receivable {2}.").format(
					received.idx, fieldname, source.name
				)
			)
	return source


def _find_deliverable(deliverables, received, work_order_name):
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json

	candidates = [
		row
		for row in deliverables
		if row.item_variant == received.item_variant
		and (not received.get("uom") or row.get("uom") == received.get("uom"))
	]
	received_combination = _normal_json(received.get("set_combination"))
	candidates = [
		row
		for row in candidates
		if _normal_json(row.get("set_combination")) == received_combination
	]

	for fieldname in ("lot", "received_type"):
		value = received.get(fieldname)
		if not value:
			continue
		candidates = [row for row in candidates if row.get(fieldname) == value]

	if len(candidates) == 1:
		return candidates[0]
	if len(candidates) > 1:
		frappe.throw(
			_(
				"Received panel {0} matches multiple Deliverables in Work Order {1}."
			).format(received.item_variant, work_order_name)
		)
	frappe.throw(
		_("Received panel {0} is not a Deliverable in Work Order {1}.").format(
			received.item_variant, work_order_name
		)
	)
