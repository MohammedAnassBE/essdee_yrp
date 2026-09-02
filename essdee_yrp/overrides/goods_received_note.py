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
from frappe.utils import cint, flt

from yrp.stock.dimensions import get_dimension_fieldnames
from yrp.stock.stock_ledger import make_sl_entries
from yrp.stock.utils import get_last_sle_rate
from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	_get_warehouse_for_supplier,
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
		display_rows = self.get("items") or []
		if (
			self.docstatus == 0
			and self.against == "Work Order"
			and self.against_id
			and display_rows
			and not self.get("is_return")
		):
			display_rows = _selected_draft_receivable_rows(self, display_rows)
		if self.get("includes_packing"):
			# A fixed-ratio packing receipt can split one size across many Work
			# Order Receivable references. Those rows must remain separate in the
			# transaction, but the submitted Desk matrix is one logical packed SKU
			# row with the split quantities added together.
			from yrp.stock.save_stock_items import group_items_for_ui

			self.set_onload(
				"item_details",
				group_items_for_ui(
					aggregate_packing_grn_rows_for_ui(display_rows),
					"Goods Received Note",
				),
			)
			return
		if not (
			self.get("cutting_laysheet")
			or self.get("allow_non_bundle")
			or self.get("additional_grn")
		):
			if display_rows is not self.get("items"):
				from yrp.stock.save_stock_items import group_items_for_ui

				self.set_onload(
					"item_details",
					group_items_for_ui(display_rows, "Goods Received Note"),
				)
			return

		# Cutting and collapsed-bundle GRNs can inherit a different Work Order
		# row_index for every size. Rebuild the display indexes from the actual
		# logical SKU so the document renders one size matrix row, as it did in
		# production_api, without mutating saved transaction rows.
		from yrp.stock.save_stock_items import group_items_for_ui

		self.set_onload(
			"item_details",
			group_items_for_ui(
				normalize_cutting_grn_row_indexes(display_rows),
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
		if self._is_essdee_return():
			_validate_direct_finishing_return_against(self)
			return
		return super().validate_against()

	def set_missing_values(self):
		super().set_missing_values()
		if not self._is_essdee_return():
			return
		work_order = frappe.get_cached_doc("Work Order", self.against_id)
		self.process_name = self.process_name or work_order.process_name
		self.item = self.item or work_order.item
		self.production_detail = self.production_detail or work_order.production_detail
		self.from_warehouse = self.from_warehouse or _get_warehouse_for_supplier(
			self.supplier
		)
		self.to_warehouse = self.to_warehouse or _get_warehouse_for_supplier(
			self.delivery_location
		)
		self.freight_charges = 0

	def set_item_defaults(self):
		super().set_item_defaults()
		_set_dynamic_packing_piece_uom(self)

	def before_submit(self):
		if self.get("against") == "Work Order" and self.get("against_id"):
			# One lock covers sewing caps, source-pending checks, deterministic plan
			# calculation, and the later Work Order stock-update transition.
			_lock_work_order(self.against_id)
		validate_sewing_plan_quantity(self)
		plan_kind = _new_consumption_plan_kind(self)
		if plan_kind:
			plan = _calculate_new_consumption_plan(self, plan_kind)
			if not plan and any(
				flt(row.get("stock_qty") or row.get("quantity")) > 0
				for row in self.get("items") or []
			):
				frappe.throw(
					_(
						"No deterministic {0} consumption plan was found for this receipt. "
						"Correct the Work Order/IPD mapping before submitting."
					).format(plan_kind)
				)
			from essdee_yrp.fabric_grn import populate_grn_deliverables

			populate_grn_deliverables(self, plan)
			self.mapped_stock_update_state = 0
			self.flags.essdee_mapped_consumption = plan
		if _has_complete_mapped_consumption(self):
			_validate_mapped_consumption_ownership(self)
			if not self.flags.get("essdee_mapped_consumption"):
				from essdee_yrp.fabric_grn import load_submitted_consumption_plan

				self.mapped_stock_update_state = 0
				self.flags.essdee_mapped_consumption = (
					load_submitted_consumption_plan(self)
				)
		return super().before_submit()

	def before_cancel(self):
		if _has_complete_mapped_consumption(self):
			_lock_work_order(self.against_id)
			_validate_mapped_consumption_ownership(self)
			if frappe.db.get_value("Work Order", self.against_id, "open_status") == "Close":
				frappe.throw(
					_(
						"Reopen Work Order {0} before cancelling Goods Received Note {1}."
					).format(self.against_id, self.name)
				)
			from essdee_yrp.fabric_grn import load_submitted_consumption_plan

			self.flags.essdee_mapped_consumption = load_submitted_consumption_plan(self)
		return super().before_cancel()

	def on_submit(self):
		plan = self.flags.get("essdee_mapped_consumption")
		apply_update = bool(
			plan and _claim_mapped_stock_update_transition(self, target_state=1)
		)
		if plan and not apply_update:
			return
		super().on_submit()
		if apply_update:
			from essdee_yrp.fabric_grn import apply_work_order_stock_update

			apply_work_order_stock_update(self.against_id, plan)
		self._enqueue_repost_if_mapped()

	def on_cancel(self):
		plan = self.flags.get("essdee_mapped_consumption")
		apply_update = bool(
			plan and _claim_mapped_stock_update_transition(self, target_state=-1)
		)
		if plan and not apply_update:
			return
		super().on_cancel()
		if apply_update:
			from essdee_yrp.fabric_grn import apply_work_order_stock_update

			apply_work_order_stock_update(self.against_id, plan, cancel=True)
		self._enqueue_repost_if_mapped()

	def validate_items(self):
		"""Allow every Essdee GRN to use one physical warehouse as both endpoints.

		Like an in-place Essdee Delivery Challan, a GRN may be required to advance
		production lineage without a physical warehouse change.  Keep base YRP's
		complete validation when the endpoints differ.  When they match, omit only
		the warehouse-inequality rejection and retain the mandatory warehouse,
		item, and positive-quantity gates.
		"""
		same_warehouse = bool(
			self.from_warehouse
			and self.from_warehouse == self.to_warehouse
		)
		if not same_warehouse:
			return super().validate_items()

		if not (self.get("items") or self.get("correction_items")):
			frappe.throw(_("At least one receivable or correction item is required."))
		if self.against == "Work Order" and not self.from_warehouse:
			frappe.throw(_("From Warehouse is required."))
		if not self.to_warehouse:
			frappe.throw(_("To Warehouse is required."))
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
		make_sl_entries(
			_return_stock_ledger_entries(self, cancel=cancel),
			cancel=cancel,
			force_inline=True,
		)

	def _is_essdee_return(self):
		return bool(
			self.against == "Work Order"
			and self.against_id
			and self.get("is_return")
			and self.get("from_finishing")
			and not self.get("delivery_challan")
		)

	def _enqueue_repost_if_mapped(self):
		if not _has_complete_mapped_consumption(self):
			return
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)


def _lock_work_order(work_order):
	frappe.db.sql(
		"SELECT name FROM `tabWork Order` WHERE name=%s FOR UPDATE",
		(work_order,),
	)


def _set_dynamic_packing_piece_uom(grn):
	"""Keep current dynamic output quantities in Pieces, not legacy Boxes.

	Version 2 stores physical boxes exclusively in ``packing_batches`` and stores
	the per-size output quantities as physical pieces. Base still validates the
	Item master first; this scoped business adapter changes only the transaction
	label/conversion after that authoritative validation.
	"""
	from essdee_yrp.dynamic_packing import is_dynamic_packing_grn

	if not is_dynamic_packing_grn(grn):
		return
	piece_uom = frappe.db.get_value("Lot", grn.get("lot"), "packing_uom")
	if not piece_uom:
		frappe.throw(_("Packing UOM is required on Lot {0}.").format(grn.get("lot")))
	for row in grn.get("items") or []:
		stock_uom = row.get("stock_uom") or piece_uom
		if stock_uom != piece_uom:
			frappe.throw(
				_(
					"Dynamic packing requires Lot packing UOM {0} to match stock UOM {1} for {2}."
				).format(piece_uom, stock_uom, row.item_variant)
			)
		row.uom = piece_uom
		row.stock_uom = piece_uom
		row.conversion_factor = 1
		row.stock_qty = flt(row.quantity)
		row.amount = flt(row.stock_qty) * flt(row.rate)


def _new_consumption_plan_kind(grn):
	"""Return the exact Essdee planner for a regular new Work Order receipt."""
	if (
		grn.get("against") != "Work Order"
		or not grn.get("against_id")
		or grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("from_closed_wo_sewing_details")
	):
		return None
	if grn.get("cutting_laysheet"):
		return "cutting"
	if grn.get("includes_packing"):
		return "packing"

	from essdee_yrp.garment_grn import (
		_is_identity_garment_grn,
		_is_stitching_garment_grn,
	)

	if _is_stitching_garment_grn(grn):
		return "stitching"

	if _is_identity_garment_grn(grn):
		return "identity"
	from essdee_yrp.fabric_grn import is_calculable_fabric_grn

	return "fabric" if is_calculable_fabric_grn(grn) else None


def _calculate_new_consumption_plan(grn, plan_kind):
	if plan_kind == "cutting":
		from essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet import (
			calculate_cutting_consumption_plan,
		)

		return calculate_cutting_consumption_plan(grn)
	if plan_kind == "packing":
		from essdee_yrp.finishing.packing_grn import (
			calculate_packing_consumption_plan,
		)

		return calculate_packing_consumption_plan(grn)
	if plan_kind == "identity":
		from essdee_yrp.garment_grn import calculate_identity_consumption_plan

		return calculate_identity_consumption_plan(grn)
	if plan_kind == "stitching":
		from essdee_yrp.garment_grn import calculate_stitching_consumption_plan

		return calculate_stitching_consumption_plan(grn)
	from essdee_yrp.fabric_grn import calculate_consumption_plan

	return calculate_consumption_plan(grn)


def _has_complete_mapped_consumption(grn):
	from yrp.yrp.doctype.goods_received_note.goods_received_note import (
		has_mapped_grn_deliverables,
	)

	return bool(
		grn.get("against") == "Work Order"
		and grn.get("against_id")
		and has_mapped_grn_deliverables(grn)
	)


def _validate_mapped_consumption_ownership(grn):
	"""Validate Essdee-owned links before base mapped valuation starts."""
	from yrp.stock.utils import get_conversion_factor
	from yrp.yrp.doctype.work_order.work_order import _stock_dimension_values

	items = {row.name: row for row in grn.get("items") or []}
	work_order = frappe.get_doc("Work Order", grn.against_id)
	deliverables = {
		row.name: row for row in work_order.get("deliverables") or []
	}
	dimension_fields = get_dimension_fieldnames()
	mapped_outputs = set()
	for row in grn.get("grn_deliverables") or []:
		output = items.get(row.get("goods_received_note_item"))
		if not output:
			frappe.throw(
				_("GRN Deliverable row {0} is not owned by this receipt.").format(
					row.idx
				)
			)
		mapped_outputs.add(output.name)
		if row.get("received_item_variant") != output.item_variant:
			frappe.throw(
				_(
					"GRN Deliverable row {0} received variant does not match its output row."
				).format(row.idx)
			)

		source = deliverables.get(row.get("work_order_deliverable"))
		if not source:
			frappe.throw(
				_(
					"GRN Deliverable row {0} is not linked to a Deliverable owned by Work Order {1}."
				).format(row.idx, work_order.name)
			)
		if row.item_variant != source.item_variant or row.uom != source.uom:
			frappe.throw(
				_(
					"GRN Deliverable row {0} input item/UOM does not match Work Order Deliverable {1}."
				).format(row.idx, source.name)
			)

		conversion = get_conversion_factor(source.item_variant, source.uom)
		expected_factor = flt(conversion.get("conversion_factor")) or 1
		expected_stock_uom = conversion.get("stock_uom") or source.uom
		if (
			(row.get("stock_uom") or row.uom) != expected_stock_uom
			or abs((flt(row.get("conversion_factor")) or 1) - expected_factor) > QTY_TOLERANCE
			or abs(flt(row.stock_qty) - flt(row.quantity) * expected_factor)
			> QTY_TOLERANCE
		):
			frappe.throw(
				_(
					"GRN Deliverable row {0} has an invalid stock-UOM conversion."
				).format(row.idx)
			)

		raw_dimensions = row.get("stock_dimensions") or {}
		if isinstance(raw_dimensions, str):
			try:
				raw_dimensions = frappe.parse_json(raw_dimensions)
			except (TypeError, ValueError):
				frappe.throw(
					_("GRN Deliverable row {0} has invalid Stock Dimensions.").format(
						row.idx
					)
				)
		if not isinstance(raw_dimensions, dict):
			frappe.throw(
				_("GRN Deliverable row {0} has invalid Stock Dimensions.").format(
					row.idx
				)
			)
		actual_dimensions = {
			fieldname: (
				row.get(fieldname)
				if row.get(fieldname) not in (None, "")
				else raw_dimensions.get(fieldname)
			)
			for fieldname in dimension_fields
		}
		expected_dimensions = _stock_dimension_values(work_order, source)
		mismatched = [
			fieldname
			for fieldname in dimension_fields
			if (actual_dimensions.get(fieldname) or None)
			!= (expected_dimensions.get(fieldname) or None)
		]
		if mismatched:
			frappe.throw(
				_(
					"GRN Deliverable row {0} Stock Dimensions do not match Work Order Deliverable {1}: {2}."
				).format(row.idx, source.name, ", ".join(mismatched))
			)

	positive_outputs = {
		row.name
		for row in grn.get("items") or []
		if flt(row.get("stock_qty") or row.get("quantity")) > 0
	}
	missing_outputs = positive_outputs - mapped_outputs
	if missing_outputs:
		frappe.throw(
			_("Every positive received row requires exact mapped consumption.")
		)


def _claim_mapped_stock_update_transition(grn, *, target_state):
	"""Claim one submit/cancel bookkeeping transition under the Work Order lock."""
	current_state = cint(
		frappe.db.get_value(
			grn.doctype,
			grn.name,
			"mapped_stock_update_state",
			for_update=True,
		)
	)
	if target_state == 1 and current_state != 0:
		return False
	if target_state == -1 and current_state == -1:
		return False
	frappe.db.set_value(
		grn.doctype,
		grn.name,
		"mapped_stock_update_state",
		target_state,
		update_modified=False,
	)
	grn.mapped_stock_update_state = target_state
	return True


def _validate_direct_finishing_return_against(grn):
	docstatus, open_status = frappe.db.get_value(
		"Work Order", grn.against_id, ["docstatus", "open_status"]
	)
	if docstatus != 1:
		frappe.throw(_("Work Order {0} must be submitted.").format(grn.against_id))
	if open_status == "Close":
		frappe.throw(_("Work Order {0} is closed.").format(grn.against_id))
	if not grn.get("supplier") or not grn.get("delivery_location"):
		frappe.throw(_("From Location and Delivery Location are required for a finishing return."))


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
	items = _only_default_received_type(defaults.get("items") or [])
	items = normalize_cutting_grn_row_indexes(items)
	defaults["items"] = items
	defaults["item_details"] = group_items_for_ui(items, "Goods Received Note")
	return defaults


def _default_received_type():
	return frappe.db.get_single_value("YRP Stock Settings", "default_received_type")


def _only_default_received_type(rows):
	"""Initial GRN matrices show the configured default split only.

	The base Vue editor already exposes ``+ Received Type`` actions for every
	other configured type, so pre-creating zero rows adds noise without enabling
	any operation.
	"""
	default = _default_received_type()
	if not default:
		return rows
	return [
		row
		for row in rows or []
		if not row.get("received_type") or row.get("received_type") == default
	]


def _selected_draft_receivable_rows(grn, existing_rows):
	"""Rebuild a draft using only Received Types the operator actually saved."""
	from yrp.stock.dimensions import apply_dimension_defaults
	from yrp.yrp.doctype.delivery_challan.delivery_challan import (
		_apply_dimension_values_to_rows,
		_get_production_group_dimensions,
	)
	from yrp.yrp.doctype.goods_received_note.goods_received_note import (
		_pending_receivable_rows,
	)

	work_order = frappe.get_doc("Work Order", grn.against_id)
	delivery_challan = (
		frappe.get_doc("Delivery Challan", grn.delivery_challan)
		if grn.delivery_challan
		else None
	)
	rows = _pending_receivable_rows(
		work_order,
		existing_rows=existing_rows,
		delivery_challan=delivery_challan,
	)
	default = _default_received_type()
	selected = {
		(
			row.get("ref_docname"),
			row.get("item_variant"),
			row.get("delivery_challan_item"),
			row.get("received_type") or default or "",
		)
		for row in existing_rows
	}
	rows = [
		row
		for row in rows
		if (
			row.get("ref_docname"),
			row.get("item_variant"),
			row.get("delivery_challan_item"),
			row.get("received_type") or default or "",
		) in selected
	]
	_apply_dimension_values_to_rows(rows, _get_production_group_dimensions(work_order))
	apply_dimension_defaults(rows)
	return rows


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
	if grn.get("supplier") and frappe.db.exists(
		"GRN Quantity Validation Exempt Supplier",
		{
			"parent": "MRP Settings",
			"parenttype": "MRP Settings",
			"parentfield": "grn_quantity_validation_exempt_suppliers",
			"supplier": grn.supplier,
		},
	):
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


def _return_stock_ledger_entries(grn, *, cancel=False):
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
		rate = 0
		if not cancel:
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
		transfer_key = f"{grn.name}:{row.name}:finishing-return"
		entries.extend(
			[
				{
					**outgoing,
					"warehouse": grn.from_warehouse,
					"qty": -quantity,
					"rate": 0,
					"outgoing_rate": flt(rate),
					"_transfer_key": transfer_key,
					"_transfer_role": "outgoing",
				},
				{
					**incoming,
					"warehouse": grn.to_warehouse,
					"qty": quantity,
					"rate": 0,
					"_transfer_key": transfer_key,
					"_transfer_role": "incoming",
				},
			]
		)
	return entries


def _find_deliverable(work_order, source_row):
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

	if (
		source_row.get("ref_doctype") == "Work Order Deliverables"
		and source_row.get("ref_docname")
	):
		for row in work_order.get("deliverables") or []:
			if row.name == source_row.ref_docname:
				if _return_deliverable_matches(row, source_row, _normal_json):
					return row
				frappe.throw(
					_(
						"Row {0}: referenced Work Order Deliverable {1} does not match the returned item/UOM/combination."
					).format(source_row.idx, source_row.ref_docname)
				)
		return None

	candidates = [
		row
		for row in work_order.get("deliverables") or []
		if _return_deliverable_matches(row, source_row, _normal_json)
	]
	if len(candidates) == 1:
		return candidates[0]
	if len(candidates) > 1:
		frappe.throw(
			_(
				"Row {0}: returned item {1} matches multiple Work Order Deliverables; reload the return to restore its exact reference."
			).format(source_row.idx, source_row.item_variant)
		)
	return None


def _return_deliverable_matches(deliverable, source_row, normal_json):
	return bool(
		deliverable.item_variant == source_row.item_variant
		and (
			not source_row.get("uom")
			or deliverable.get("uom") == source_row.get("uom")
		)
		and normal_json(deliverable.get("set_combination"))
		== normal_json(source_row.get("set_combination"))
	)
