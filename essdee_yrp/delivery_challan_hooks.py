"""Essdee-specific Delivery Challan defaults from the selected Work Order."""

import frappe
from frappe import _
from frappe.utils import flt


def before_validate(doc, method=None):
	"""Keep the Work Order's packing rule authoritative on the DC."""
	if not doc.get("work_order") or not doc.meta.get_field("includes_packing"):
		return
	if not frappe.get_meta("Work Order").get_field("includes_packing"):
		return

	doc.includes_packing = frappe.db.get_value(
		"Work Order", doc.work_order, "includes_packing"
	) or 0


def validate_exact_source_limits(doc, method=None):
	"""Keep submitted dispatches within their exact predecessor GRN rows."""
	if not doc.get("work_order") or doc.docstatus == 2:
		return
	if any(flt(row.get("qty") or row.get("delivered_quantity")) > 0 for row in doc.get("correction_items") or []):
		source_process = frappe.db.get_value(
			"Work Order", doc.work_order, "fabric_source_process"
		)
		if source_process:
			frappe.throw(_(
				"Work Order Corrections cannot dispatch material against an exact-source "
				"fabric Work Order. Create a new Work Order from available predecessor GRNs."
			))
	quantities = {}
	rows_by_reference = {}
	for row in doc.get("items") or []:
		if row.get("ref_doctype") != "Work Order Deliverables" or not row.get("ref_docname"):
			continue
		quantities[row.ref_docname] = quantities.get(row.ref_docname, 0) + flt(
			row.get("delivered_quantity") or row.get("qty")
		)
		rows_by_reference.setdefault(row.ref_docname, []).append(row)
	if not quantities:
		return
	from yrp.stock.dimensions import get_dimension_fieldnames

	dimension_fields = get_dimension_fieldnames()
	source_pool = _prepare_dispatch_source_pool(doc) if doc.docstatus == 1 else None
	# Base DC submit has already locked the Work Order Deliverable children. Use
	# a current locking read here as well: under REPEATABLE READ, get_all/plain
	# SELECT could otherwise retain the validation-time snapshot after a
	# concurrent partial DC commits and permit both requests to dispatch the
	# same remaining exact-source quantity.
	field_sql = ", ".join(
		f"`{fieldname}`" for fieldname in (
			"name", "source_grn_item", "pending_quantity", "item_variant",
			"qty", "uom", "set_combination", "source_grn",
			"fabric_reference_variant", "fabric_reference_allocations",
			*dimension_fields,
		)
	)
	targets = {
		row.name: row
		for row in frappe.db.sql(
			f"""
			SELECT {field_sql}
			FROM `tabWork Order Deliverables`
			WHERE parent = %(work_order)s
				AND name IN %(names)s
			ORDER BY idx
			FOR UPDATE
			""",
			{"work_order": doc.work_order, "names": tuple(quantities)},
			as_dict=True,
		)
	}
	for name, qty in quantities.items():
		target = targets.get(name)
		if not target or not target.source_grn_item:
			continue
		for row in rows_by_reference.get(name) or []:
			if row.get("item_variant") != target.item_variant or row.get("uom") != target.uom:
				frappe.throw(_(
					"Exact-source deliverable {0} item or UOM changed. Recreate the "
					"Delivery Challan from its Work Order."
				).format(name))
			if frappe.parse_json(row.get("set_combination") or "{}") != frappe.parse_json(
				target.set_combination or "{}"
			):
				frappe.throw(_(
					"Exact-source deliverable {0} set combination changed. Recreate the "
					"Delivery Challan from its Work Order."
				).format(name))
			for fieldname in dimension_fields:
				if (row.get(fieldname) or None) != (target.get(fieldname) or None):
					frappe.throw(_(
						"Exact-source deliverable {0} stock dimension {1} changed. "
						"Recreate the Delivery Challan from its Work Order."
					).format(name, fieldname))
		allowed = max(flt(target.pending_quantity), 0)
		if doc.docstatus == 1 and qty > allowed + 0.000001:
			frappe.throw(_(
				"Exact-source deliverable {0} can dispatch only {1}; {2} was entered. "
				"Recalculate a separate Work Order for additional source stock."
			).format(name, flt(allowed, 3), flt(qty, 3)))
		if source_pool:
			_consume_dispatch_source(source_pool, target, qty)


def _prepare_dispatch_source_pool(doc):
	"""Lock and rebuild actual source availability for a DC submit.

	The synthetic current-work-order value deliberately excludes nothing, so
	previous submitted DCs from this or another Work Order are deducted. Draft
	plans remain non-reserving.
	"""
	work_order = frappe.db.get_value(
		"Work Order",
		doc.work_order,
		[
			"lot", "production_detail", "item", "process_name",
			"fabric_source_process", "fabric_source_process_step",
			"delivery_location",
		],
		as_dict=True,
	)
	if not work_order or not work_order.fabric_source_process_step:
		return None
	from essdee_yrp.fabric_source import prepare_source_pool

	ipd = frappe.get_cached_doc(
		"Item Production Detail", work_order.production_detail
	)
	pool = prepare_source_pool(
		lot=work_order.lot,
		ipd=ipd,
		cloth_item=work_order.item,
		current_process=work_order.process_name,
		current_work_order=f"__delivery_challan__::{doc.get('name') or 'new'}",
		source_process=work_order.fabric_source_process_step,
		target_location=work_order.delivery_location,
	)
	if (
		work_order.fabric_source_process
		and pool.get("selected", {}).get("process_name")
		!= work_order.fabric_source_process
	):
		frappe.throw(_(
			"The Work Order's exact source process changed. Reopen Calculate."
		))
	return pool


def _consume_dispatch_source(pool, target, quantity):
	from essdee_yrp.fabric_reference import (
		get_reference_allocations,
		scale_reference_allocations,
	)
	from essdee_yrp.fabric_source import (
		_bucket_key,
		_conversion_factor,
		consume_source_bucket,
	)

	stock_qty = flt(quantity) * _conversion_factor(target.item_variant, target.uom)
	allocations = get_reference_allocations(target, target.qty)
	stock_allocations = scale_reference_allocations(allocations, stock_qty)
	if not stock_allocations:
		stock_allocations = {None: stock_qty}
	for reference, required_qty in stock_allocations.items():
		key = _bucket_key(
			target.source_grn_item,
			None if pool.get("physical_knitting_source") else reference,
		)
		bucket = consume_source_bucket(pool, key, required_qty)
		if (
			bucket.get("source_grn") != target.get("source_grn")
			or bucket.get("source_grn_item") != target.source_grn_item
			or bucket.get("item_variant") != target.item_variant
		):
			frappe.throw(_(
				"The exact source GRN lineage changed. Reopen Calculate."
			))
