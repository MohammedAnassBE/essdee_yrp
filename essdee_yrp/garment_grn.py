"""Garment-process GRN consumption rows.

Production API treated an ordinary, non-group embellishment process (for
example Printing: Cut -> Cut) as a one-to-one conversion: every received panel
also consumes the same panel variant from the supplier warehouse.  Base YRP
owns the stock posting; this Essdee hook supplies that company-specific
``grn_deliverables`` calculation before submission.
"""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_grn import QTY_TOLERANCE, populate_grn_deliverables


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

	work_order = frappe.get_doc("Work Order", doc.against_id)
	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	lot = frappe.get_cached_doc("Lot", work_order.lot)
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
	from yrp.yrp.doctype.work_order.work_order import _stock_dimension_values

	work_order = frappe.get_doc("Work Order", doc.against_id)
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
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

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
				"Item Variant", item_variant, "item"
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

	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	lot = frappe.get_cached_doc("Lot", work_order.lot)
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
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
		return False
	if (
		grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("includes_packing")
		or grn.get("cutting_laysheet")
	):
		return False

	work_order = frappe.get_cached_doc("Work Order", grn.against_id)
	if not work_order.get("production_detail") or not work_order.get("process_name"):
		return False
	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	if ipd.get("is_cloth_item"):
		return False
	if work_order.process_name in {
		ipd.get("cutting_process"),
		ipd.get("stiching_process"),
		ipd.get("packing_process"),
	}:
		return False
	if frappe.db.get_value("Process", work_order.process_name, "is_group"):
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
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
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

	work_order = frappe.get_cached_doc("Work Order", grn.against_id)
	if not work_order.get("production_detail") or not work_order.get("process_name"):
		return False
	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	return bool(
		not ipd.get("is_cloth_item")
		and ipd.get("stiching_process")
		and work_order.process_name == ipd.stiching_process
	)


def _find_receivable(receivables, received, work_order_name):
	"""Resolve and validate the exact Work Order output owned by a GRN row."""
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

	if received.get("ref_doctype") not in (None, "", "Work Order Receivables"):
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
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

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
