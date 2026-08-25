"""Deterministic Essdee piece tracking for Work Order DC/GRN lifecycles.

F15 maintained garment-piece counters incrementally from Delivery Challans and
Goods Received Notes and exposed ``Calculate Pieces`` as a recovery action.
The F16 YRP transaction engine owns stock and pending quantities, while this
module owns only the Essdee garment projection.  Replaying submitted sources
makes submit, cancel, return, retry, and the recovery action idempotent.
"""

from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict
from itertools import zip_longest

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item.item import build_variant_attributes, get_or_create_variant

from essdee_yrp.dynamic_packing import is_dynamic_packing_grn


def _json_dict(value) -> dict:
	value = update_if_string_instance(value) or {}
	return value if isinstance(value, dict) else {}


def _json_key(value) -> str:
	return json.dumps(_json_dict(value), sort_keys=True, separators=(",", ":"))


def _processes(process_name: str | None) -> list[str]:
	if not process_name:
		return []
	process = frappe.get_cached_doc("Process", process_name)
	if not process.get("is_group"):
		return [process_name]
	return [row.process_name for row in process.get("process_details") or [] if row.process_name]


def _process_for_direction(process_name: str, direction: str) -> str:
	processes = _processes(process_name)
	if not processes:
		return process_name
	return processes[0] if direction == "delivery" else processes[-1]


def _process_stage(ipd, process_name: str | None) -> str | None:
	if not process_name:
		return None
	if process_name == ipd.cutting_process:
		return "cutting"
	if process_name == ipd.stiching_process:
		return ipd.stiching_in_stage
	if process_name == ipd.packing_process:
		return ipd.pack_out_stage
	for row in ipd.get("ipd_processes") or []:
		if row.process_name == process_name:
			return row.get("in_stage") or row.get("stage")
	return None


def _is_finishing_process(process_name: str) -> bool:
	configured = frappe.db.get_single_value("MRP Settings", "finishing_inward_process")
	return bool(configured and configured in _processes(process_name))


def _panel_list(ipd, process_name: str) -> list[str]:
	stage = _process_stage(ipd, process_name)
	embellishments = _json_dict(ipd.get("emblishment_details_json"))
	if stage == ipd.stiching_in_stage and embellishments.get(process_name):
		panels = update_if_string_instance(embellishments[process_name]) or []
		if isinstance(panels, list):
			return panels
	return [
		row.stiching_attribute_value
		for row in ipd.get("stiching_item_details") or []
		if row.stiching_attribute_value
	]


def _panel_requirements(ipd) -> dict[str, float]:
	return {
		row.stiching_attribute_value: flt(row.quantity) or 1
		for row in ipd.get("stiching_item_details") or []
		if row.stiching_attribute_value
	}


def _panel_parts(ipd) -> dict[str, str]:
	return {
		row.stiching_attribute_value: row.set_item_attribute_value
		for row in ipd.get("stiching_item_details") or []
		if row.stiching_attribute_value
	}


class PieceState:
	def __init__(self, work_order, ipd):
		self.work_order = work_order
		self.ipd = ipd
		self.rows = []
		self.by_identity = {}
		for row in work_order.get("work_order_calculated_items") or []:
			data = {
				"row": row,
				"item_variant": row.item_variant,
				"set_combination": _json_dict(row.set_combination),
				"attributes": get_variant_attr_details(row.item_variant),
				"parent_item": frappe.db.get_value("Item Variant", row.item_variant, "item"),
				"planned": flt(row.quantity),
				"delivered": 0.0,
				"received": 0.0,
				"received_types": defaultdict(float),
			}
			self.rows.append(data)
			self.by_identity[(row.item_variant, _json_key(row.set_combination))] = data
		self.tracking = []
		self.source_tracking = defaultdict(list)
		for row in work_order.get("work_order_track_pieces") or []:
			if not row.against_id:
				continue
			self.source_tracking[(row.against, row.against_id)].append(row)
		self.first_dc_date = None
		self.last_dc_date = None
		self.first_grn_date = None
		self.last_grn_date = None
		(
			self.delivery_completed,
			self.delivery_incomplete,
		) = self._initial_panel_structures()
		(
			self.received_completed,
			self.received_incomplete,
		) = self._initial_panel_structures()

	def _initial_panel_structures(self):
		if not self.rows:
			return {}, {}
		from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import (
			get_complete_incomplete_structure,
		)
		from essdee_yrp.essdee_yrp.doctype.lot.lot import fetch_order_item_details

		item_details = fetch_order_item_details(
			self.work_order.get("work_order_calculated_items") or [],
			self.work_order.production_detail,
		)
		if not item_details:
			return {}, {}
		completed, incomplete = get_complete_incomplete_structure(
			self.work_order.production_detail, copy.deepcopy(item_details)
		)
		return completed, incomplete

	def _exact(self, item_variant, set_combination):
		return self.by_identity.get((item_variant, _json_key(set_combination)))

	def add_delivery(self, item_variant, set_combination, quantity, voucher):
		quantity = flt(quantity)
		if quantity <= 0:
			return False
		row = self._exact(item_variant, set_combination)
		if not row:
			return False
		row["delivered"] += quantity
		self.tracking.append(
			{
				"item_variant": row["item_variant"],
				"set_combination": row["set_combination"],
				"delivered_quantity": quantity,
				"received_qty": 0,
				"against": "Delivery Challan",
				"against_id": voucher.name,
				"date": voucher.posting_date,
			}
		)
		return True

	def add_received(self, item_variant, set_combination, quantity, received_type, voucher):
		quantity = flt(quantity)
		if quantity <= 0:
			return False
		row = self._exact(item_variant, set_combination)
		if row:
			self._add_received_row(row, quantity, received_type, voucher)
			return True

		# F15 proportional fallback for an aggregated output variant: distribute
		# within the same parent item and primary size, retaining exact totals.
		attributes = get_variant_attr_details(item_variant)
		parent_item = frappe.db.get_value("Item Variant", item_variant, "item")
		primary = self.ipd.primary_item_attribute
		candidates = [
			candidate
			for candidate in self.rows
			if candidate["parent_item"] == parent_item
			and candidate["attributes"].get(primary) == attributes.get(primary)
		]
		total_planned = sum(candidate["planned"] for candidate in candidates)
		if not candidates or total_planned <= 0:
			return False
		remaining = quantity
		for index, candidate in enumerate(candidates):
			share = (
				remaining
				if index == len(candidates) - 1
				else int(quantity * candidate["planned"] / total_planned)
			)
			remaining -= share
			if share > 0:
				self._add_received_row(candidate, share, received_type, voucher)
		return True

	def _add_received_row(self, row, quantity, received_type, voucher):
		received_type = received_type or frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		)
		row["received"] += quantity
		if received_type:
			row["received_types"][received_type] += quantity
		self.tracking.append(
			{
				"item_variant": row["item_variant"],
				"set_combination": row["set_combination"],
				"delivered_quantity": 0,
				"received_qty": quantity,
				"against": "Goods Received Note",
				"against_id": voucher.name,
				"date": voucher.posting_date,
			}
		)

	def subtract_delivery(self, item_variant, set_combination, quantity):
		row = self._exact(item_variant, set_combination)
		if not row:
			return False
		row["delivered"] = max(row["delivered"] - flt(quantity), 0)
		return True

	def as_dict(self):
		return {
			"rows": [
				{
					"name": data["row"].name,
					"item_variant": data["item_variant"],
					"set_combination": data["set_combination"],
					"delivered_quantity": cint(data["delivered"]),
					"received_qty": cint(data["received"]),
					"received_type_json": {
						received_type: flt(quantity, 3)
						for received_type, quantity in data["received_types"].items()
					},
				}
				for data in self.rows
			],
			"tracking": self.tracking,
			"total_delivered": cint(sum(data["delivered"] for data in self.rows)),
			"total_received": cint(sum(data["received"] for data in self.rows)),
			"received_types": {
				received_type: flt(quantity, 3)
				for received_type, quantity in _sum_received_types(
					data["received_types"] for data in self.rows
				).items()
			},
			"first_dc_date": self.first_dc_date,
			"last_dc_date": self.last_dc_date,
			"first_grn_date": self.first_grn_date,
			"last_grn_date": self.last_grn_date,
			"wo_delivered_completed_json": self.delivery_completed,
			"wo_delivered_incompleted_json": self.delivery_incomplete,
			"completed_items_json": self.received_completed,
			"incompleted_items_json": self.received_incomplete,
		}


def _sum_received_types(type_maps):
	totals = defaultdict(float)
	for type_map in type_maps:
		for received_type, quantity in type_map.items():
			totals[received_type] += flt(quantity)
	return totals


def _nonzero_received_types(value):
	return {
		received_type: flt(quantity, 3)
		for received_type, quantity in _json_dict(value).items()
		if flt(quantity, 3)
	}


def _source_documents(doctype, filters):
	return [
		frappe.get_doc(doctype, name)
		for name in frappe.get_all(
			doctype,
			filters={**filters, "docstatus": 1},
			pluck="name",
			order_by="posting_date asc, posting_time asc, creation asc",
		)
	]


def _update_date_range(state, source, prefix):
	date = source.posting_date
	first = f"first_{prefix}_date"
	last = f"last_{prefix}_date"
	if date and (not getattr(state, first) or date < getattr(state, first)):
		setattr(state, first, date)
	if date and (not getattr(state, last) or date > getattr(state, last)):
		setattr(state, last, date)


def _apply_delivery_challan(state, challan):
	process = _process_for_direction(challan.process_name, "delivery")
	process_doc = frappe.get_cached_doc("Process", challan.process_name)
	if process_doc.get("is_manual_entry_in_grn"):
		return
	stage = _process_stage(state.ipd, process)
	_update_date_range(state, challan, "dc")
	if stage == "cutting":
		return
	if _is_finishing_process(challan.process_name) or stage == state.ipd.stiching_in_stage:
		_apply_panel_delivery(state, challan, _panel_list(state.ipd, process))
		return
	if challan.get("includes_packing") or stage == state.ipd.pack_in_stage:
		for row in challan.get("items") or []:
			state.add_delivery(
				row.item_variant,
				row.set_combination,
				flt(row.delivered_quantity or row.qty),
				challan,
			)


def _apply_goods_received_note(state, grn):
	process = _process_for_direction(grn.process_name, "receipt")
	stage = _process_stage(state.ipd, process)
	_update_date_range(state, grn, "grn")
	if stage == "cutting":
		_apply_panel_receipt(state, grn, _panel_list(state.ipd, process))
		return
	if _is_finishing_process(grn.process_name):
		_apply_direct_receipt(state, grn)
		return
	if grn.get("includes_packing") or stage == state.ipd.pack_out_stage:
		_apply_packing_receipt(state, grn)
		return
	if stage == state.ipd.pack_in_stage:
		_apply_direct_receipt(state, grn)
		return
	if stage == state.ipd.stiching_in_stage:
		_apply_panel_receipt(state, grn, _panel_list(state.ipd, process))


def _apply_direct_receipt(state, grn):
	for row in grn.get("items") or []:
		state.add_received(
			row.item_variant,
			row.set_combination,
			row.quantity,
			row.received_type,
			grn,
		)


def _apply_packing_receipt(state, grn):
	ipd = state.ipd
	default_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	# Packing configuration is mutable, while a submitted GRN is historical.
	# Migrated F15 Work Orders retain the exact per-GRN projection in
	# work_order_track_pieces.  Reuse that immutable snapshot when present so a
	# later change from (for example) 5 to 10 pieces per pack cannot rewrite old
	# production.  A genuinely new GRN has no snapshot yet and follows the live
	# configuration paths below; the resulting tracking rows then become its
	# snapshot on persistence.
	snapshot_rows = state.source_tracking.get(("Goods Received Note", grn.name)) or []
	if snapshot_rows:
		snapshot_occurrences = defaultdict(int)
		for row in snapshot_rows:
			snapshot_combination = row.set_combination
			# F15 tracking rows did not always persist set_combination even
			# though the calculated Work Order row did.  Recover it only when
			# the item variant identifies one unambiguous calculated row.
			matching_rows = [
				candidate
				for candidate in state.rows
				if candidate["item_variant"] == row.item_variant
			]
			if not _json_dict(snapshot_combination) and matching_rows:
				occurrence = snapshot_occurrences[row.item_variant]
				snapshot_combination = matching_rows[
					occurrence % len(matching_rows)
				]["set_combination"]
				snapshot_occurrences[row.item_variant] += 1
			state.add_received(
				row.item_variant,
				snapshot_combination,
				_snapshot_received_quantity(state, grn, row),
				_snapshot_received_type(state, grn, row),
				grn,
			)
		return
	if grn.get("grn_deliverables"):
		for row in grn.grn_deliverables:
			state.add_received(
				row.item_variant,
				row.set_combination,
				row.quantity,
				default_type,
				grn,
			)
		return
	if is_dynamic_packing_grn(grn):
		for batch in grn.get("packing_batches") or []:
			ratio = _json_dict(batch.get("ratio_json") or batch.get("ratio"))
			for size, per_box in ratio.items():
				quantity = flt(batch.box_quantity) * flt(per_box)
				if quantity <= 0:
					continue
				combinations = [None]
				if ipd.is_set_item:
					combinations = [
						row
						for row in ipd.get("set_item_combination_details") or []
						if row.major_attribute_value == batch.colour
						or row.attribute_value == batch.colour
					] or list(ipd.get("set_item_combination_details") or [])
				for combination in combinations:
					attributes = {
						ipd.primary_item_attribute: size,
						ipd.packing_attribute: batch.colour,
					}
					set_combination = {"major_colour": batch.colour}
					if combination:
						attributes[ipd.packing_attribute] = combination.attribute_value
						attributes[ipd.set_item_attribute] = combination.set_item_attribute_value
						set_combination["major_part"] = ipd.major_attribute_value
					variant = get_or_create_variant(
						state.work_order.item,
						build_variant_attributes(attributes, ipd.pack_in_stage, ipd.name),
					)
					state.add_received(
						variant, set_combination, quantity, default_type, grn
					)
		return

	attribute_rows = []
	if ipd.is_set_item:
		attribute_rows = [
			{
				ipd.packing_attribute: row.attribute_value,
				ipd.set_item_attribute: row.set_item_attribute_value,
				"major_attr_value": row.major_attribute_value,
			}
			for row in ipd.get("set_item_combination_details") or []
		]
	else:
		attribute_rows = [
			{ipd.packing_attribute: row.attribute_value}
			for row in ipd.get("packing_attribute_details") or []
		]

	for row in grn.get("items") or []:
		if flt(row.quantity) <= 0:
			continue
		variant_doc = frappe.get_cached_doc("Item Variant", row.item_variant)
		for attribute_row in attribute_rows:
			attributes = get_variant_attr_details(row.item_variant)
			major_colour = (
				attribute_row.get("major_attr_value")
				if ipd.is_set_item
				else attribute_row[ipd.packing_attribute]
			)
			attributes.update(attribute_row)
			attributes.pop("major_attr_value", None)
			set_combination = {"major_colour": major_colour}
			if ipd.is_set_item:
				set_combination["major_part"] = ipd.major_attribute_value
			variant = get_or_create_variant(
				variant_doc.item,
				build_variant_attributes(attributes, ipd.pack_in_stage, ipd.name),
			)
			state.add_received(
				variant, set_combination, row.quantity, row.received_type, grn
			)


def _snapshot_received_type(state, grn, snapshot_row):
	"""Resolve the source GRN type for a persisted packing projection row."""

	default_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	positive_items = [row for row in grn.get("items") or [] if flt(row.quantity) > 0]
	all_types = {
		row.received_type or default_type
		for row in positive_items
		if row.received_type or default_type
	}
	if len(all_types) == 1:
		return next(iter(all_types))

	# Packing output and input variants share the primary size.  This preserves
	# mixed Accepted/Rework/etc. GRNs whenever a size identifies one source type.
	primary = state.ipd.primary_item_attribute
	snapshot_size = get_variant_attr_details(snapshot_row.item_variant).get(primary)
	size_types = {
		row.received_type or default_type
		for row in positive_items
		if get_variant_attr_details(row.item_variant).get(primary) == snapshot_size
		and (row.received_type or default_type)
	}
	return next(iter(size_types)) if len(size_types) == 1 else default_type


def _snapshot_received_quantity(state, grn, snapshot_row):
	"""Recover legacy fractional packing quantities lost by the Int snapshot field."""

	primary = state.ipd.primary_item_attribute
	snapshot_size = get_variant_attr_details(snapshot_row.item_variant).get(primary)
	size_items = [
		row
		for row in grn.get("items") or []
		if flt(row.quantity) > 0
		and get_variant_attr_details(row.item_variant).get(primary) == snapshot_size
	]
	if len(size_items) != 1:
		return snapshot_row.received_qty
	source_quantity = flt(size_items[0].quantity)
	# Only restore the decimal residue proven to have been truncated into the
	# legacy Int tracking field.  Integer packing ratios and GRN deliverables
	# continue to use their exact persisted projection quantity.
	if source_quantity != cint(source_quantity) and flt(
		snapshot_row.received_qty
	) == cint(source_quantity):
		return source_quantity
	return snapshot_row.received_qty


def _matches_panel_entry(ipd, entry, item_row, attributes, panel_parts):
	if _json_dict(entry.get("item_keys")) != _json_dict(item_row.set_combination):
		return False
	if not ipd.is_set_item:
		return True
	panel = attributes.get(ipd.stiching_attribute)
	return entry.get("attributes", {}).get(ipd.set_item_attribute) == panel_parts.get(panel)


def _apply_panel_delivery(state, challan, panel_list):
	if not state.delivery_incomplete:
		return
	ipd = state.ipd
	panel_parts = _panel_parts(ipd)
	for row in challan.get("items") or []:
		quantity = flt(
			row.get("delivered_quantity")
			or row.get("qty")
			or row.get("quantity")
		)
		if quantity <= 0:
			continue
		attributes = get_variant_attr_details(row.item_variant)
		panel = attributes.get(ipd.stiching_attribute)
		size = attributes.get(ipd.primary_item_attribute)
		if not panel or not size:
			continue
		for entry in state.delivery_incomplete.get("items") or []:
			if not _matches_panel_entry(ipd, entry, row, attributes, panel_parts):
				continue
			cell = entry.get("values", {}).get(size, {})
			if panel in cell:
				cell[panel] = flt(cell.get(panel)) + quantity
				break
	_apply_panel_completions(state, challan, panel_list, received_type=None)


def _apply_panel_receipt(state, grn, panel_list):
	if not state.received_incomplete:
		return
	ipd = state.ipd
	panel_parts = _panel_parts(ipd)
	received_types = []
	for row in grn.get("items") or []:
		quantity = flt(row.quantity)
		if quantity <= 0:
			continue
		attributes = get_variant_attr_details(row.item_variant)
		panel = attributes.get(ipd.stiching_attribute)
		size = attributes.get(ipd.primary_item_attribute)
		if not panel or not size:
			continue
		received_type = row.received_type or frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		)
		if received_type not in received_types:
			received_types.append(received_type)
		for entry in state.received_incomplete.get("items") or []:
			if not _matches_panel_entry(ipd, entry, row, attributes, panel_parts):
				continue
			cell = entry.get("values", {}).get(size, {})
			if panel in cell:
				panel_types = cell.get(panel) or {}
				if not isinstance(panel_types, dict):
					panel_types = {}
				panel_types[received_type] = flt(panel_types.get(received_type)) + quantity
				cell[panel] = panel_types
				break
	for received_type in received_types:
		_apply_panel_completions(
			state, grn, panel_list, received_type=received_type
		)


def _apply_panel_completions(state, voucher, panel_list, received_type):
	ipd = state.ipd
	requirements = _panel_requirements(ipd)
	completed = state.received_completed if received_type else state.delivery_completed
	incomplete = state.received_incomplete if received_type else state.delivery_incomplete
	for complete_entry, incomplete_entry in zip_longest(
		completed.get("items") or [], incomplete.get("items") or []
	):
		if not complete_entry or not incomplete_entry:
			continue
		for size, panels in (incomplete_entry.get("values") or {}).items():
			possible = sys.maxsize
			for panel, raw_quantity in (panels or {}).items():
				if panel not in panel_list:
					continue
				quantity = (
					flt((raw_quantity or {}).get(received_type))
					if received_type
					else flt(raw_quantity)
				)
				possible = min(
					possible,
					int(quantity // (requirements.get(panel) or 1)),
				)
			if possible in (0, sys.maxsize):
				continue
			if received_type:
				cell = complete_entry["values"].setdefault(size, {}) or {}
				cell[received_type] = flt(cell.get(received_type)) + possible
				complete_entry["values"][size] = cell
			else:
				complete_entry["values"][size] = flt(
					complete_entry["values"].get(size)
				) + possible
			for panel, raw_quantity in (panels or {}).items():
				if panel not in panel_list:
					continue
				used = possible * (requirements.get(panel) or 1)
				if received_type:
					raw_quantity[received_type] = flt(raw_quantity.get(received_type)) - used
				else:
					panels[panel] = flt(raw_quantity) - used
			_emit_completed_item(
				state, complete_entry, size, possible, voucher, received_type
			)
			if received_type:
				complete_entry["values"][size][received_type] -= possible
			else:
				complete_entry["values"][size] -= possible


def _emit_completed_item(state, entry, size, quantity, voucher, received_type):
	attributes = dict(entry.get("attributes") or {})
	attributes[state.ipd.primary_item_attribute] = size
	variant = get_or_create_variant(entry["name"], attributes)
	combination = _json_dict(entry.get("item_keys"))
	if received_type:
		state.add_received(variant, combination, quantity, received_type, voucher)
	else:
		state.add_delivery(variant, combination, quantity, voucher)


def _apply_return_grns(state, grns):
	if not grns:
		return
	process = _process_for_direction(grns[0].process_name, "delivery")
	stage = _process_stage(state.ipd, process)
	unmatched = []
	for grn in grns:
		for row in grn.get("items") or []:
			if not state.subtract_delivery(
				row.item_variant, row.set_combination, row.quantity
			):
				unmatched.append(row)
	if unmatched and (stage == "cutting" or stage == state.ipd.stiching_in_stage):
		panel_return = frappe._dict(
			{
				"name": grns[-1].name,
				"posting_date": grns[-1].posting_date,
				"items": unmatched,
			}
		)
		_apply_panel_return(
			state, panel_return, _panel_list(state.ipd, process)
		)


def _apply_panel_return(state, grn, panel_list):
	# Returns are calculated independently from the delivered remainder, matching
	# F15: complete returned panel sets first, then subtract those garment pieces.
	completed, incomplete = state._initial_panel_structures()
	if not completed or not incomplete:
		return
	original_completed = state.delivery_completed
	original_incomplete = state.delivery_incomplete
	state.delivery_completed = completed
	state.delivery_incomplete = incomplete
	before = {key: row["delivered"] for key, row in state.by_identity.items()}
	tracking_length = len(state.tracking)
	_apply_panel_delivery(state, grn, panel_list)
	for key, row in state.by_identity.items():
		returned = row["delivered"] - before[key]
		row["delivered"] = max(before[key] - returned, 0)
	del state.tracking[tracking_length:]
	state.delivery_completed = original_completed
	state.delivery_incomplete = original_incomplete


def calculate_work_order_piece_tracking(work_order: str) -> dict:
	"""Calculate the complete derived projection without persisting it."""

	doc = frappe.get_doc("Work Order", work_order)
	if doc.docstatus != 1:
		frappe.throw(_("Work Order {0} must be submitted.").format(frappe.bold(doc.name)))
	ipd = frappe.get_cached_doc("Item Production Detail", doc.production_detail)
	state = PieceState(doc, ipd)

	for challan in _source_documents(
		"Delivery Challan", {"work_order": doc.name}
	):
		_apply_delivery_challan(state, challan)

	grns = _source_documents(
		"Goods Received Note",
		{"against": "Work Order", "against_id": doc.name},
	)
	for grn in grns:
		if not grn.get("is_return"):
			_apply_goods_received_note(state, grn)
	_apply_return_grns(state, [grn for grn in grns if grn.get("is_return")])
	return state.as_dict()


def compare_work_order_piece_tracking(work_order: str) -> dict:
	"""Compact rollback-safe comparison against a migrated Work Order oracle."""

	doc = frappe.get_doc("Work Order", work_order)
	result = calculate_work_order_piece_tracking(work_order)
	actual = {row.name: row for row in doc.get("work_order_calculated_items") or []}
	row_mismatches = []
	for expected in result["rows"]:
		row = actual[expected["name"]]
		checks = {
			"delivered_quantity": (
				flt(row.delivered_quantity), expected["delivered_quantity"]
			),
			"received_qty": (flt(row.received_qty), expected["received_qty"]),
			"received_type_json": (
				_json_dict(row.received_type_json),
				expected["received_type_json"],
			),
		}
		different = {
			field: {"actual": values[0], "expected": values[1]}
			for field, values in checks.items()
			if values[0] != values[1]
		}
		if different:
			row_mismatches.append(
				{"item_variant": row.item_variant, "differences": different}
			)
	actual_totals = {
		"delivered": flt(doc.total_no_of_pieces_delivered, 3),
		"received": flt(doc.total_no_of_pieces_received, 3),
		"received_types": _nonzero_received_types(doc.received_types_json),
	}
	expected_totals = {
		"delivered": result["total_delivered"],
		"received": result["total_received"],
		"received_types": _nonzero_received_types(result["received_types"]),
	}
	return {
		"work_order": work_order,
		"matches": not row_mismatches and actual_totals == expected_totals,
		"actual": actual_totals,
		"expected": expected_totals,
		"row_mismatch_count": len(row_mismatches),
		"row_mismatches": row_mismatches[:10],
		"expected_tracking_rows": len(result["tracking"]),
	}


def audit_migrated_piece_tracking(limit: int = 0) -> dict:
	"""Compare migrated WOs that have submitted DC/GRN sources, without writes."""

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT wo.name
		FROM `tabWork Order` wo
		WHERE wo.docstatus = 1
		  AND (
			EXISTS (
				SELECT 1 FROM `tabDelivery Challan` dc
				WHERE dc.work_order = wo.name AND dc.docstatus = 1
			)
			OR EXISTS (
				SELECT 1 FROM `tabGoods Received Note` grn
				WHERE grn.against = 'Work Order'
				  AND grn.against_id = wo.name
				  AND grn.docstatus = 1
			)
		  )
		ORDER BY wo.modified DESC
		""",
		pluck=True,
	)
	if limit:
		rows = rows[: cint(limit)]
	mismatches = []
	errors = []
	for name in rows:
		try:
			comparison = compare_work_order_piece_tracking(name)
			if not comparison["matches"]:
				mismatches.append(comparison)
		except Exception as exc:  # audit result must retain every failing oracle
			errors.append({"work_order": name, "error": str(exc)})
	return {
		"checked": len(rows),
		"matched": len(rows) - len(mismatches) - len(errors),
		"mismatches": mismatches,
		"errors": errors,
	}


def _apply_projection(doc, result):
	by_name = {row["name"]: row for row in result["rows"]}
	for row in doc.get("work_order_calculated_items") or []:
		values = by_name[row.name]
		row.delivered_quantity = values["delivered_quantity"]
		row.received_qty = values["received_qty"]
		row.received_type_json = values["received_type_json"]
	doc.set("work_order_track_pieces", [])
	for row in result["tracking"]:
		doc.append("work_order_track_pieces", row)
	doc.total_no_of_pieces_delivered = result["total_delivered"]
	doc.total_no_of_pieces_received = result["total_received"]
	doc.received_types_json = result["received_types"]
	doc.first_dc_date = result["first_dc_date"]
	doc.last_dc_date = result["last_dc_date"]
	doc.first_grn_date = result["first_grn_date"]
	doc.last_grn_date = result["last_grn_date"]
	doc.end_date = result["last_grn_date"]
	doc.wo_delivered_completed_json = result["wo_delivered_completed_json"]
	doc.wo_delivered_incompleted_json = result["wo_delivered_incompleted_json"]
	doc.completed_items_json = result["completed_items_json"]
	doc.incompleted_items_json = result["incompleted_items_json"]
	doc.save(ignore_permissions=True)


def _lot_quantity_field(work_order, ipd):
	process = _process_for_direction(work_order.process_name, "receipt")
	if process == ipd.cutting_process:
		return "cut_qty"
	if work_order.get("includes_packing") or process == ipd.packing_process:
		return "pack_qty"
	if _is_finishing_process(work_order.process_name):
		return "stich_qty"
	return None


def _rebuild_lot_stage_quantities(lot):
	fields = ("cut_qty", "stich_qty", "pack_qty")
	totals = {field: defaultdict(float) for field in fields}
	for name in frappe.get_all(
		"Work Order",
		filters={"lot": lot.name, "docstatus": 1, "is_rework": 0},
		pluck="name",
	):
		work_order = frappe.get_doc("Work Order", name)
		ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
		field = _lot_quantity_field(work_order, ipd)
		if not field:
			continue
		for row in work_order.get("work_order_calculated_items") or []:
			totals[field][(row.item_variant, _json_key(row.set_combination))] += flt(
				row.received_qty
			)
	for row in lot.get("lot_order_details") or []:
		identity = (row.item_variant, _json_key(row.set_combination))
		for field in fields:
			row.set(field, flt(totals[field].get(identity), 3))
	lot.save(ignore_permissions=True)


def rebuild_work_order_piece_tracking(
	work_order: str, *, check_permission: bool = True
) -> dict:
	"""Lock and persist an idempotent projection from submitted DCs/GRNs."""

	# Lock the source row first to identify the Lot, then lock that shared Lot
	# before any consistent reads. Different Work Orders for one Lot can finish
	# in separate queue workers; taking the common lock at the start ensures the
	# second worker creates its read snapshot only after the first has committed.
	doc = frappe.get_doc("Work Order", work_order, for_update=True)
	locked_lot = frappe.get_doc("Lot", doc.lot, for_update=True)
	if check_permission:
		doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Work Order {0} must be submitted.").format(frappe.bold(doc.name)))
	result = calculate_work_order_piece_tracking(doc.name)
	_apply_projection(doc, result)
	_rebuild_lot_stage_quantities(locked_lot)
	# This is the authoritative post-calculation boundary. In the legacy flow,
	# Calculate Pieces only enqueued a worker, so on_update_after_submit could run
	# before the worker finished. Keeping the dependent rebuild here also remains
	# correct if this complete function is invoked by a queue worker later.
	from essdee_yrp.finishing.rebuild import sync_finishing_plans_from_work_order

	finishing_plans = sync_finishing_plans_from_work_order(doc)
	return {
		"work_order": doc.name,
		"total_delivered": result["total_delivered"],
		"total_received": result["total_received"],
		"received_types": result["received_types"],
		"source_rows": len(result["tracking"]),
		"finishing_plans": finishing_plans,
	}


@frappe.whitelist()
def calculate_completed_pieces(work_order: str) -> dict:
	return rebuild_work_order_piece_tracking(work_order, check_permission=True)


def on_delivery_challan_submit(doc, method=None):
	if doc.work_order and _has_piece_tracking_context(doc.work_order):
		rebuild_work_order_piece_tracking(doc.work_order, check_permission=False)


def on_delivery_challan_cancel(doc, method=None):
	if doc.work_order and _has_piece_tracking_context(doc.work_order):
		rebuild_work_order_piece_tracking(doc.work_order, check_permission=False)


def on_goods_received_note_submit(doc, method=None):
	if (
		doc.against == "Work Order"
		and doc.against_id
		and _has_piece_tracking_context(doc.against_id)
	):
		rebuild_work_order_piece_tracking(doc.against_id, check_permission=False)


def on_goods_received_note_cancel(doc, method=None):
	if (
		doc.against == "Work Order"
		and doc.against_id
		and _has_piece_tracking_context(doc.against_id)
	):
		rebuild_work_order_piece_tracking(doc.against_id, check_permission=False)


def _has_piece_tracking_context(work_order: str) -> bool:
	"""Essdee replay is meaningful only for an IPD-backed Work Order.

	Base YRP can coexist on the site and legitimately submit generic Work Orders.
	Those transactions still use the base stock engine, but have no panel/size
	matrix for Essdee to replay.
	"""
	return bool(frappe.db.get_value("Work Order", work_order, "production_detail"))
