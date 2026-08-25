"""Essdee-only Goods Received Note transaction modes.

Base YRP owns ordinary receipts. A Finishing return GRN is different: it
restores a Work Order deliverable and moves stock from the Finishing warehouse
to the selected destination/received-type bucket. Keeping that branch here
prevents Essdee fields such as ``is_return`` from leaking into base YRP.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from yrp.stock.dimensions import get_dimension_fieldnames
from yrp.stock.stock_ledger import make_sl_entries
from yrp.stock.utils import get_last_sle_rate
from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	_normal_json,
	_sle_base,
	_update_work_order_status,
)
from yrp.yrp.doctype.goods_received_note.goods_received_note import GoodsReceivedNote


QTY_TOLERANCE = 0.0001


class EssdeeGoodsReceivedNote(GoodsReceivedNote):
	"""Use base YRP normally; specialize only an Essdee return GRN."""

	def onload(self):
		super().onload()
		if self.get("includes_packing"):
			# A fixed-ratio packing receipt can split one size across many Work
			# Order Receivable references. Those rows must remain separate in the
			# transaction, but the submitted Desk matrix is one logical packed SKU
			# row with the split quantities added together.
			from yrp.stock.save_stock_items import group_items_for_ui

			self.set_onload(
				"item_details",
				group_items_for_ui(
					aggregate_packing_grn_rows_for_ui(self.get("items") or []),
					"Goods Received Note",
				),
			)
			return
		if not (
			self.get("cutting_laysheet")
			or self.get("allow_non_bundle")
			or self.get("additional_grn")
		):
			return

		# Cutting and collapsed-bundle GRNs can inherit a different Work Order
		# row_index for every size. Rebuild the display indexes from the actual
		# logical SKU so the document renders one size matrix row, as it did in
		# production_api, without mutating saved transaction rows.
		from yrp.stock.save_stock_items import group_items_for_ui

		self.set_onload(
			"item_details",
			group_items_for_ui(
				normalize_cutting_grn_row_indexes(self.get("items") or []),
				"Goods Received Note",
			),
		)

	def validate_against(self):
		from essdee_yrp.sewing.closed_work_order import (
			is_closed_sewing_grn,
			validate_closed_sewing_grn,
		)

		if is_closed_sewing_grn(self):
			validate_closed_sewing_grn(self)
			return
		return super().validate_against()

	def before_submit(self):
		validate_sewing_plan_quantity(self)
		return super().before_submit()

	def validate_items(self):
		"""Allow a cutting conversion to consume and produce in one warehouse.

		Ordinary GRNs must use different source and destination warehouses.  A
		label-generated cutting GRN is a production conversion, though: cloth is
		consumed and cut-panel variants are received at the cutting unit itself.
		The later CPM Stock Entry performs the physical warehouse movement.
		"""
		if not (
			self.get("cutting_laysheet")
			and self.from_warehouse
			and self.from_warehouse == self.to_warehouse
		):
			return super().validate_items()

		if not (self.get("items") or self.get("correction_items")):
			frappe.throw(_("At least one receivable or correction item is required."))
		for row in (self.get("items") or []) + (self.get("correction_items") or []):
			if not row.item_variant:
				frappe.throw(_("Row {0}: Item Variant is required.").format(row.idx))
			if flt(row.quantity) <= 0:
				frappe.throw(_("Row {0}: Quantity must be greater than zero.").format(row.idx))

	def validate_source_pending(self):
		if not self._is_essdee_return():
			return super().validate_source_pending()
		_validate_return_quantities(self)

	def update_source_pending(self, cancel=False):
		if not self._is_essdee_return():
			return super().update_source_pending(cancel=cancel)
		_update_returned_deliverables(self, cancel=cancel)

	def make_stock_ledger_entries(self, cancel=False):
		if not self._is_essdee_return():
			return super().make_stock_ledger_entries(cancel=cancel)
		make_sl_entries(_return_stock_ledger_entries(self), cancel=cancel)

	def _is_essdee_return(self):
		return bool(
			self.against == "Work Order"
			and self.against_id
			and self.get("is_return")
			and not self.get("delivery_challan")
		)


@frappe.whitelist()
def get_work_order_defaults(work_order, delivery_challan=None):
	"""Return base GRN defaults with Essdee's logical size-row indexes.

	Migrated garment Work Orders can retain one source ``row_index`` per exact
	Item Variant.  A fresh GRN must still show the parent SKU once with every
	size across that row.  Normalize only copied response rows; the Work Order
	and its saved receivable references remain untouched.
	"""
	from yrp.stock.save_stock_items import group_items_for_ui
	from yrp.yrp.doctype.goods_received_note.goods_received_note import (
		get_work_order_defaults as get_base_work_order_defaults,
	)

	defaults = get_base_work_order_defaults(work_order, delivery_challan)
	items = normalize_cutting_grn_row_indexes(defaults.get("items") or [])
	defaults["items"] = items
	defaults["item_details"] = group_items_for_ui(items, "Goods Received Note")
	return defaults


def normalize_cutting_grn_row_indexes(rows):
	"""Return cutting GRN rows with one index per logical SKU/received-type.

	The primary item attribute (Size in the cutting flow) is deliberately omitted
	from the key.  All sizes for the same panel/colour/set combination therefore
	share one row_index and render across the matrix columns.  Stock dimensions
	other than Received Type remain part of the key so distinct stock buckets are
	not accidentally merged.  Received Type itself gets a separate indexed row;
	the Vue editor combines those rows into its Accepted/Rejected splits.
	"""
	from yrp.stock.dimensions import get_dimension_fieldnames

	dimension_fields = get_dimension_fieldnames()
	logical_indexes = {}
	normalized = []
	for position, source in enumerate(rows or []):
		row = frappe._dict(source if isinstance(source, dict) else source.as_dict())
		variant_name = row.get("item_variant")
		if not variant_name:
			row.row_index = f"cutting-{position:04d}"
			normalized.append(row)
			continue

		variant = frappe.get_cached_doc("Item Variant", variant_name)
		parent_item = frappe.get_cached_doc("Item", variant.item)
		primary_attribute = parent_item.get("primary_attribute")
		attributes = tuple(
			sorted(
				(attribute.attribute, attribute.attribute_value)
				for attribute in (variant.get("attributes") or [])
				if attribute.attribute != primary_attribute
			)
		)
		dimensions = tuple(
			(fieldname, row.get(fieldname))
			for fieldname in dimension_fields
			if fieldname != "received_type"
		)
		key = (
			variant.item,
			attributes,
			_canonical_json(row.get("set_combination")),
			dimensions,
			row.get("received_type") or "",
		)
		if key not in logical_indexes:
			logical_indexes[key] = len(logical_indexes)
		row.row_index = f"cutting-{logical_indexes[key]:04d}"
		normalized.append(row)
	return normalized


def aggregate_packing_grn_rows_for_ui(rows):
	"""Collapse only the read model for split fixed-ratio packing outputs.

	The stored child rows retain their immutable Work Order Receivable links.
	Rows with the same logical SKU, exact size, dimensions, and combination are
	added for the submitted matrix so repeated source allocations cannot overwrite
	one another in ``group_items_for_ui``.
	"""
	normalized = normalize_cutting_grn_row_indexes(rows)
	groups = {}
	ordered_keys = []
	sum_fields = (
		"quantity",
		"stock_qty",
		"amount",
		"pending_quantity",
		"max_receivable_quantity",
		"secondary_qty",
	)
	for source in normalized:
		key = (
			source.get("row_index"),
			source.get("item_variant"),
			source.get("received_type"),
			source.get("uom"),
			source.get("stock_uom"),
			flt(source.get("conversion_factor")),
			_canonical_json(source.get("set_combination")),
		)
		if key not in groups:
			groups[key] = frappe._dict(source)
			for fieldname in sum_fields:
				groups[key][fieldname] = 0
			ordered_keys.append(key)
		target = groups[key]
		for fieldname in sum_fields:
			target[fieldname] = flt(target.get(fieldname)) + flt(source.get(fieldname))

	result = []
	for key in ordered_keys:
		row = groups[key]
		if flt(row.stock_qty):
			row.rate = flt(row.amount) / flt(row.stock_qty)
		result.append(row)
	return result


def validate_sewing_plan_quantity(grn):
	"""Cap stitching receipts at committed Checking Output, per variant."""
	if (
		grn.get("against") != "Work Order"
		or grn.get("is_return")
		or grn.get("avoid_sewing_plan_qty")
		or not grn.get("against_id")
	):
		return
	if not frappe.db.exists("Sewing Plan", {"work_order": grn.against_id}):
		return

	checking_type = frappe.db.get_single_value("MRP Settings", "type_wise_diff_summary")
	if not checking_type:
		return

	allowed = {
		row.variant: flt(row.qty)
		for row in frappe.db.sql(
			"""
				select detail.item_variant as variant, sum(detail.quantity) as qty
				from `tabSewing Plan Detail` detail
				join `tabSewing Plan Entry Detail` entry on detail.parent = entry.name
				join `tabSewing Plan` plan on entry.sewing_plan = plan.name
				where plan.work_order = %(work_order)s
				  and entry.input_type = %(checking_type)s
				group by detail.item_variant
			""",
			{"work_order": grn.against_id, "checking_type": checking_type},
			as_dict=True,
		)
	}
	already_received = {
		row.variant: flt(row.qty)
		for row in frappe.db.sql(
			"""
				select item.item_variant as variant,
				       sum(item.quantity * if(grn.is_return, -1, 1)) as qty
				from `tabGoods Received Note Item` item
				join `tabGoods Received Note` grn on item.parent = grn.name
				where grn.against = 'Work Order'
				  and grn.against_id = %(work_order)s
				  and grn.docstatus = 1
				  and grn.name != %(grn_name)s
				group by item.item_variant
			""",
			{"work_order": grn.against_id, "grn_name": grn.name},
			as_dict=True,
		)
	}

	this_grn = defaultdict(float)
	for item in grn.get("items") or []:
		if flt(item.get("quantity")) > 0:
			this_grn[item.get("item_variant")] += flt(item.get("quantity"))

	def format_quantity(value):
		return "%g" % flt(value)

	mismatches = []
	for variant, quantity in this_grn.items():
		cap = allowed.get(variant, 0)
		received = already_received.get(variant, 0)
		running_total = received + quantity
		if flt(running_total, 3) > flt(cap, 3):
			mismatches.append(
				_(
					"{0} &mdash; Checking Output: {1}, Already received: {2}, "
					"This GRN: {3}, Over by: {4}"
				).format(
					variant,
					format_quantity(cap),
					format_quantity(received),
					format_quantity(quantity),
					format_quantity(running_total - cap),
				)
			)

	if mismatches:
		frappe.throw(
			"<br>".join(mismatches),
			title=_("Sewing Plan Qty Mismatch"),
		)


def _canonical_json(value):
	if not value:
		return "{}"
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _validate_return_quantities(grn):
	work_order = frappe.get_doc("Work Order", grn.against_id)
	quantities = defaultdict(float)
	deliverables = {}
	for row in grn.get("items") or []:
		deliverable = _find_deliverable(work_order, row)
		if not deliverable:
			frappe.throw(
				_("Row {0}: no matching Work Order Deliverable found for {1}.").format(
					row.idx, row.item_variant
				)
			)
		row.ref_doctype = "Work Order Deliverables"
		row.ref_docname = deliverable.name
		quantities[deliverable.name] += flt(row.quantity)
		deliverables[deliverable.name] = deliverable

	for name, quantity in quantities.items():
		deliverable = deliverables[name]
		delivered = max(flt(deliverable.qty) - flt(deliverable.pending_quantity), 0)
		if quantity > delivered + QTY_TOLERANCE:
			frappe.throw(
				_("Return qty {0} exceeds delivered qty {1} for {2}.").format(
					quantity, delivered, deliverable.item_variant
				)
			)


def _update_returned_deliverables(grn, *, cancel):
	work_order = frappe.get_doc("Work Order", grn.against_id)
	quantities = defaultdict(float)
	for row in grn.get("items") or []:
		deliverable = _find_deliverable(work_order, row)
		if deliverable:
			quantities[deliverable.name] += flt(row.quantity)

	for deliverable in work_order.get("deliverables") or []:
		quantity = quantities.get(deliverable.name)
		if not quantity:
			continue
		pending = (
			flt(deliverable.pending_quantity) - quantity
			if cancel
			else flt(deliverable.pending_quantity) + quantity
		)
		if pending < -QTY_TOLERANCE or pending > flt(deliverable.qty) + QTY_TOLERANCE:
			frappe.throw(
				_("Returned pending quantity is invalid for {0}.").format(
					deliverable.item_variant
				)
			)
		deliverable.db_set("pending_quantity", max(pending, 0), update_modified=False)
	_update_work_order_status(work_order.name)


def _return_stock_ledger_entries(grn):
	if not grn.from_warehouse or not grn.to_warehouse:
		frappe.throw(_("From Warehouse and To Warehouse are required for a return GRN."))
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	dimension_fields = get_dimension_fieldnames()
	entries = []
	for row in grn.get("items") or []:
		quantity = flt(row.stock_qty) or flt(row.quantity)
		if quantity <= 0:
			continue
		incoming = _sle_base(grn, row)
		outgoing = dict(incoming)
		if "received_type" in outgoing:
			outgoing["received_type"] = default_received_type
		dimensions = {fieldname: outgoing.get(fieldname) for fieldname in dimension_fields}
		rate, _matched_bucket = get_last_sle_rate(
			row.item_variant,
			warehouse=grn.from_warehouse,
			**dimensions,
		)
		if flt(rate) <= 0:
			frappe.throw(
				_("No source valuation rate is available for {0} in {1}.").format(
					row.item_variant, grn.from_warehouse
				)
			)
		entries.extend(
			[
				{
					**outgoing,
					"warehouse": grn.from_warehouse,
					"qty": -quantity,
					"rate": 0,
					"outgoing_rate": flt(rate),
				},
				{
					**incoming,
					"warehouse": grn.to_warehouse,
					"qty": quantity,
					"rate": flt(rate),
				},
			]
		)
	return entries


def _find_deliverable(work_order, source_row):
	if (
		source_row.get("ref_doctype") == "Work Order Deliverables"
		and source_row.get("ref_docname")
	):
		for row in work_order.get("deliverables") or []:
			if row.name == source_row.ref_docname:
				return row
	for row in work_order.get("deliverables") or []:
		if row.item_variant != source_row.item_variant:
			continue
		if _normal_json(row.set_combination) == _normal_json(source_row.set_combination):
			return row
	return None
