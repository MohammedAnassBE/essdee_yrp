"""Essdee's commercial Work Order Purchase Invoice projection.

Users bill finished garment quantities at one process rate.  Stock valuation,
however, must retain the exact physical GRN panel rows.  This module owns the
lossless conversion between those two views and the historical
``production_api`` backfill.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt
from yrp.stock.uom import resolve_item_uom
from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant
from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import (
	_check_invoice_fetch_permission,
	_get_item_group,
	_get_tax_rate,
	_normal_json,
	_validate_selected_grn,
	fetch_grn_details as base_fetch_grn_details,
)
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import get_variant_attributes

from essdee_yrp.overrides.work_order import _combination_key, _matches_garment_demand
from essdee_yrp.erp_purchase_invoice import fetch_expense_accounts


RATE_PRECISION = 6
QUANTITY_TOLERANCE = 0.01
VALUE_TOLERANCE = 0.01
MODERN_RATE_SOURCE = "yrp_grn_v1"
LEGACY_RATE_SOURCE = "production_api"
MAX_SELECTED_GRNS = 200


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


def build_verification_details(rows):
	"""Build the colour/size verification matrix used by production_api.

	The base YRP Purchase Invoice deliberately exposes a generic flat list.  The
	Essdee workflow has richer garment metadata, so its verification view keeps
	the established production_api layout while remaining self-contained in the
	customization app.
	"""
	rows = [row for row in (rows or []) if row.get("work_order")]
	if not rows:
		return []

	attribute_map = _get_variant_attribute_map(
		[row.get("item_variant") for row in rows if row.get("item_variant")]
	)
	grouped = {}
	for row in rows:
		grouped.setdefault(row.work_order, []).append(row)

	details = []
	for work_order, work_order_rows in grouped.items():
		context = _get_verification_work_order_context(work_order)
		data = {
			"work_order": work_order,
			"lot": context.get("lot"),
			"item_name": context.get("item_name"),
			"sizes": [],
			"colours": {},
			"total_qty": {},
			"is_set_item": context.get("is_set_item") or 0,
			"primary_attribute": context.get("primary_attribute"),
			"set_attr": context.get("set_attr"),
			"packing_attr": context.get("packing_attr"),
			"bills": _get_existing_verification_bills(work_order),
		}
		for row in work_order_rows:
			attributes = attribute_map.get(row.get("item_variant"), {})
			combination = _normal_json(row.get("set_combination"))
			primary = context.get("primary_attribute")
			packing_attr = context.get("packing_attr")
			set_attr = context.get("set_attr")
			size = attributes.get(primary) or _("Unspecified")
			major_colour = (
				combination.get("major_colour")
				or attributes.get(packing_attr)
				or _("Unspecified")
			)
			colour = major_colour
			part = None
			if data["is_set_item"]:
				variant_colour = attributes.get(packing_attr) or major_colour
				part = attributes.get(set_attr) or combination.get("major_part") or ""
				colour = f"{variant_colour}({major_colour}) @{part}"

			if size not in data["sizes"]:
				data["sizes"].append(size)
			data["total_qty"].setdefault(
				colour,
				{
					"total_delivered": 0,
					"total_received": 0,
					"total_billed": 0,
					"total_quantity": 0,
				},
			)
			data["colours"].setdefault(colour, {"part": part, "data": {}})
			data["colours"][colour]["data"].setdefault(
				size,
				{
					"total_delivered": 0,
					"total_received": 0,
					"billed": 0,
					"quantity": 0,
				},
			)
			cell = data["colours"][colour]["data"][size]
			cell["total_delivered"] += flt(row.get("total_delivered"))
			cell["total_received"] += flt(row.get("total_received"))
			cell["billed"] += flt(row.get("billed"))
			cell["quantity"] += flt(row.get("quantity"))
			totals = data["total_qty"][colour]
			totals["total_delivered"] += flt(row.get("total_delivered"))
			totals["total_received"] += flt(row.get("total_received"))
			totals["total_billed"] += flt(row.get("billed"))
			totals["total_quantity"] += flt(row.get("quantity"))

		data["grand_total"] = _calculate_verification_grand_total(data)
		details.append(data)
	return details


def _get_variant_attribute_map(item_variants):
	item_variants = list(dict.fromkeys(item_variants or []))
	if not item_variants:
		return {}
	result = {item_variant: {} for item_variant in item_variants}
	for row in frappe.get_all(
		'YRP Item Variant Attribute',
		filters={
			"parent": ["in", item_variants],
			"parenttype": 'YRP Item Variant',
		},
		fields=["parent", "attribute", "attribute_value"],
		order_by="parent, idx",
		limit_page_length=0,
	):
		result.setdefault(row.parent, {})[row.attribute] = row.attribute_value
	return result


def _get_verification_work_order_context(work_order):
	work_order_values = frappe.db.get_value(
		'YRP Work Order',
		work_order,
		["lot", "production_detail"],
		as_dict=True,
	) or frappe._dict()
	lot_values = frappe.db.get_value(
		'SD YRP Lot',
		work_order_values.get("lot"),
		["production_detail", "item"],
		as_dict=True,
	) or frappe._dict()
	production_detail = (
		lot_values.get("production_detail") or work_order_values.get("production_detail")
	)
	ipd_values = frappe.db.get_value(
		'YRP Item Production Detail',
		production_detail,
		[
			"is_set_item",
			"primary_item_attribute",
			"packing_attribute",
			"set_item_attribute",
		],
		as_dict=True,
	) or frappe._dict()
	return frappe._dict(
		lot=work_order_values.get("lot"),
		item_name=lot_values.get("item"),
		is_set_item=ipd_values.get("is_set_item"),
		primary_attribute=ipd_values.get("primary_item_attribute"),
		packing_attr=ipd_values.get("packing_attribute"),
		set_attr=ipd_values.get("set_item_attribute"),
	)


def _get_existing_verification_bills(work_order):
	return frappe.db.sql(
		"""
		SELECT parent AS pi_name
		FROM `tabYRP PI Work Order Billed Detail`
		WHERE work_order = %(work_order)s AND docstatus = 1
		GROUP BY parent, work_order
		ORDER BY MIN(creation), parent
		""",
		{"work_order": work_order},
		as_dict=True,
	)


def _calculate_verification_grand_total(data):
	fields = (
		"total_delivered",
		"total_received",
		"difference",
		"total_billed",
		"pending_for_bill",
		"grn_quantity",
	)
	size_totals = {
		size: {field: 0 for field in fields}
		for size in data["sizes"]
	}
	for colour in data["colours"].values():
		for size in data["sizes"]:
			values = colour["data"].get(size) or {}
			delivered = flt(values.get("total_delivered"))
			received = flt(values.get("total_received"))
			billed = flt(values.get("billed"))
			quantity = flt(values.get("quantity"))
			size_totals[size]["total_delivered"] += delivered
			size_totals[size]["total_received"] += received
			size_totals[size]["difference"] += delivered - received
			size_totals[size]["total_billed"] += billed
			size_totals[size]["pending_for_bill"] += received - billed
			size_totals[size]["grn_quantity"] += quantity
	return {
		"sizes": size_totals,
		"total": {
			field: sum(size_totals[size][field] for size in data["sizes"])
			for field in fields
		},
	}


@frappe.whitelist()
def fetch_grn_details(grns, against, supplier, purchase_invoice=None):
	"""Override base YRP only for Essdee's Work Order billing view."""
	if against != 'YRP Work Order':
		payload = base_fetch_grn_details(grns, against, supplier, purchase_invoice)
		payload["items"] = fetch_expense_accounts(payload.get("items"))
		return payload

	_check_invoice_fetch_permission(purchase_invoice)
	frappe.has_permission('YRP Goods Received Note', "read", throw=True)
	if purchase_invoice and frappe.db.exists('YRP Purchase Invoice', purchase_invoice):
		# Link values can be masked in Desk for restricted users. The permission-
		# checked saved document is authoritative; never compare a masked client
		# placeholder such as XXXXXXXX with the GRN's real supplier.
		supplier = frappe.db.get_value('YRP Purchase Invoice', purchase_invoice, "supplier")
	grns = frappe.parse_json(grns) if isinstance(grns, str) else grns
	if not isinstance(grns, list):
		frappe.throw(_("Selected GRNs must be a list."))
	grns = list(dict.fromkeys(grns or []))
	if not grns:
		frappe.throw(_("Please select at least one GRN."))
	if len(grns) > MAX_SELECTED_GRNS:
		frappe.throw(
			_("A maximum of {0} GRNs can be fetched at once.").format(MAX_SELECTED_GRNS)
		)
	if supplier and not str(supplier).strip("Xx*"):
		supplier = None
	validated_grns = [
		_validate_selected_grn(grn, supplier, 'YRP Work Order', purchase_invoice)
		for grn in grns
	]
	selected_suppliers = {grn.supplier for grn in validated_grns}
	if len(selected_suppliers) != 1:
		frappe.throw(_("All selected GRNs must belong to one Supplier."))
	supplier = supplier or next(iter(selected_suppliers))

	payload = build_work_order_invoice_payload(
		grns,
		supplier=supplier,
		purchase_invoice=purchase_invoice,
	)
	payload["commercial_items"] = fetch_expense_accounts(payload["commercial_items"])
	payload["additional_field_values"] = {
		"essdee_items": payload.pop("commercial_items"),
		"essdee_rate_table_source": MODERN_RATE_SOURCE,
		"total": payload["pre_tax_total"],
		"total_tax": payload["tax_total"],
		"grand_total": payload["total"],
	}
	payload.pop("pre_tax_total")
	payload.pop("tax_total")
	return payload


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
		_validate_selected_grn(grn_name, supplier, 'YRP Work Order', purchase_invoice)
		grn_docs.append(frappe.get_doc('YRP Goods Received Note', grn_name))
	if not grn_docs:
		frappe.throw(_("Please select at least one GRN."))

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

	for work_order_name, selected_grns in by_work_order.items():
		work_order = frappe.get_doc('YRP Work Order', work_order_name)
		context = _build_work_order_context(work_order, selected_grns)

		for demand in context["demands"]:
			selected_qty = flt(demand["selected_qty"])
			if selected_qty <= QUANTITY_TOLERANCE:
				continue
			group_key = demand["group_key"]
			final_rate = final_rates.get(group_key, demand["source_rate"])
			if final_rate < 0:
				frappe.throw(_("Final process rate cannot be negative."))
			row = commercial.setdefault(
				group_key,
				{
					"item": context["billing_variant"],
					"lot": context["lot"],
					"item_group": context["item_group"],
					"expense_head": expense_heads.get(group_key),
					"qty": 0,
					"uom": context["billing_uom"],
					"source_rate": demand["source_rate"],
					"rate": final_rate,
					"amount": 0,
					"tax": context["tax"],
					"group_key": group_key,
				},
			)
			if abs(flt(row["rate"]) - final_rate) > 0.000001:
				frappe.throw(_("Conflicting final rates were supplied for one process item group."))
			row["qty"] += selected_qty

			calculated = demand["row"]
			billed_rows.append(
				{
					"work_order": work_order.name,
					"item_variant": calculated.item_variant,
					"quantity": selected_qty,
					"total_delivered": flt(calculated.delivered_quantity),
					"total_received": flt(calculated.received_qty),
					"billed": flt(calculated.billed_qty),
					"set_combination": _json_value(calculated.get("set_combination")),
					"essdee_group_key": group_key,
				}
			)

		_validate_selected_physical_quantities(context, selected_grns)
		for grn in selected_grns:
			for grn_item in grn.get("items") or []:
				receivable = _receivable_for_grn_item(context, grn, grn_item)
				demand = context["demand_by_receivable"][receivable.name]
				group_key = demand["group_key"]
				final_rate = final_rates.get(group_key, demand["source_rate"])
				quantity = flt(grn_item.quantity)
				if quantity <= 0:
					continue
				conversion_factor = (
					flt(grn_item.stock_qty) / quantity
					if flt(grn_item.stock_qty) and quantity
					else 1
				)
				physical_source_rate = flt(receivable.cost) * conversion_factor
				rate_weight = demand["weights"][receivable.name] * conversion_factor
				final_physical_rate = final_rate * rate_weight
				set_combination = _normal_json(grn_item.get("set_combination"))
				key = (
					grn_item.item_variant,
					grn_item.uom,
					round(physical_source_rate, RATE_PRECISION),
					round(rate_weight, 9),
					context["tax"] or "",
					_combination_key(set_combination),
					group_key,
				)
				row = hidden.setdefault(
					key,
					{
						"item": grn_item.item_variant,
						"lot": context["lot"],
						"item_group": _get_item_group(grn_item.item_variant),
						"qty": 0,
						"uom": grn_item.uom,
						"rate": final_physical_rate,
						"source_rate": physical_source_rate,
						"amount": 0,
						"tax": context["tax"],
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
				row["_actual_amount"] += quantity * flt(grn_item.rate)

	commercial_rows = list(commercial.values())
	for row in commercial_rows:
		row["amount"] = flt(row["qty"]) * flt(row["rate"])

	hidden_rows = list(hidden.values())
	for row in hidden_rows:
		row["amount"] = flt(row["qty"]) * flt(row["rate"])
		row["actual_rate"] = (
			flt(row.pop("_actual_amount")) / flt(row["actual_qty"])
			if flt(row["actual_qty"])
			else 0
		)

	commercial_total = sum(flt(row["amount"]) for row in commercial_rows)
	hidden_total = sum(flt(row["amount"]) for row in hidden_rows)
	if abs(commercial_total - hidden_total) > VALUE_TOLERANCE:
		frappe.throw(
			_(
				"The commercial process value {0} does not reconcile with the physical GRN value {1}."
			).format(flt(commercial_total, 2), flt(hidden_total, 2))
		)

	grand_total = sum(
		flt(row["amount"]) * (1 + _get_tax_rate(row.get("tax")) / 100)
		for row in hidden_rows
	)
	return {
		"items": hidden_rows,
		"commercial_items": commercial_rows,
		"total": grand_total,
		"pre_tax_total": hidden_total,
		"tax_total": grand_total - hidden_total,
		"total_quantity": sum(flt(row["qty"]) for row in commercial_rows),
		"wo_items": billed_rows,
		"tax_rates": {
			row.get("tax"): _get_tax_rate(row.get("tax"))
			for row in hidden_rows
			if row.get("tax")
		},
		"allow_to_change_rate": 1,
	}


def _build_work_order_context(work_order, selected_grns):
	process_item = frappe.db.get_value('YRP Process', work_order.process_name, "item")
	if not process_item:
		frappe.throw(
			_("Process {0} has no Purchase Invoice billing Item configured.").format(
				work_order.process_name
			)
		)
	billing_variant = get_or_create_variant(process_item, {})
	billing_uom = resolve_item_uom(billing_variant).uom
	item_group = frappe.db.get_value('YRP Item', process_item, "item_group")
	process_cost = (
		frappe.get_doc('YRP Process Cost', work_order.process_cost)
		if work_order.process_cost
		else None
	)
	if not process_cost:
		frappe.throw(_("Work Order {0} has no Process Cost.").format(work_order.name))
	tax = process_cost.tax_slab
	lots = {grn.get("lot") or work_order.get("lot") for grn in selected_grns}
	if len(lots) != 1:
		frappe.throw(_("Selected GRNs for Work Order {0} do not have one Lot.").format(work_order.name))
	lot = next(iter(lots))

	demands = []
	for calculated in work_order.get("work_order_calculated_items") or []:
		planned_qty = flt(calculated.quantity)
		if planned_qty <= 0:
			continue
		demands.append(
			{
				"row": calculated,
				"planned_qty": planned_qty,
				"attributes": get_variant_attributes(calculated.item_variant),
				"combination": _combination_key(calculated.get("set_combination")),
				"receivables": [],
				"selected_qty": 0,
			}
		)
	if not demands:
		frappe.throw(_("Work Order {0} has no calculated garment items.").format(work_order.name))

	ipd = (
		frappe.get_cached_doc('YRP Item Production Detail', work_order.production_detail)
		if work_order.production_detail
		else None
	)
	demand_by_receivable = {}
	receivables_by_name = {}
	for receivable in work_order.get("receivables") or []:
		demand = _demand_for_receivable(demands, receivable, ipd)
		demand["receivables"].append(receivable)
		demand_by_receivable[receivable.name] = demand
		receivables_by_name[receivable.name] = receivable
	if any(not demand["receivables"] for demand in demands):
		missing = next(demand for demand in demands if not demand["receivables"])
		frappe.throw(
			_("Calculated item {0} in Work Order {1} has no receivable rows.").format(
				missing["row"].item_variant, work_order.name
			)
		)

	selected_names = {grn.name for grn in selected_grns}
	for tracking in work_order.get("work_order_track_pieces") or []:
		if tracking.against != 'YRP Goods Received Note' or tracking.against_id not in selected_names:
			continue
		demand = _demand_for_tracking(demands, tracking, work_order.name)
		demand["selected_qty"] += flt(tracking.received_qty)
	if not any(flt(demand["selected_qty"]) > 0 for demand in demands):
		frappe.throw(
			_("Selected GRNs have no finished-piece tracking rows in Work Order {0}.").format(
				work_order.name
			)
		)

	for demand in demands:
		source_value = sum(
			flt(row.cost) * flt(row.qty) for row in demand["receivables"]
		)
		demand["source_rate"] = source_value / demand["planned_qty"]
		demand["weights"] = _physical_rate_weights(demand, ipd)
		demand["group_key"] = commercial_group_key(
			billing_variant,
			lot,
			billing_uom,
			demand["source_rate"],
			tax,
		)

	return {
		"work_order": work_order,
		"demands": demands,
		"demand_by_receivable": demand_by_receivable,
		"receivables_by_name": receivables_by_name,
		"billing_variant": billing_variant,
		"billing_uom": billing_uom,
		"item_group": item_group,
		"tax": tax,
		"lot": lot,
		"ipd": ipd,
	}


def _demand_for_receivable(demands, receivable, ipd):
	combination = _combination_key(receivable.get("set_combination"))
	exact = [
		demand
		for demand in demands
		if demand["row"].item_variant == receivable.item_variant
		and demand["combination"] == combination
	]
	if len(exact) == 1:
		return exact[0]

	attributes = get_variant_attributes(receivable.item_variant)
	garment = (
		[
			demand
			for demand in demands
			if _matches_garment_demand(demand, receivable, attributes, ipd)
		]
		if ipd
		else []
	)
	if len(garment) != 1:
		frappe.throw(
			_("Receivable {0} cannot be mapped to one calculated garment item.").format(
				receivable.item_variant
			)
		)
	return garment[0]


def _demand_for_tracking(demands, tracking, work_order):
	combination = _combination_key(tracking.get("set_combination"))
	matches = [
		demand
		for demand in demands
		if demand["row"].item_variant == tracking.item_variant
		and demand["combination"] == combination
	]
	if not matches and combination == "{}":
		matches = [
			demand for demand in demands if demand["row"].item_variant == tracking.item_variant
		]
	if len(matches) != 1:
		frappe.throw(
			_("Tracking item {0} in Work Order {1} is ambiguous.").format(
				tracking.item_variant, work_order
			)
		)
	return matches[0]


def _physical_rate_weights(demand, ipd):
	"""Return per-physical-unit shares whose planned extended sum is one piece."""
	source_rate = flt(demand["source_rate"])
	if abs(source_rate) > 0.0000001:
		return {
			row.name: flt(row.cost) / source_rate for row in demand["receivables"]
		}

	panel_attribute = ipd.get("stiching_attribute") if ipd else None
	panel_groups = defaultdict(list)
	if panel_attribute:
		for row in demand["receivables"]:
			panel = get_variant_attributes(row.item_variant).get(panel_attribute)
			if panel:
				panel_groups[panel].append(row)
	if not panel_groups:
		panel_groups["all"] = list(demand["receivables"])

	weights = {}
	for rows in panel_groups.values():
		group_qty = sum(flt(row.qty) for row in rows)
		if group_qty <= 0:
			frappe.throw(_("Work Order receivable quantity must be positive."))
		weight = demand["planned_qty"] / (len(panel_groups) * group_qty)
		for row in rows:
			weights[row.name] = weight
	return weights


def _receivable_for_grn_item(context, grn, grn_item):
	if (
		grn_item.get("ref_doctype") == 'YRP Work Order Receivables'
		and grn_item.get("ref_docname") in context["receivables_by_name"]
	):
		return context["receivables_by_name"][grn_item.ref_docname]

	combination = _combination_key(grn_item.get("set_combination"))
	matches = [
		row
		for row in context["receivables_by_name"].values()
		if row.item_variant == grn_item.item_variant
		and _combination_key(row.get("set_combination")) == combination
	]
	if len(matches) != 1:
		frappe.throw(
			_("GRN {0} row {1} cannot be mapped to one Work Order receivable.").format(
				grn.name, grn_item.idx
			)
		)
	return matches[0]


def _validate_selected_physical_quantities(context, selected_grns):
	actual = defaultdict(float)
	for grn in selected_grns:
		for grn_item in grn.get("items") or []:
			receivable = _receivable_for_grn_item(context, grn, grn_item)
			actual[receivable.name] += flt(grn_item.quantity)

	for receivable_name, receivable in context["receivables_by_name"].items():
		demand = context["demand_by_receivable"][receivable_name]
		expected = (
			flt(demand["selected_qty"])
			* flt(receivable.qty)
			/ flt(demand["planned_qty"])
		)
		if abs(expected - actual[receivable_name]) > QUANTITY_TOLERANCE:
			frappe.throw(
				_(
					"Selected GRNs are incomplete for {0}: physical quantity is {1}, expected {2} from the finished-piece receipt."
				).format(
					receivable.item_variant,
					flt(actual[receivable_name], 3),
					flt(expected, 3),
				)
			)


def _json_value(value):
	value = _normal_json(value)
	return frappe.as_json(value) if value else None


def backfill_legacy_commercial_items():
	"""Copy the migrated F15 visible service rows into Essdee's new table.

	Only invoices whose current base rows are Process billing Item Variants are
	eligible.  That structural guard excludes F16-native physical-panel drafts.
	"""
	if not frappe.db.exists("DocType", 'SD YRP Essdee Purchase Invoice Item'):
		return {"migrated_invoices": 0, "migrated_rows": 0}

	parents = frappe.db.sql(
		"""
		SELECT pi.name
		FROM `tabYRP Purchase Invoice` pi
		WHERE pi.against = 'YRP Work Order'
		  AND NOT EXISTS (
			SELECT 1
			FROM `tabSD YRP Essdee Purchase Invoice Item` commercial
			WHERE commercial.parent = pi.name
			  AND commercial.parenttype = 'YRP Purchase Invoice'
		  )
		ORDER BY pi.creation, pi.name
		""",
		pluck=True,
	)
	migrated_invoices = 0
	migrated_rows = 0
	for name in parents:
		doc = frappe.get_doc('YRP Purchase Invoice', name)
		allowed_variants = _legacy_billing_variants(doc)
		items = list(doc.get("items") or [])
		if not items or not allowed_variants or any(row.item not in allowed_variants for row in items):
			continue

		for idx, row in enumerate(items, 1):
			source_value = row.get("actual_rate")
			if source_value is None or source_value == "":
				source_value = row.get("source_rate")
			if source_value is None or source_value == "":
				source_value = row.rate
			lot = row.get("lot") or _legacy_row_lot(doc, row)
			child = frappe.get_doc(
				{
					"doctype": 'SD YRP Essdee Purchase Invoice Item',
					"parent": doc.name,
					"parenttype": doc.doctype,
					"parentfield": "essdee_items",
					"idx": idx,
					"docstatus": doc.docstatus,
					"item": row.item,
					"lot": lot,
					"item_group": row.item_group,
					"expense_head": row.get("expense_head"),
					"qty": row.qty,
					"uom": row.uom,
					"source_rate": source_value,
					"rate": row.rate,
					"amount": flt(row.qty) * flt(row.rate),
					"tax": row.get("tax"),
					"group_key": commercial_group_key(
						row.item, lot, row.uom, source_value, row.get("tax")
					),
				}
			)
			child.db_insert()
			migrated_rows += 1
		frappe.db.set_value(
			'YRP Purchase Invoice',
			doc.name,
			"essdee_rate_table_source",
			LEGACY_RATE_SOURCE,
			update_modified=False,
		)
		migrated_invoices += 1

	return {
		"migrated_invoices": migrated_invoices,
		"migrated_rows": migrated_rows,
	}


def backfill_unprojected_work_order_drafts():
	"""Rebuild pre-feature Work Order drafts from their selected GRNs.

	The physical table is never operator-facing in Essdee. Drafts created before
	the commercial projection existed therefore need the same authoritative GRN
	rebuild as a fresh Fetch GRN action.
	"""
	if not frappe.db.exists("DocType", 'SD YRP Essdee Purchase Invoice Item'):
		return {"migrated_invoices": 0, "migrated_rows": 0, "skipped": []}

	candidates = frappe.db.sql(
		"""
		SELECT pi.name
		FROM `tabYRP Purchase Invoice` pi
		WHERE pi.against = 'YRP Work Order'
		  AND pi.docstatus = 0
		  AND COALESCE(pi.essdee_rate_table_source, '') = ''
		  AND EXISTS (
			SELECT 1 FROM `tabYRP Purchase Invoice GRN` grn
			WHERE grn.parent = pi.name AND COALESCE(grn.grn, '') != ''
		  )
		  AND NOT EXISTS (
			SELECT 1 FROM `tabSD YRP Essdee Purchase Invoice Item` commercial
			WHERE commercial.parent = pi.name
			  AND commercial.parenttype = 'YRP Purchase Invoice'
		  )
		ORDER BY pi.creation, pi.name
		""",
		pluck=True,
	)
	migrated_invoices = 0
	migrated_rows = 0
	skipped = []
	for name in candidates:
		try:
			doc = frappe.get_doc('YRP Purchase Invoice', name)
			grns = [row.grn for row in doc.get("grn") or [] if row.grn]
			payload = build_work_order_invoice_payload(
				grns,
				supplier=doc.supplier,
				purchase_invoice=doc.name,
			)
			doc.set("items", payload["items"])
			doc.set("essdee_items", payload["commercial_items"])
			doc.set("pi_work_order_billed_details", payload["wo_items"])
			doc.essdee_rate_table_source = MODERN_RATE_SOURCE
			doc.allow_to_change_rate = payload["allow_to_change_rate"]
			doc.total_quantity = payload["total_quantity"]
			doc.save(ignore_permissions=True)
			migrated_invoices += 1
			migrated_rows += len(payload["commercial_items"])
		except Exception:
			skipped.append(name)
			frappe.log_error(
				title=f"Purchase Invoice draft projection backfill failed: {name}",
				message=frappe.get_traceback(),
			)
	return {
		"migrated_invoices": migrated_invoices,
		"migrated_rows": migrated_rows,
		"skipped": skipped,
	}


def _legacy_billing_variants(doc):
	work_orders = {
		row.work_order
		for row in doc.get("pi_work_order_billed_details") or []
		if row.work_order
	}
	if not work_orders:
		return set()
	processes = frappe.get_all(
		'YRP Work Order',
		filters={"name": ["in", list(work_orders)]},
		pluck="process_name",
		limit_page_length=0,
	)
	items = frappe.get_all(
		'YRP Process',
		filters={"name": ["in", list(set(processes))], "item": ["is", "set"]},
		pluck="item",
		limit_page_length=0,
	) if processes else []
	return set(
		frappe.get_all(
			'YRP Item Variant',
			filters={"item": ["in", list(set(items))]},
			pluck="name",
			limit_page_length=0,
		)
	) if items else set()


def _legacy_row_lot(doc, row):
	if row.get("set_combination"):
		# Lot is not encoded in the set; this branch only documents that no
		# inference from Colour/Size is allowed.
		pass
	work_orders = [
		value
		for value in dict.fromkeys(
			detail.work_order
			for detail in doc.get("pi_work_order_billed_details") or []
			if detail.work_order
		)
	]
	lots = set(
		frappe.get_all(
			'YRP Work Order',
			filters={"name": ["in", work_orders]},
			pluck="lot",
			limit_page_length=0,
		)
	) if work_orders else set()
	return next(iter(lots)) if len(lots) == 1 else None
