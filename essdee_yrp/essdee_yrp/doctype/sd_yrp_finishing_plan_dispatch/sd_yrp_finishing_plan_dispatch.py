# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt
from itertools import groupby
from operator import itemgetter

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_read_context import attribute_read_scope
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item.yrp_item import (
	build_variant_attributes,
	get_attribute_details,
	get_or_create_variant,
)

from essdee_yrp.dynamic_packing import aggregate_batch_pieces
from essdee_yrp.finishing.dispatch_locations import get_dispatch_locations
from essdee_yrp.finishing.packing import (
	get_finishing_packing_summary,
	get_ipd_packing_config,
	prepare_dynamic_batch_dispatch,
)
from essdee_yrp.finishing.transactions import populate_stock_rates


class SDYRPFinishingPlanDispatch(Document):
	def validate(self):
		is_fresh = (
			self.is_new()
			or not self.name
			or not frappe.db.exists("SD YRP Finishing Plan Dispatch", self.name)
		)
		if is_fresh and not self.amended_from:
			expected = get_current_fiscal_naming_series()
			if self.naming_series and self.naming_series != expected:
				frappe.throw(
					f"Finishing Plan Dispatch Naming Series must be {expected} for the configured fiscal year"
				)
			self.naming_series = expected

	def before_cancel(self):
		if self.stock_entry:
			stock_entry = frappe.get_doc("YRP Stock Entry", self.stock_entry)
			if stock_entry.docstatus == 1:
				stock_entry.cancel()

	def onload(self):
		if not self.amended_from and not self.naming_series:
			self.naming_series = get_current_fiscal_naming_series()
		if self.docstatus == 0 and self.finishing_items:
			saved_items = update_if_string_instance(self.finishing_items) or []
			self.set_onload(
				"items",
				merge_saved_finishing_items(fetch_fp_items(), saved_items),
			)
			return
		if not self.finishing_plan_dispatch_items:
			return
		self.set_onload("items", _build_saved_item_view(self))

	def before_validate(self):
		if not self.finishing_items:
			return
		# update_if_string_instance turns an empty selection ("[]") into {}.
		finishing_items = update_if_string_instance(self.finishing_items) or []
		if not isinstance(finishing_items, list):
			frappe.throw("Finishing Items must be a JSON list")

		items = []
		colour_details = []
		packing_batch_dispatches = []
		selected_finishing_items = []
		for row in finishing_items:
			if not _has_dispatch_request(row):
				continue
			selected_finishing_items.append(row)
			fp_doc = frappe.get_doc("SD YRP Finishing Plan", row["doc_name"])
			fp_doc.check_permission("read")
			packing_summary = get_finishing_packing_summary(fp_doc)
			dynamic_ratio_packing = bool(packing_summary.dynamic_ratio_packing)
			requested_batches = row.get("batch_dispatches") or []
			if dynamic_ratio_packing:
				_add_dynamic_dispatch_rows(
					row,
					fp_doc,
					requested_batches,
					items,
					packing_batch_dispatches,
				)
			elif requested_batches:
				frappe.throw(f"Packing batches are not valid for legacy Finishing Plan {fp_doc.name}")
			else:
				_add_legacy_dispatch_rows(row, items)

			if row.get("colour_grid"):
				colour_details.append(
					{
						"lot": row["lot"],
						"item": row["item"],
						"grid": row["colour_grid"],
					}
				)

		self.set("finishing_plan_dispatch_items", items)
		# The fetch grid can contain every open Finishing Plan on the site. Keep the
		# document snapshot limited to rows the operator actually selected; otherwise
		# every save reloads and validates unrelated plans and the Desk request can
		# become impractically slow.
		self.finishing_items = frappe.as_json(selected_finishing_items)
		self.dispatch_colour_details = frappe.as_json(colour_details) if colour_details else None
		self.packing_batch_dispatch_json = (
			frappe.as_json(packing_batch_dispatches) if packing_batch_dispatches else None
		)

	def before_submit(self):
		selected = [row for row in self.finishing_plan_dispatch_items if flt(row.quantity) > 0]
		if not selected:
			frappe.throw("Select at least one Finishing Plan quantity or packing batch to dispatch")
		self.set("finishing_plan_dispatch_items", [row.as_dict() for row in selected])
		_set_dispatch_snapshot(self)


@frappe.whitelist()
def get_current_fiscal_naming_series(reference_date=None):
	"""Return the authoritative Finishing Plan Dispatch series for MRP's FY."""
	start = frappe.db.get_single_value("SD YRP MRP Settings", "fiscal_year_start_date")
	end = frappe.db.get_single_value("SD YRP MRP Settings", "fiscal_year_end_date")
	if not start or not end:
		frappe.throw("Configure Fiscal Year Start Date and Fiscal Year End Date in MRP Settings")
	start = getdate(start)
	end = getdate(end)
	current = getdate(reference_date or nowdate())
	if end < start:
		frappe.throw("MRP Settings Fiscal Year End Date cannot precede Start Date")
	if not start <= current <= end:
		frappe.throw(f"Date {current} is outside the configured MRP fiscal year {start} to {end}")
	return f"FPD-{start.strftime('%y')}{end.strftime('%y')}-"


def _has_dispatch_request(row):
	if any(flt(batch.get("box_quantity")) > 0 for batch in row.get("batch_dispatches") or []):
		return True
	return any(flt(value.get("dispatch_qty")) > 0 for value in (row.get("values") or {}).values())


def _build_saved_item_view(doc):
	saved_batches = update_if_string_instance(doc.packing_batch_dispatch_json) or []
	saved_by_plan = {}
	for batch in saved_batches:
		saved_by_plan.setdefault(batch.get("finishing_plan"), []).append(
			{
				"batch_row": batch.get("batch_row"),
				"box_quantity": batch.get("box_quantity"),
			}
		)

	items = [row.as_dict() for row in doc.finishing_plan_dispatch_items]
	items.sort(key=itemgetter("lot", "item"))
	item_details = []
	for (lot, item), variants in groupby(items, key=itemgetter("lot", "item")):
		variants = list(variants)
		fp_name = variants[0]["against_id"]
		ipd = attribute_db.get_value("SD YRP Lot", lot, "production_detail")
		primary, dependent, pack_out_stage = attribute_db.get_value(
			"YRP Item Production Detail",
			ipd,
			["primary_item_attribute", "dependent_attribute", "pack_out_stage"],
		)
		fp_doc = frappe.get_doc("SD YRP Finishing Plan", fp_name)
		packing_summary = get_finishing_packing_summary(fp_doc)
		packing_config = get_ipd_packing_config(lot)
		row = {
			"lot": lot,
			"item": item,
			"doc_name": fp_name,
			"uom": variants[0]["uom"],
			"values": {},
			"total": {"total_qty": 0, "total_dispatch": 0},
			"primary_attribute": primary,
			"dependent_attribute": dependent,
			"stage": pack_out_stage,
			"packing_config": packing_config,
			"dynamic_ratio_packing": packing_summary.dynamic_ratio_packing,
			"packing_batches": packing_summary.packing_batches,
			"batch_dispatches": saved_by_plan.get(fp_name, []),
		}
		if packing_summary.dynamic_ratio_packing or (
			packing_config.get("based_on_other_attribute_mapping")
			and packing_config.get("packing_mode") == "Size Wise Packing"
		):
			row["uom"] = attribute_db.get_value("SD YRP Lot", lot, "packing_uom") or row["uom"]
		for variant in variants:
			size = get_variant_attr_details(variant["item_variant"])[primary]
			value = row["values"].setdefault(
				size,
				{
					"qty": 0,
					"row_detail": variant["against_id_detail"],
					"dispatch_qty": 0,
				},
			)
			piece_quantity = flt(variant.get("packing_piece_quantity")) or flt(variant["quantity"])
			value["qty"] = max(flt(value["qty"]), flt(variant["balance_qty"]))
			value["dispatch_qty"] += piece_quantity
			row["total"]["total_dispatch"] += piece_quantity
		row["total"]["total_qty"] = sum(flt(value["qty"]) for value in row["values"].values())
		item_details.append(row)

	colour_map = {}
	for entry in update_if_string_instance(doc.dispatch_colour_details) or []:
		colour_map[(entry.get("lot"), entry.get("item"))] = entry.get("grid") or {}
	for row in item_details:
		row["colour_grid"] = colour_map.get((row["lot"], row["item"]), {})
	return item_details


def _add_dynamic_dispatch_rows(
	row,
	fp_doc,
	requested_batches,
	items,
	packing_batch_dispatches,
):
	for value in row["values"].values():
		value["dispatch_qty"] = 0
	if not requested_batches:
		return
	normalized = prepare_dynamic_batch_dispatch(fp_doc, requested_batches)
	size_pieces, _boxes, _pieces = aggregate_batch_pieces(normalized)
	for size, quantity in size_pieces.items():
		if size not in row["values"]:
			frappe.throw(f"Size {size} is not available in Finishing Plan {fp_doc.name}")
		row["values"][size]["dispatch_qty"] = quantity
	packing_batch_dispatches.extend({**batch, "finishing_plan": fp_doc.name} for batch in normalized)

	colour_grid = {}
	stock_groups = {}
	for batch in normalized:
		colour_grid.setdefault(_attribute_value(batch["colour"]), {})
		for size, quantity in batch["size_pieces"].items():
			colour_grid[_attribute_value(batch["colour"])][size] = (
				colour_grid[_attribute_value(batch["colour"])].get(size, 0) + quantity
			)
		for size, stock_quantity in (batch.get("stock_quantities") or batch["size_pieces"]).items():
			key = (
				size,
				batch.get("stock_uom") or row["uom"],
				batch["packing_calculation_version"],
			)
			group = stock_groups.setdefault(key, {"stock_qty": 0, "piece_qty": 0})
			group["stock_qty"] += flt(stock_quantity)
			group["piece_qty"] += flt(batch["size_pieces"].get(size))
	row["colour_grid"] = colour_grid

	for (size, stock_uom, _version), quantities in stock_groups.items():
		attributes = build_variant_attributes({row["primary_attribute"]: size}, row["stage"], row["item"])
		items.append(
			{
				"item_variant": get_or_create_variant(row["item"], attributes),
				"lot": row["lot"],
				"balance_qty": row["values"][size]["qty"],
				"quantity": quantities["stock_qty"],
				"uom": stock_uom,
				"item": row["item"],
				"against_id": row["doc_name"],
				"against_id_detail": row["values"][size]["row_detail"],
				"packing_source": "batch",
				"packing_piece_quantity": quantities["piece_qty"],
			}
		)


def _add_legacy_dispatch_rows(row, items):
	for size, value in row["values"].items():
		dispatch_quantity = flt(value["dispatch_qty"])
		if dispatch_quantity < 0:
			frappe.throw(f"Dispatch quantity cannot be negative for {row['doc_name']} / {size}")
		if dispatch_quantity > flt(value["qty"]):
			frappe.throw(
				f"Dispatch quantity for {row['doc_name']} / {size} exceeds "
				f"the available balance of {flt(value['qty']):g}"
			)
		if not dispatch_quantity:
			continue
		attributes = build_variant_attributes({row["primary_attribute"]: size}, row["stage"], row["item"])
		items.append(
			{
				"item_variant": get_or_create_variant(row["item"], attributes),
				"lot": row["lot"],
				"balance_qty": value["qty"],
				"quantity": dispatch_quantity,
				"uom": row["uom"],
				"item": row["item"],
				"against_id": row["doc_name"],
				"against_id_detail": value["row_detail"],
				"packing_source": "legacy",
				"packing_piece_quantity": 0,
			}
		)


def _set_dispatch_snapshot(doc):
	fp_cache = {}
	batch_dispatch_by_size = {}
	for row in doc.finishing_plan_dispatch_items:
		if row.packing_source != "batch":
			continue
		fp_doc = frappe.get_doc("SD YRP Finishing Plan", row.against_id)
		primary = attribute_db.get_value(
			"YRP Item Production Detail", fp_doc.production_detail, "primary_item_attribute"
		)
		size = get_variant_attr_details(row.item_variant).get(primary, "")
		key = (row.against_id, size)
		batch_dispatch_by_size[key] = batch_dispatch_by_size.get(key, 0) + flt(row.packing_piece_quantity)

	seen_batch_sizes = set()
	for row in doc.finishing_plan_dispatch_items:
		fp_name = row.against_id
		if fp_name not in fp_cache:
			fp_cache[fp_name] = _get_dispatch_snapshot_context(fp_name)
		context = fp_cache[fp_name]
		size = get_variant_attr_details(row.item_variant).get(context["primary"], "")
		component_count = len(context["components_by_size"].get(size, ())) or 1
		if row.packing_source == "batch":
			key = (fp_name, size)
			prior_dispatched = flt(
				(context["packing_summary"].get("sizes") or {}).get(size, {}).get("dispatched")
			)
			row.total_dispatched = prior_dispatched + batch_dispatch_by_size.get(key, 0)
			if key in seen_batch_sizes:
				row.total_dispatched = 0
			seen_batch_sizes.add(key)
			cutting_quantity = context["cutting_by_size"].get(size, 0) / component_count
		else:
			already_dispatched = (
				frappe.db.get_value("SD YRP Finishing Plan GRN Detail", row.against_id_detail, "dispatched")
				or 0
			)
			denominator = component_count * context["pieces_per_box"]
			cutting_quantity = context["cutting_by_size"].get(size, 0) / denominator
			row.total_dispatched = already_dispatched + row.quantity
		row.dispatch_pct = (
			round(row.total_dispatched / cutting_quantity * 100, 2) if cutting_quantity > 0 else 0
		)
	doc.fp_total_dispatched = sum(flt(row.total_dispatched) for row in doc.finishing_plan_dispatch_items)


def _get_dispatch_snapshot_context(fp_name):
	fp_doc = frappe.get_doc("SD YRP Finishing Plan", fp_name)
	ipd_fields = attribute_db.get_value(
		"YRP Item Production Detail",
		fp_doc.production_detail,
		["primary_item_attribute", "is_set_item", "set_item_attribute"],
		as_dict=True,
	)
	packing_summary = get_finishing_packing_summary(fp_doc)
	cutting_by_size = {}
	components_by_size = {}
	for row in fp_doc.finishing_plan_details:
		attributes = get_variant_attr_details(row.item_variant)
		size = attributes.get(ipd_fields.primary_item_attribute, "")
		cutting_by_size[size] = cutting_by_size.get(size, 0) + flt(row.cutting_qty)
		if ipd_fields.is_set_item:
			components_by_size.setdefault(size, set()).add(attributes.get(ipd_fields.set_item_attribute, ""))
	return {
		"primary": ipd_fields.primary_item_attribute,
		"cutting_by_size": cutting_by_size,
		"pieces_per_box": flt(fp_doc.pieces_per_box) or 1,
		"components_by_size": components_by_size,
		"packing_summary": packing_summary,
	}


@frappe.whitelist()
def fetch_fp_items():
	with attribute_read_scope():
		return _read_fetch_fp_items()


def _read_fetch_fp_items():
	finishing_plans = frappe.db.sql(
		"""
			SELECT DISTINCT fp.name
			FROM `tabSD YRP Finishing Plan` fp
			INNER JOIN `tabSD YRP Finishing Plan GRN Detail` detail ON detail.parent = fp.name
			WHERE fp.docstatus < 2
				AND COALESCE(detail.quantity, 0) - COALESCE(detail.dispatched, 0) > 0
			ORDER BY fp.modified DESC
		""",
		pluck=True,
	)
	item_details = []
	for fp_name in finishing_plans:
		if not frappe.has_permission("SD YRP Finishing Plan", "read", doc=fp_name):
			continue
		fp_doc = frappe.get_lazy_doc("SD YRP Finishing Plan", fp_name)
		packing_summary = get_finishing_packing_summary(fp_doc)
		box_uom, piece_uom = attribute_db.get_value("SD YRP Lot", fp_doc.lot, ["uom", "packing_uom"])
		packing_config = get_ipd_packing_config(fp_doc.lot)
		primary, dependent, pack_out_stage = attribute_db.get_value(
			"YRP Item Production Detail",
			fp_doc.production_detail,
			["primary_item_attribute", "dependent_attribute", "pack_out_stage"],
		)
		row = {
			"lot": fp_doc.lot,
			"item": fp_doc.item,
			"doc_name": fp_name,
			"uom": (
				piece_uom
				if packing_summary.dynamic_ratio_packing
				or (
					packing_config.get("based_on_other_attribute_mapping")
					and packing_config.get("packing_mode") == "Size Wise Packing"
				)
				else box_uom
			),
			"values": {},
			"total": {"total_qty": 0, "total_dispatch": 0},
			"primary_attribute": primary,
			"dependent_attribute": dependent,
			"stage": pack_out_stage,
			"packing_config": packing_config,
			"dynamic_ratio_packing": packing_summary.dynamic_ratio_packing,
			"packing_batches": packing_summary.packing_batches,
			"batch_dispatches": [],
		}
		for detail in fp_doc.finishing_plan_grn_details:
			balance = flt(detail.quantity) - flt(detail.dispatched)
			size = get_variant_attr_details(detail.item_variant).get(primary)
			row["values"][size] = {
				"qty": balance,
				"row_detail": detail.name,
				"dispatch_qty": 0,
			}
			row["total"]["total_qty"] += balance
		if row["total"]["total_qty"] > 0:
			item_details.append(row)
	return item_details


def merge_saved_finishing_items(fresh_items, saved_items):
	saved_by_plan = {row.get("doc_name"): row for row in saved_items or [] if row.get("doc_name")}
	for fresh in fresh_items:
		saved = saved_by_plan.get(fresh.get("doc_name")) or {}
		fresh["colour_grid"] = saved.get("colour_grid") or {}
		if fresh.get("dynamic_ratio_packing"):
			valid_batches = {batch.get("batch_row") for batch in fresh.get("packing_batches") or []}
			fresh["batch_dispatches"] = [
				{
					"batch_row": batch.get("batch_row"),
					"box_quantity": batch.get("box_quantity"),
				}
				for batch in saved.get("batch_dispatches") or []
				if batch.get("batch_row") in valid_batches
			]
		else:
			for size, value in fresh.get("values", {}).items():
				value["dispatch_qty"] = flt((saved.get("values") or {}).get(size, {}).get("dispatch_qty"))
	return fresh_items


@frappe.whitelist()
def create_stock_dispatch(
	doc_name,
	from_supplier,
	from_warehouse,
	to_supplier,
	to_warehouse,
	vehicle_no,
	goods_value,
):
	dispatch_doc = frappe.get_doc("SD YRP Finishing Plan Dispatch", doc_name)
	# Dispatching posts stock and updates the submitted FPD.  A user who can
	# merely read the dispatch must never be able to invoke this action directly.
	dispatch_doc.check_permission("write")
	if dispatch_doc.docstatus != 1:
		frappe.throw("Submit the Finishing Plan Dispatch before dispatching stock")
	if dispatch_doc.stock_entry:
		existing_status = frappe.db.get_value("YRP Stock Entry", dispatch_doc.stock_entry, "docstatus")
		if existing_status != 2:
			frappe.throw(f"Stock Entry {dispatch_doc.stock_entry} already exists")
	locations = get_dispatch_locations(from_supplier, from_warehouse, to_supplier, to_warehouse)

	batch_requests = {}
	for batch in update_if_string_instance(dispatch_doc.packing_batch_dispatch_json) or []:
		batch_requests.setdefault(batch.get("finishing_plan"), []).append(
			{
				"batch_row": batch.get("batch_row"),
				"box_quantity": batch.get("box_quantity"),
			}
		)
	dynamic_dispatches = []
	for fp_name, requests in batch_requests.items():
		if not fp_name:
			frappe.throw("Packing batch dispatch is missing its Finishing Plan")
		fp_doc = frappe.get_doc("SD YRP Finishing Plan", fp_name)
		dynamic_dispatches.extend(
			{**batch, "finishing_plan": fp_name} for batch in prepare_dynamic_batch_dispatch(fp_doc, requests)
		)
	versions_by_source = {}
	for batch in dynamic_dispatches:
		key = (batch["finishing_plan"], batch.get("stock_uom"))
		versions_by_source.setdefault(key, set()).add(batch["packing_calculation_version"])

	default_received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	stock_entry = frappe.new_doc("YRP Stock Entry")
	stock_entry.update(
		{
			"purpose": "Material Issue",
			"against": "SD YRP Finishing Plan Dispatch",
			"against_id": doc_name,
			**locations,
			"vehicle_no": vehicle_no,
			"additional_amount": goods_value,
			"packing_batch_dispatch_json": (
				frappe.as_json(dynamic_dispatches) if dynamic_dispatches else None
			),
			"dispatch_colour_details": dispatch_doc.dispatch_colour_details,
		}
	)
	for row in dispatch_doc.finishing_plan_dispatch_items:
		stock_row = stock_entry.append(
			"items",
			{
				"item": row.item_variant,
				"qty": row.quantity,
				"lot": row.lot,
				"received_type": default_received_type,
				"uom": row.uom,
				"set_combination": "{}",
			},
		)
		stock_row._packing_finishing_plan = row.against_id
		versions = versions_by_source.get((row.against_id, row.uom), set())
		if row.packing_source == "batch" and len(versions) == 1:
			stock_row._packing_calculation_version = next(iter(versions))
	populate_stock_rates(stock_entry, from_warehouse)
	stock_entry.insert()
	stock_entry.submit()
	return stock_entry.name


@frappe.whitelist()
def get_fpd_print_data(doc_name):
	"""MRP's print rows per lot and item: the frozen snapshot once submitted, live Finishing Plan figures in draft."""
	dispatch_doc = frappe.get_doc("SD YRP Finishing Plan Dispatch", doc_name)
	dispatch_doc.check_permission("print")
	items = [row.as_dict() for row in dispatch_doc.finishing_plan_dispatch_items]
	items.sort(key=itemgetter("lot", "item"))
	return [
		get_dispatch_print_row(lot, item_name, list(variants), dispatch_doc.docstatus == 1)
		for (lot, item_name), variants in groupby(items, key=itemgetter("lot", "item"))
	]


def get_dispatch_print_row(lot, item_name, variants, is_submitted):
	context = _get_dispatch_snapshot_context(variants[0]["against_id"])
	dispatch_by_size = {}
	frozen_by_size = {}
	for row in variants:
		size = get_variant_attr_details(row["item_variant"]).get(context["primary"], "")
		dispatch_by_size[size] = dispatch_by_size.get(size, 0) + (
			flt(row.get("packing_piece_quantity")) or flt(row["quantity"])
		)
		frozen = frozen_by_size.setdefault(size, {"total_dispatched": 0.0, "dispatch_pct": 0.0})
		frozen["total_dispatched"] = max(frozen["total_dispatched"], flt(row.get("total_dispatched")))
		frozen["dispatch_pct"] = max(frozen["dispatch_pct"], flt(row.get("dispatch_pct")))

	progress = (
		frozen_by_size if is_submitted else get_live_dispatch_progress(variants[0]["against_id"], context)
	)
	shown_sizes = (
		set(dispatch_by_size) if is_submitted else set(dispatch_by_size) | set(context["cutting_by_size"])
	)
	ordered_sizes = get_attribute_details(item_name).get("primary_attribute_values", [])
	size_data = {
		size: {
			"dispatch_qty": dispatch_by_size.get(size, 0),
			"dispatch_pct": round(progress.get(size, {}).get("dispatch_pct", 0), 1),
			"total_dispatched": progress.get(size, {}).get("total_dispatched", 0),
		}
		for size in ordered_sizes
		if size in shown_sizes
	}
	uom = variants[0]["uom"]
	if any(row.get("packing_source") == "batch" for row in variants):
		uom = attribute_db.get_value("SD YRP Lot", lot, "packing_uom") or uom
	return {
		"lot": lot,
		"item": item_name,
		"stage": attribute_db.get_value(
			"YRP Item Production Detail",
			attribute_db.get_value("SD YRP Lot", lot, "production_detail"),
			"pack_out_stage",
		)
		or "",
		"uom": uom or "",
		"sizes": list(size_data),
		"size_data": size_data,
		"total_dispatch": sum(value["dispatch_qty"] for value in size_data.values()),
		"total_dispatched_all": sum(value["total_dispatched"] for value in size_data.values()),
	}


def get_live_dispatch_progress(fp_name, context):
	"""Draft progress per size: dispatched so far against the Finishing Plan's cut boxes."""
	dispatched_by_size = {}
	for detail in frappe.get_all(
		"SD YRP Finishing Plan GRN Detail",
		filters={"parent": fp_name},
		fields=["item_variant", "dispatched"],
	):
		size = get_variant_attr_details(detail.item_variant).get(context["primary"], "")
		dispatched_by_size[size] = dispatched_by_size.get(size, 0) + flt(detail.dispatched)
	progress = {}
	for size in set(dispatched_by_size) | set(context["cutting_by_size"]):
		denominator = len(context["components_by_size"].get(size, ())) or 1
		if not context["packing_summary"].dynamic_ratio_packing:
			denominator *= context["pieces_per_box"]
		cutting_boxes = context["cutting_by_size"].get(size, 0) / denominator
		dispatched = dispatched_by_size.get(size, 0)
		progress[size] = {
			"total_dispatched": dispatched,
			"dispatch_pct": dispatched / cutting_boxes * 100 if cutting_boxes else 0,
		}
	return progress


FinishingPlanDispatch = SDYRPFinishingPlanDispatch
