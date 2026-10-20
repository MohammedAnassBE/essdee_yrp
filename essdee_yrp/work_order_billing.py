from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import flt, getdate
from yrp.attribute_links import value as _attribute_value
from yrp.stock.uom import resolve_item_uom
from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant
from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import (
	_get_item_group,
	_get_tax_rate,
	_normal_json,
)
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import get_variant_attributes

from essdee_yrp.overrides.work_order import _combination_key
from essdee_yrp.work_order_piece_tracking import get_selected_grn_piece_quantities

RATE_PRECISION = 6
VALUE_TOLERANCE = 0.01
QUANTITY_TARGET_FIELDS = {
	"physical": ("YRP Purchase Invoice Item", "qty"),
	"commercial": ("SD YRP Essdee Purchase Invoice Item", "qty"),
	"billed": ("YRP PI Work Order Billed Detail", "quantity"),
}


def _active_purchase_invoice_names(names):
	names = list(dict.fromkeys(name for name in (names or []) if name))
	if not names:
		return set()
	return set(
		frappe.get_all(
			"YRP Purchase Invoice",
			filters={"name": ["in", names], "docstatus": ["!=", 2]},
			pluck="name",
			limit_page_length=0,
		)
	)


def _active_invoice_links_for_grns(grns):
	grns = list(dict.fromkeys(grn for grn in (grns or []) if grn))
	if not grns or not frappe.db.exists("DocType", "YRP Purchase Invoice GRN"):
		return {}
	rows = frappe.get_all(
		"YRP Purchase Invoice GRN",
		filters={"grn": ["in", grns], "parenttype": "YRP Purchase Invoice"},
		fields=["grn", "parent"],
		limit_page_length=0,
	)
	active = _active_purchase_invoice_names(row.parent for row in rows)
	links = defaultdict(set)
	for row in rows:
		if row.parent in active:
			links[row.grn].add(row.parent)
	return dict(links)


def _is_active_purchase_invoice(name):
	return name in _active_purchase_invoice_names([name])


def _validate_selected_grn(grn_name, supplier=None, against=None, purchase_invoice=None):
	if not frappe.db.exists("YRP Goods Received Note", grn_name):
		frappe.throw(_("Goods Received Note {0} does not exist.").format(grn_name))
	frappe.has_permission("YRP Goods Received Note", "read", doc=grn_name, throw=True)
	grn = frappe.db.get_value(
		"YRP Goods Received Note",
		grn_name,
		["docstatus", "supplier", "against", "purchase_invoice_name", "is_return"],
		as_dict=True,
	)
	if grn.docstatus != 1:
		frappe.throw(_("Goods Received Note {0} must be submitted.").format(grn_name))
	if supplier and grn.supplier != supplier:
		frappe.throw(_("Goods Received Note {0} belongs to another supplier.").format(grn_name))
	if against and grn.against != against:
		frappe.throw(_("Goods Received Note {0} is against {1}.").format(grn_name, grn.against))
	if grn.against == "YRP Work Order" and grn.is_return:
		frappe.throw(
			_(
				"Goods Received Note {0} is a return of delivered material, not processed work, "
				"so it cannot be billed."
			).format(grn_name)
		)
	owners = set(_active_invoice_links_for_grns([grn_name]).get(grn_name, set()))
	if _is_active_purchase_invoice(grn.purchase_invoice_name):
		owners.add(grn.purchase_invoice_name)
	owners.discard(purchase_invoice)
	if owners:
		owner = sorted(owners)[0]
		frappe.throw(
			_("Goods Received Note {0} is already linked to Purchase Invoice {1}.").format(
				grn_name, owner
			)
		)
	return grn


def commercial_group_key(item, lot, uom, source_rate, tax=None):
	"""Return a stable identity that deliberately excludes the editable rate."""
	payload = [
		item or "",
		lot or "",
		uom or "",
		round(flt(source_rate), RATE_PRECISION),
		tax or "",
	]
	encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
	return hashlib.sha256(encoded.encode()).hexdigest()


def _quantity_precisions():
	return {
		key: get_field_precision(frappe.get_meta(doctype).get_field(fieldname))
		for key, (doctype, fieldname) in QUANTITY_TARGET_FIELDS.items()
	}


def _stored_quantity(value, precision, source, target):
	quantity = flt(value)
	rounded = round(quantity, precision)
	if not math.isfinite(quantity) or abs(quantity - rounded) > 10 ** -(precision + 6):
		doctype, fieldname = QUANTITY_TARGET_FIELDS[target]
		frappe.throw(
			_("{0} quantity {1} cannot be stored in {2}.{3} at precision {4}.").format(
				source,
				value,
				doctype,
				fieldname,
				precision,
			)
		)
	return rounded


def _validate_selected_grn_quantities(grns, precision):
	for grn in grns:
		for row_number, row in enumerate(grn.get("items") or [], start=1):
			_stored_quantity(
				row.get("quantity"),
				precision,
				_("Goods Received Note {0} row {1}").format(
					grn.name,
					row.get("idx") or row_number,
				),
				"physical",
			)


def build_work_order_invoice_payload(
	grns,
	*,
	supplier=None,
	purchase_invoice=None,
	final_rates=None,
	expense_heads=None,
):
	"""Build commercial, verification, and physical valuation rows together."""
	grn_docs = []
	for grn_name in list(dict.fromkeys(grns or [])):
		_validate_selected_grn(grn_name, supplier, "YRP Work Order", purchase_invoice)
		grn_docs.append(frappe.get_doc("YRP Goods Received Note", grn_name))
	if not grn_docs:
		frappe.throw(_("Please select at least one GRN."))
	quantity_precisions = _quantity_precisions()
	_validate_selected_grn_quantities(grn_docs, quantity_precisions["physical"])
	is_historical = _is_historical_selection(grn_docs)

	by_work_order = defaultdict(list)
	for grn in grn_docs:
		if not grn.against_id:
			frappe.throw(_("Goods Received Note {0} has no Work Order.").format(grn.name))
		by_work_order[grn.against_id].append(grn)

	final_rates = {key: flt(value) for key, value in (final_rates or {}).items()}
	expense_heads = expense_heads or {}
	commercial = {}
	hidden = {}
	billed_rows = []
	warnings = []
	has_gstin = bool(frappe.db.get_value("Supplier", supplier, "gstin"))

	for work_order_name, selected_grns in by_work_order.items():
		work_order = frappe.get_doc("YRP Work Order", work_order_name)
		context = _build_modern_work_order_context(
			work_order,
			selected_grns,
			is_historical=is_historical,
			has_gstin=has_gstin,
			final_rates=final_rates,
			expense_heads=expense_heads,
			warnings=warnings,
			quantity_precisions=quantity_precisions,
		)
		work_order_commercial, work_order_hidden, work_order_billed = _build_modern_work_order_rows(
			work_order,
			selected_grns,
			context,
		)

		_merge_commercial_rows(commercial, work_order_commercial)
		_merge_hidden_rows(hidden, work_order_hidden)
		billed_rows.extend(work_order_billed)

	commercial_rows = []
	for row in commercial.values():
		row["qty"] = round(flt(row["qty"]), quantity_precisions["commercial"])
		row["amount"] = flt(row["qty"]) * flt(row["rate"])
		# A rate tier that only zero-quantity items fall into bills nothing.
		if row["qty"]:
			commercial_rows.append(row)

	hidden_rows = list(hidden.values())
	for row in hidden_rows:
		row["qty"] = round(flt(row["qty"]), quantity_precisions["physical"])
		row["actual_qty"] = round(flt(row["actual_qty"]), quantity_precisions["physical"])
		row["amount"] = flt(row["qty"]) * flt(row["rate"])
		row["actual_rate"] = (
			flt(row.pop("_actual_amount")) / flt(row["actual_qty"]) if flt(row["actual_qty"]) else 0
		)

	commercial_total = sum(flt(row["amount"]) for row in commercial_rows)
	hidden_total = sum(flt(row["amount"]) for row in hidden_rows)
	if abs(commercial_total - hidden_total) > VALUE_TOLERANCE:
		frappe.throw(
			_("The commercial process value {0} does not reconcile with the physical GRN value {1}.").format(
				flt(commercial_total, 2), flt(hidden_total, 2)
			)
		)

	grand_total = sum(flt(row["amount"]) * (1 + _get_tax_rate(row.get("tax")) / 100) for row in hidden_rows)
	return {
		"items": hidden_rows,
		"commercial_items": commercial_rows,
		"total": grand_total,
		"pre_tax_total": hidden_total,
		"tax_total": grand_total - hidden_total,
		"total_quantity": sum(flt(row["qty"]) for row in commercial_rows),
		"wo_items": billed_rows,
		"tax_rates": {row.get("tax"): _get_tax_rate(row.get("tax")) for row in hidden_rows if row.get("tax")},
		"allow_to_change_rate": 1,
		"warnings": warnings,
	}


def _build_modern_work_order_context(
	work_order,
	selected_grns,
	*,
	is_historical,
	has_gstin,
	final_rates,
	expense_heads,
	warnings,
	quantity_precisions,
):
	process = frappe.get_doc("YRP Process", work_order.process_name)
	process_item = process.get("item")
	if not process_item:
		frappe.throw(
			_("Process {0} has no Purchase Invoice billing Item configured.").format(work_order.process_name)
		)
	billing_variant = get_or_create_variant(process_item, {})
	item_group = _get_item_group(billing_variant)
	if not item_group:
		frappe.throw(
			_("Process {0} billing Item {1} has no Item Group.").format(
				work_order.process_name,
				billing_variant,
			)
		)
	billing_uom = resolve_item_uom(billing_variant).uom
	process_cost = _get_work_order_process_cost(work_order, is_historical)
	tax = process_cost.get("tax_slab") if process_cost and has_gstin else None
	ipd = (
		frappe.get_cached_doc("YRP Item Production Detail", work_order.production_detail)
		if work_order.get("production_detail")
		else None
	)
	received_json = _uses_received_json(work_order, process, ipd)
	calculated = _modern_calculated_items(work_order)
	if received_json:
		quantities = get_selected_grn_piece_quantities(work_order, selected_grns)
		for calculated_item in calculated.values():
			calculated_item["selected_qty"] = quantities.get(
				_piece_quantity_key(calculated_item["row"]), 0
			)
	else:
		for grn in selected_grns:
			for grn_item in grn.get("items") or []:
				_add_calculated_quantity(
					calculated,
					grn_item,
					round(flt(grn_item.get("quantity")), quantity_precisions["physical"]),
					grn.name,
					work_order.name,
					warnings,
				)

	stitching_attribute = ipd.get("stiching_attribute") if ipd else None
	for row in calculated.values():
		row["source_rate"] = _process_cost_rate(
			process_cost,
			row["selected_qty"],
			row["row"].item_variant,
			stitching_attribute,
		)
		row["group_key"] = commercial_group_key(
			billing_variant,
			work_order.get("lot"),
			billing_uom,
			row["source_rate"],
			tax,
		)
		row["final_rate"] = final_rates.get(row["group_key"], row["source_rate"])
		if row["final_rate"] < 0:
			frappe.throw(_("Final process rate cannot be negative."))

	return {
		"billing_variant": billing_variant,
		"billing_uom": billing_uom,
		"item_group": item_group,
		"tax": tax,
		"lot": work_order.get("lot"),
		"received_json": received_json,
		"ipd": ipd,
		"calculated": calculated,
		"expense_heads": expense_heads,
		"quantity_precisions": quantity_precisions,
	}


def _is_historical_selection(selected_grns):
	minimum_date = frappe.db.get_single_value("SD YRP MRP Settings", "pi_minimum_grn_date")
	posting_dates = [getdate(grn.posting_date) for grn in selected_grns if grn.get("posting_date")]
	return bool(minimum_date and posting_dates and min(posting_dates) < getdate(minimum_date))


def _get_work_order_process_cost(work_order, is_historical):
	if not is_historical:
		return (
			frappe.get_doc("YRP Process Cost", work_order.process_cost)
			if work_order.get("process_cost")
			else None
		)

	filters = {
		"process_name": work_order.process_name,
		"item": work_order.item,
		"is_expired": 0,
		"from_date": ["<=", work_order.wo_date],
		"docstatus": 1,
		"lot": work_order.get("lot"),
		"is_rework": 1 if work_order.get("is_rework") else 0,
	}
	if frappe.get_meta("YRP Process Cost").get_field("workflow_state"):
		filters["workflow_state"] = "Approved"
	if work_order.get("supplier"):
		filters["supplier"] = work_order.supplier

	filter_variants = [filters.copy()]
	if "supplier" in filters:
		without_supplier = filters.copy()
		without_supplier.pop("supplier")
		filter_variants.append(without_supplier)
	without_lot = filters.copy()
	without_lot.pop("lot", None)
	filter_variants.append(without_lot)
	if "supplier" in without_lot:
		without_lot_or_supplier = without_lot.copy()
		without_lot_or_supplier.pop("supplier")
		filter_variants.append(without_lot_or_supplier)

	for variant in filter_variants:
		matches = frappe.get_list(
			"YRP Process Cost",
			filters=variant,
			fields=["name"],
			order_by="modified desc",
			limit_page_length=1,
		)
		if matches:
			return frappe.get_doc("YRP Process Cost", matches[0].name)
	return None


def _uses_received_json(work_order, process, ipd):
	if not ipd:
		return False
	process_name = work_order.process_name
	if process.get("is_group"):
		process_details = process.get("process_details") or []
		process_name = process_details[0].process_name if process_details else None
	if not process_name:
		return False
	if process_name == ipd.get("cutting_process"):
		return True
	stage = _attribute_value(ipd.get("stiching_in_stage"))
	return any(
		row.process_name == process_name and _attribute_value(row.get("in_stage")) == stage
		for row in ipd.get("ipd_processes") or []
	)


def _modern_calculated_items(work_order):
	calculated = {}
	for row in work_order.get("work_order_calculated_items") or []:
		calculated[_calculated_item_key(row)] = {
			"row": row,
			"selected_qty": 0,
		}
	return calculated


def _calculated_item_key(row):
	combination = _normal_json(row.get("set_combination"))
	return row.item_variant, combination.get("major_colour")


def _piece_quantity_key(row):
	return row.item_variant, _combination_key(row.get("set_combination"))


def _add_calculated_quantity(calculated, source_row, quantity, grn, work_order, warnings):
	key = _calculated_item_key(source_row)
	if key in calculated:
		calculated[key]["selected_qty"] += quantity
		return
	warnings.append(
		{
			"work_order": work_order,
			"grns": [grn],
			"reason": _(
				"GRN {0} row {1} item {2} is not a calculated item of Work Order {3}; "
				"its quantity is not billed."
			).format(grn, source_row.get("idx") or "?", source_row.item_variant, work_order),
		}
	)


def _process_cost_rate(process_cost, quantity, item_variant, stitching_attribute=None):
	"""Return production_api's strict minimum-quantity tier rate."""
	if not process_cost:
		return 0
	rows = list(process_cost.get("process_cost_values") or [])
	if process_cost.get("depends_on_attribute") and process_cost.get("attribute") != stitching_attribute:
		attribute = process_cost.attribute
		variant_value = _attribute_value(get_variant_attributes(item_variant).get(attribute))
		if not variant_value:
			return 0
		rows = [
			row
			for row in rows
			if _attribute_value(row.get("attribute_value")) == variant_value
		]
	tiers = defaultdict(float)
	for row in rows:
		tiers[int(flt(row.get("min_order_qty")))] += flt(row.get("price"))
	if len(tiers) == 1:
		return next(iter(tiers.values()))
	for minimum_quantity in sorted(tiers, reverse=True):
		if minimum_quantity < flt(quantity):
			return tiers[minimum_quantity]
	return 0


def _build_modern_work_order_rows(work_order, selected_grns, context):
	commercial = {}
	hidden = {}
	billed_rows = []
	grn_names = ", ".join(grn.name for grn in selected_grns)
	for row_number, calculated in enumerate(context["calculated"].values(), start=1):
		selected_qty = flt(calculated["selected_qty"])
		work_order_item = calculated["row"]
		source = _("Goods Received Note(s) {0}, Work Order {1} calculated row {2}").format(
			grn_names,
			work_order.name,
			work_order_item.get("idx") or row_number,
		)
		commercial_qty = _stored_quantity(
			selected_qty,
			context["quantity_precisions"]["commercial"],
			source,
			"commercial",
		)
		billed_qty = _stored_quantity(
			selected_qty,
			context["quantity_precisions"]["billed"],
			source,
			"billed",
		)
		calculated["commercial_qty"] = commercial_qty
		group_key = calculated["group_key"]
		final_rate = calculated["final_rate"]
		row = commercial.setdefault(
			group_key,
			{
				"item": context["billing_variant"],
				"lot": context["lot"],
				"item_group": context["item_group"],
				"expense_head": context["expense_heads"].get(group_key),
				"qty": 0,
				"uom": context["billing_uom"],
				"source_rate": calculated["source_rate"],
				"rate": final_rate,
				"amount": 0,
				"tax": context["tax"],
				"group_key": group_key,
			},
		)
		if abs(flt(row["rate"]) - final_rate) > 0.000001:
			frappe.throw(_("Conflicting final rates were supplied for one process item group."))
		row["qty"] += commercial_qty

		billed_rows.append(
			{
				"work_order": work_order.name,
				"item_variant": work_order_item.item_variant,
				"quantity": billed_qty,
				"total_delivered": flt(work_order_item.get("delivered_quantity")),
				"total_received": flt(work_order_item.get("received_qty")),
				"billed": flt(work_order_item.get("billed_qty")),
				"set_combination": _json_value(work_order_item.get("set_combination")),
				"essdee_group_key": group_key,
			}
		)

	if context["received_json"]:
		_build_received_json_physical_rows(hidden, work_order, selected_grns, context)
	else:
		_build_direct_physical_rows(hidden, work_order, selected_grns, context)
	return commercial, hidden, billed_rows


def _build_direct_physical_rows(hidden, work_order, selected_grns, context):
	for grn in selected_grns:
		for grn_item in grn.get("items") or []:
			quantity = round(
				flt(grn_item.get("quantity")), context["quantity_precisions"]["physical"]
			)
			if quantity <= 0:
				continue
			calculated = context["calculated"].get(_calculated_item_key(grn_item))
			_append_modern_physical_row(
				hidden,
				grn.name,
				grn_item,
				work_order,
				context["tax"] if calculated else None,
				calculated["group_key"] if calculated else None,
				_physical_source_rate(work_order, grn_item),
				calculated["final_rate"] if calculated else 0,
				1 if calculated else 0,
				quantity,
			)


def _build_received_json_physical_rows(hidden, work_order, selected_grns, context):
	physical_rows = []
	for grn in selected_grns:
		for grn_item in grn.get("items") or []:
			quantity = round(
				flt(grn_item.get("quantity")), context["quantity_precisions"]["physical"]
			)
			if quantity > 0:
				physical_rows.append((grn.name, grn_item, quantity))
	physical_quantity = sum(quantity for _grn, _row, quantity in physical_rows)
	if not physical_quantity:
		return
	calculated_rows = list(context["calculated"].values())
	group_values = defaultdict(float)
	group_rows = {}
	for calculated in calculated_rows:
		group_key = calculated["group_key"]
		group_values[group_key] += flt(calculated["commercial_qty"]) * flt(
			calculated["final_rate"]
		)
		group_rows[group_key] = calculated
	valued_groups = {
		group_key for group_key, value in group_values.items() if abs(flt(value)) > 0.0000001
	}
	mapped = defaultdict(list)
	for source_grn, grn_item, quantity in physical_rows:
		calculated = _panel_calculated_item(grn_item, context)
		if calculated and calculated["group_key"] in valued_groups:
			mapped[calculated["group_key"]].append((source_grn, grn_item, quantity))
	if sum(len(rows) for rows in mapped.values()) != len(physical_rows) or any(
		group_key not in mapped for group_key in valued_groups
	):
		_build_even_received_json_physical_rows(
			hidden,
			work_order,
			physical_rows,
			physical_quantity,
			calculated_rows,
			context,
		)
		return

	for group_key, rows in mapped.items():
		calculated = group_rows[group_key]
		group_quantity = sum(quantity for _grn, _row, quantity in rows)
		physical_rate = group_values[group_key] / group_quantity
		final_rate = flt(calculated["final_rate"])
		rate_weight = physical_rate / final_rate if abs(final_rate) > 0.0000001 else 0
		for source_grn, grn_item, quantity in rows:
			_append_modern_physical_row(
				hidden,
				source_grn,
				grn_item,
				work_order,
				context["tax"],
				group_key,
				_physical_source_rate(work_order, grn_item),
				physical_rate,
				rate_weight,
				quantity,
			)


def _build_even_received_json_physical_rows(
	hidden,
	work_order,
	physical_rows,
	physical_quantity,
	calculated_rows,
	context,
):
	commercial_value = sum(
		flt(row["commercial_qty"]) * flt(row["final_rate"]) for row in calculated_rows
	)
	physical_rate = commercial_value / physical_quantity
	anchor = next(
		(row for row in calculated_rows if abs(flt(row["final_rate"])) > 0.0000001),
		calculated_rows[0] if calculated_rows else None,
	)
	anchor_rate = flt(anchor["final_rate"]) if anchor else 0
	rate_weight = physical_rate / anchor_rate if abs(anchor_rate) > 0.0000001 else 0
	for source_grn, grn_item, quantity in physical_rows:
		_append_modern_physical_row(
			hidden,
			source_grn,
			grn_item,
			work_order,
			context["tax"] if anchor else None,
			anchor["group_key"] if anchor else None,
			_physical_source_rate(work_order, grn_item),
			physical_rate,
			rate_weight,
			quantity,
		)


def _panel_calculated_item(grn_item, context):
	ipd = context.get("ipd")
	if not ipd or not ipd.get("primary_item_attribute"):
		return None
	attributes = get_variant_attributes(grn_item.item_variant)
	primary_value = _attribute_value(attributes.get(ipd.primary_item_attribute))
	combination = _normal_json(grn_item.get("set_combination"))
	panel_parts = {
		_attribute_value(row.get("stiching_attribute_value")): _attribute_value(
			row.get("set_item_attribute_value")
		)
		for row in ipd.get("stiching_item_details") or []
	}
	panel = _attribute_value(attributes.get(ipd.get("stiching_attribute")))
	matches = []
	for calculated in context["calculated"].values():
		row = calculated["row"]
		if _normal_json(row.get("set_combination")) != combination:
			continue
		calculated_attributes = get_variant_attributes(row.item_variant)
		if _attribute_value(calculated_attributes.get(ipd.primary_item_attribute)) != primary_value:
			continue
		if ipd.get("is_set_item") and _attribute_value(
			calculated_attributes.get(ipd.get("set_item_attribute"))
		) != panel_parts.get(panel):
			continue
		matches.append(calculated)
	return matches[0] if len(matches) == 1 else None


def _physical_source_rate(work_order, grn_item):
	quantity = flt(grn_item.get("quantity"))
	if quantity <= 0:
		return 0
	combination = _normal_json(grn_item.get("set_combination"))
	receivable = next(
		(
			row
			for row in work_order.get("receivables") or []
			if row.item_variant == grn_item.item_variant
			and _normal_json(row.get("set_combination")) == combination
		),
		None,
	)
	stock_quantity = flt(grn_item.get("stock_qty")) or quantity
	if receivable:
		return flt(receivable.get("cost")) * stock_quantity / quantity
	return flt(grn_item.get("amount")) / quantity


def _append_modern_physical_row(
	hidden,
	source_grn,
	grn_item,
	work_order,
	tax,
	group_key,
	source_rate,
	rate,
	rate_weight,
	quantity,
):
	set_combination = _normal_json(grn_item.get("set_combination"))
	key = (
		source_grn,
		grn_item.get("name") or grn_item.get("idx") or len(hidden),
		grn_item.item_variant,
		grn_item.uom,
		round(flt(source_rate), RATE_PRECISION),
		round(flt(rate_weight), 9),
		tax or "",
		_combination_key(set_combination),
		group_key or "",
	)
	row = hidden.setdefault(
		key,
		{
			"item": grn_item.item_variant,
			"lot": work_order.get("lot"),
			"item_group": _get_item_group(grn_item.item_variant),
			"qty": 0,
			"uom": grn_item.uom,
			"rate": rate,
			"source_rate": source_rate,
			"amount": 0,
			"tax": tax,
			"actual_rate": 0,
			"actual_qty": 0,
			"set_combination": _json_value(set_combination),
			"essdee_group_key": group_key,
			"essdee_rate_weight": rate_weight,
			"_actual_amount": 0,
		},
	)
	row["qty"] += quantity
	row["actual_qty"] += quantity
	row["_actual_amount"] += quantity * flt(grn_item.get("rate"))


def _merge_commercial_rows(target, rows):
	for group_key, row in rows.items():
		if group_key not in target:
			target[group_key] = row
			continue
		if abs(flt(target[group_key]["rate"]) - flt(row["rate"])) > 0.000001:
			frappe.throw(_("Conflicting final rates were supplied for one process item group."))
		target[group_key]["qty"] += flt(row["qty"])


def _merge_hidden_rows(target, rows):
	for key, row in rows.items():
		if key not in target:
			target[key] = row
			continue
		target[key]["qty"] += flt(row["qty"])
		target[key]["actual_qty"] += flt(row["actual_qty"])
		target[key]["_actual_amount"] += flt(row["_actual_amount"])


def _json_value(value):
	return json.dumps(_normal_json(value), sort_keys=True)


def create_work_order_purchase_invoice_adjustment(invoice):
	"""Run YRP's allocator in the physical-row source order."""
	from yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment import (
		create_purchase_invoice_adjustment,
	)

	grn_names = list(dict.fromkeys(row.grn for row in invoice.get("grn") or [] if row.grn))
	if not grn_names:
		return create_purchase_invoice_adjustment(invoice)

	work_order_by_grn = {
		name: frappe.get_doc("YRP Goods Received Note", name).get("against_id") for name in grn_names
	}
	work_order_order = list(dict.fromkeys(work_order_by_grn.values()))
	ordered_names = [
		name
		for work_order in work_order_order
		for name in grn_names
		if work_order_by_grn[name] == work_order
	]
	ordered_names.extend(name for name in grn_names if name not in ordered_names)
	allocation_invoice = frappe._dict(
		doctype=invoice.doctype,
		name=invoice.name,
		posting_date=invoice.posting_date,
		grn=[frappe._dict(grn=name) for name in ordered_names],
		items=invoice.get("items") or [],
	)
	return create_purchase_invoice_adjustment(allocation_invoice)
