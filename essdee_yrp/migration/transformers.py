"""Reviewed pure transformations for Production API historical data.

These functions do not import Frappe and can be exercised before either live
site is opened.  Site-derived invariants are checked again by the live runner.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from essdee_yrp.migration.engine import (
	SYSTEM_FIELDS,
	MigrationError,
	MigrationPlan,
	MigrationSpec,
)


def supplier_to_warehouse(
	value: Any,
	document: Mapping[str, Any],
	spec: MigrationSpec,
	fieldname: str,
) -> Any:
	"""F16 Essdee warehouses deliberately retain their Supplier name.

	The target migration runner creates/updates one Warehouse for every migrated
	Supplier using this same name, matching the existing SD-YRP consumer.
	"""

	return value


def purchase_order_status(
	value: Any,
	document: Mapping[str, Any],
	spec: MigrationSpec,
	fieldname: str,
) -> Any:
	return {
		"Delivered": "Received",
		"Partially Delivered": "Partially Received",
	}.get(value, value)


def purchase_order_open_status(
	value: Any,
	document: Mapping[str, Any],
	spec: MigrationSpec,
	fieldname: str,
) -> Any:
	return "Close" if value == "Closed" else value


def attribute_value_link_to_data(
	value: Any,
	document: Mapping[str, Any],
	spec: MigrationSpec,
	fieldname: str,
) -> Any:
	"""Use the value identity after live preflight verifies name=value."""

	return value


def item_attribute_value_to_standard_child(
	document: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
) -> Mapping[str, Any]:
	"""Move one legacy value master into ERPNext's attribute child table."""

	value = document.get("attribute_value")
	return {
		**_system_values(document),
		"doctype": "Item Attribute Value",
		"parent": document.get("attribute_name"),
		"parenttype": "Item Attribute",
		"parentfield": "item_attribute_values",
		"attribute_value": value,
		# Legacy has no abbreviation. Exact legacy Item codes are retained, so
		# this fallback is not used to rename migrated physical Items.
		"abbr": value,
	}


def item_variant_to_standard_item(
	document: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
) -> Mapping[str, Any]:
	"""Represent a legacy physical Item Variant as a standard ERPNext Item."""

	attributes = document.get("attributes") or []
	standalone = not attributes and document.get("name") == document.get("item")
	output = _system_values(document)
	output.update(
		{
			"doctype": "Item",
			"item_code": document.get("name"),
			"item_name": document.get("name"),
			"variant_of": None if standalone else document.get("item"),
			"has_variants": 0,
			"item_tuple_attribute": document.get("item_tuple_attribute"),
			"sync_with_erp": document.get("sync_with_erp") or 0,
			"attributes": [
				{
					**_system_values(row),
					"doctype": "Item Variant Attribute",
					"variant_of": document.get("item"),
					"attribute": row.get("attribute"),
					"attribute_value": row.get("attribute_value"),
					"display_name": row.get("display_name"),
					"display_name_is_empty": row.get("display_name_is_empty") or 0,
				}
				for row in attributes
			],
		}
	)
	return output


def essdee_debit_to_debit(
	document: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
) -> Mapping[str, Any]:
	against = document.get("against")
	if against != "Work Order":
		raise MigrationError(
			f"Essdee Debit {document.get('name')} has unsupported against={against!r}"
		)
	output = _copy_common_fields(document, spec, plan)
	output["doctype"] = 'YRP Debit'
	output["work_order"] = document.get("against_id")
	if not output.get("work_order"):
		raise MigrationError(f"Essdee Debit {document.get('name')} has no Work Order")
	return output


def ipd_process_to_f16(
	document: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
) -> Mapping[str, Any]:
	stage = document.get("stage")
	output = _system_values(document)
	output.update(
		{
			"doctype": 'YRP IPD Process',
			"process_name": document.get("process_name"),
			"in_stage": stage,
			"out_stage": stage,
		}
	)
	return output


def derive_stock_entry_detail_reference(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Give the legacy plain-text receipt/challan row ID its target controller."""
	result = dict(output)
	if not source.get("against_id_detail"):
		return result
	parent = parent or {}
	child = {
		("Delivery Challan", "DC Completion"): "Delivery Challan Item",
		("Goods Received Note", "GRN Completion"): "Goods Received Note Item",
	}.get((parent.get("against"), parent.get("purpose")))
	if not child or not parent.get("against_id"):
		raise MigrationError(
			f"Stock Entry Detail {source.get('name')}: cannot resolve reference "
			f"{source.get('against_id_detail')!r} from its parent Stock Entry"
		)
	result["against"] = plan.specs[child].target
	return result


def derive_delivery_challan_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["from_warehouse"] = source.get("from_location")
	result["to_warehouse"] = source.get("supplier")
	return result


def derive_goods_received_note_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["from_warehouse"] = source.get("supplier")
	result["to_warehouse"] = source.get("delivery_location")
	item_lots = {
		row.get("lot")
		for row in source.get("items") or []
		if row.get("lot")
	}
	# The legacy header field was hidden and optional. Its item rows are the
	# authoritative stock dimensions: 13,380 blank-header GRNs have one row Lot
	# and 809 intentionally span several Lots. Populate the header only when all
	# rows agree; multi-Lot GRNs retain their exact row dimensions and a blank
	# historical header instead of receiving an invented value.
	result["lot"] = source.get("lot") or (
		next(iter(item_lots)) if len(item_lots) == 1 else None
	)
	return result


def derive_purchase_order_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["is_yrp_managed"] = 1
	fulfilment_status = {
		"Delivered": "Received",
		"Partially Delivered": "Partially Received",
	}.get(source.get("status"), source.get("status") or "Draft")
	result["yrp_fulfillment_status"] = fulfilment_status
	result["status"] = {
		"Ordered": "To Receive",
		"Partially Received": "To Receive",
		"Received": "Completed",
	}.get(fulfilment_status, fulfilment_status)

	items = result.get("items") or []
	result["total_qty"] = sum(float(row.get("qty") or 0) for row in items)
	result["total_stock_qty"] = sum(float(row.get("stock_qty") or 0) for row in items)
	result["total"] = sum(float(row.get("amount") or 0) for row in items)
	result["total_discount"] = sum(
		float(row.get("discount_amount") or 0) for row in items
	)
	result["total_tax"] = sum(float(row.get("tax_amount") or 0) for row in items)
	result["grand_total"] = sum(float(row.get("total_amount") or 0) for row in items)
	result["net_total"] = result["total"] - result["total_discount"]
	result["total_taxes_and_charges"] = result["total_tax"]
	result["conversion_rate"] = float(result.get("conversion_rate") or 1)
	result["base_total"] = result["total"] * result["conversion_rate"]
	result["base_net_total"] = result["net_total"] * result["conversion_rate"]
	result["base_total_taxes_and_charges"] = (
		result["total_tax"] * result["conversion_rate"]
	)
	result["base_grand_total"] = result["grand_total"] * result["conversion_rate"]
	received_qty = sum(float(row.get("received_qty") or 0) for row in items)
	result["per_received"] = (
		100 * received_qty / result["total_qty"] if result["total_qty"] else 0
	)
	item_lots = {
		row.get("lot")
		for row in source.get("items") or []
		if row.get("lot")
	}
	# The F16 operational header dimension was introduced after these records.
	# Preserve an explicit legacy default; otherwise it is safe to infer the
	# header only when every historical item row agrees on one Lot. Multi-lot
	# Purchase Orders retain a blank header and their exact per-row dimensions.
	result["lot"] = source.get("default_lot") or (
		next(iter(item_lots)) if len(item_lots) == 1 else None
	)
	return result


def derive_purchase_order_item_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	item_code = result.get("item_code")
	uom = result.get("uom")
	qty = float(result.get("qty") or 0)
	rate = float(result.get("rate") or 0)
	amount = qty * rate

	# The legacy row stores its physical Item identity, quantity, UOM and final
	# rate directly; it has no ERPNext stock-UOM/base-currency shadow fields.
	# The commonized target is single-company/single-currency, and historical
	# YRP POs never drive ERPNext stock. A 1:1 shadow therefore preserves the
	# legacy row's commercial quantity and amount without inventing a conversion.
	result["item_name"] = result.get("item_name") or item_code
	result["stock_uom"] = result.get("stock_uom") or uom
	result["conversion_factor"] = result.get("conversion_factor") or 1.0
	result["stock_qty"] = qty * float(result["conversion_factor"])
	result["received_qty"] = max(
		qty
		- float(result.get("pending_quantity") or 0)
		- float(result.get("cancelled_quantity") or 0),
		0,
	)
	result["amount"] = (
		result.get("amount") if result.get("amount") is not None else amount
	)
	result["discount_amount"] = (
		float(result["amount"]) * float(result.get("discount_percentage") or 0) / 100
	)
	result["tax_amount"] = (
		(float(result["amount"]) - result["discount_amount"])
		* float(result.get("tax") or 0)
		/ 100
	)
	result["total_amount"] = (
		float(result["amount"]) - result["discount_amount"] + result["tax_amount"]
	)
	result["base_rate"] = result.get("base_rate") if result.get("base_rate") is not None else rate
	result["base_amount"] = (
		result.get("base_amount") if result.get("base_amount") is not None else amount
	)
	return result


def item_to_standard_item(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Build the standard template/standalone Item identity from a source Item."""

	result = dict(output)
	result["item_code"] = source.get("name")
	result["item_name"] = result.get("item_name") or source.get("name")
	result["has_variants"] = int(bool(source.get("attributes")))
	result["variant_of"] = None
	result["variant_based_on"] = "Item Attribute"
	return result


def derive_process_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	# Essdee's Work Order PI flow requires one billing item per Process. Cutting
	# predates that source field, and setup has always supplied this reviewed
	# default. Put it in the canonical transform so write and verification agree.
	if source.get("name") == "Cutting" and not result.get("item"):
		result["item"] = "Cutting Charges"
	return result


def derive_purchase_invoice_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Classify pre-``against`` invoices from their authoritative child data.

	All 6,940 blank historical rows carry GRNs and no Work Order billed rows.
	Every one of the 601 Work Order invoices carries billed-detail rows. This is
	the same structural distinction used by the current Purchase Invoice flow.
	"""

	result = dict(output)
	result["against"] = {
		"Work Order": "YRP Work Order",
		"Purchase Order": "Purchase Order",
	}.get(result.get("against"), result.get("against"))
	if not result.get("against"):
		result["against"] = (
			'YRP Work Order' if source.get("pi_work_order_billed_details") else 'Purchase Order'
		)
	mapped_items = list(result.get("items") or [])
	commercial_rows = {}
	physical_rows = []
	for source_row, target_row in zip(
		source.get("items") or [],
		mapped_items,
		strict=True,
	):
		source_rate = _legacy_purchase_invoice_source_rate(
			source_row,
			against=result.get("against"),
		)
		lot = source_row.get("lot") or target_row.get("lot")
		qty = float(target_row.get("qty") or 0)
		rate = float(target_row.get("rate") or 0)
		group_key = _commercial_group_key(
			target_row.get("item"),
			lot,
			target_row.get("uom"),
			source_rate,
			target_row.get("tax"),
		)
		physical_row = dict(target_row)
		physical_row.update(
			{
				"lot": lot,
				"source_rate": source_rate,
				# Preserve the exact historical direct-row amount. Legacy invoice
				# rows can contain rounding or adjustments that intentionally differ
				# from qty * rate. Only the grouped commercial row below is derived.
				"amount": target_row.get("amount"),
				"essdee_group_key": group_key,
				"essdee_rate_weight": 1,
			}
		)
		physical_rows.append(physical_row)

		commercial_row = commercial_rows.setdefault(
			group_key,
			{
				"doctype": 'SD YRP Essdee Purchase Invoice Item',
				"item": target_row.get("item"),
				"lot": lot,
				"item_group": target_row.get("item_group"),
				"expense_head": source_row.get("expense_head"),
				"qty": 0,
				"uom": target_row.get("uom"),
				"source_rate": source_rate,
				"rate": rate,
				"amount": 0,
				"tax": target_row.get("tax"),
				"group_key": group_key,
			},
		)
		if abs(float(commercial_row["rate"] or 0) - rate) > 0.000001:
			raise MigrationError(
				f"Purchase Invoice {source.get('name')} has conflicting final rates "
				f"for commercial group {group_key}"
			)
		if (
			commercial_row.get("expense_head")
			and source_row.get("expense_head")
			and commercial_row["expense_head"] != source_row["expense_head"]
		):
			raise MigrationError(
				f"Purchase Invoice {source.get('name')} has conflicting expense heads "
				f"for commercial group {group_key}"
			)
		commercial_row["expense_head"] = (
			commercial_row.get("expense_head") or source_row.get("expense_head")
		)
		commercial_row["qty"] += qty
		commercial_row["amount"] += qty * rate

	result["essdee_items"] = list(commercial_rows.values())
	result["essdee_rate_table_source"] = "migrated_v1"
	if result.get("against") == 'YRP Work Order':
		# The F15 rows are commercial Process items, not physical valuation rows.
		# Preserve them only in Essdee's visible table; the migration writer builds
		# the base table from the invoice's exact linked GRNs before inserting it.
		result["items"] = []
	else:
		# Purchase Order source rows already are the direct linked-GRN variants.
		# Retain them for stock valuation and add the grouped commercial projection.
		result["items"] = physical_rows
	return result


def _legacy_purchase_invoice_source_rate(source_row, *, against):
	source_rate = source_row.get("actual_rate")
	if (
		against == 'Purchase Order'
		and not float(source_rate or 0)
		and float(source_row.get("rate") or 0)
	):
		# Old PO invoices predate reliable actual_rate capture and retain its
		# database default zero. Their non-zero row rate is the only historical
		# material-rate value and must keep separately priced GRN groups distinct.
		source_rate = source_row.get("rate")
	if source_rate is None or source_rate == "":
		source_rate = source_row.get("source_rate")
	if source_rate is None or source_rate == "":
		source_rate = source_row.get("rate") or 0
	return float(source_rate)


def _commercial_group_key(item, lot, uom, source_rate, tax):
	payload = [
		item or "",
		lot or "",
		uom or "",
		round(float(source_rate or 0), 6),
		tax or "",
	]
	encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
	return hashlib.sha256(encoded.encode()).hexdigest()


def derive_product_item_name(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	# Legacy Product rows predate item_name. style_no is complete and is the
	# autoname source, so this preserves an existing business identity.
	result["item_name"] = result.get("item_name") or source.get("style_no") or source.get("name")
	return result


def remove_empty_ipd_process_placeholders(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["original_process_rows"] = deepcopy(source.get("ipd_processes") or [])
	result["ipd_processes"] = [
		row for row in result.get("ipd_processes") or [] if row.get("process_name")
	]
	return result


def derive_production_order_detail_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["item"] = (parent or {}).get("item")
	return result


def derive_workstation_fields(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["workstation_name"] = source.get("name")
	return result


def default_legacy_stitching_category(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Use the deployed target schema's first valid category for legacy blanks."""

	return _default_first_select_option(output, spec, "category")


def default_legacy_lot_costing_type(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Use the deployed target schema's first valid legacy costing mode."""

	return _default_first_select_option(output, spec, "lot_costing_type")


def _default_first_select_option(
	output: Mapping[str, Any], spec: MigrationSpec, fieldname: str
) -> Mapping[str, Any]:
	result = dict(output)
	if result.get(fieldname) not in (None, ""):
		return result
	field = next(
		(
			row
			for row in spec.target_schema.get("fields") or []
			if row.get("fieldname") == fieldname
		),
		None,
	)
	options = [
		value.strip()
		for value in str((field or {}).get("options") or "").splitlines()
		if value.strip()
	]
	if (field or {}).get("fieldtype") != "Select" or not options:
		raise MigrationError(
			f"{spec.target}.{fieldname} has no schema-defined legacy Select option"
		)
	result[fieldname] = options[0]
	return result


def derive_grn_deliverable_dimensions(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["lot"] = result.get("lot") or (parent or {}).get("lot")
	# The current production_api schema does not expose valuation-lineage fields,
	# so historical rows normally remain blank. Preserve an explicit value when
	# a newer source snapshot supplies it; never derive one from row order.
	target_fields = {
		row.get("fieldname") for row in spec.target_schema.get("fields") or []
	}
	for fieldname in (
		"goods_received_note_item",
		"received_item_variant",
		"work_order_deliverable",
		"consumption_sle",
		"output_receipt_sle",
		"material_value",
		"stock_dimensions",
	):
		if fieldname in source and fieldname in target_fields:
			result[fieldname] = deepcopy(source[fieldname])
	return result


def _copy_common_fields(
	document: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
) -> dict[str, Any]:
	target_fields = {
		row["fieldname"]
		for row in spec.target_schema.get("fields") or []
		if row.get("fieldname")
	}
	output = _system_values(document)
	output["doctype"] = spec.target
	for source_field, value in document.items():
		if source_field in SYSTEM_FIELDS or source_field in spec.ignored_fields:
			continue
		target_field = spec.field_map.get(source_field, source_field)
		if target_field not in target_fields:
			continue
		transformer_name = spec.value_transformers.get(source_field)
		if transformer_name:
			transformer = plan.value_transformers[transformer_name]
			value = transformer(value, document, spec, source_field)
		output[target_field] = deepcopy(value)
	return output


def _system_values(document: Mapping[str, Any]) -> dict[str, Any]:
	return {
		fieldname: deepcopy(document[fieldname])
		for fieldname in SYSTEM_FIELDS
		if fieldname in document
	}



def sms_settings_with_roles(document, spec, plan):
	"""Preserve SMS-scoped Has Role rows without importing all User role rows."""
	from essdee_yrp.migration.engine import transform_document

	parent = deepcopy(document)
	roles = parent.pop("allowed_roles", None)
	output = transform_document(parent, plan, _spec_override=replace(spec, custom_transformer=None))
	if roles is None:
		return output
	for schema in (spec.source_schema, spec.target_schema):
		field = next((f for f in schema.get("fields", []) if f.get("fieldname") == "allowed_roles"), {})
		if field.get("fieldtype") != "Table" or field.get("options") != "Has Role":
			raise MigrationError("SMS Settings.allowed_roles must use Has Role on both sites")
	allowed = SYSTEM_FIELDS | {"doctype", "role"}
	for row in roles:
		if row.get("doctype") != "Has Role":
			raise MigrationError("Unexpected SMS Settings role child DocType")
		for key, value in row.items():
			if key not in allowed and value not in (None, "", 0, False, [], {}):
				raise MigrationError(f"Unmapped SMS role field Has Role.{key}")
		for key, expected in (("parent", "SMS Settings"), ("parenttype", "SMS Settings"), ("parentfield", "allowed_roles")):
			if row.get(key) != expected:
				raise MigrationError(f"Invalid SMS role child {key}")
	output["allowed_roles"] = deepcopy(roles)
	return output


TRANSFORMERS = {
	"sms_settings_with_roles": sms_settings_with_roles,
	"essdee_debit_to_debit": essdee_debit_to_debit,
	"ipd_process_to_f16": ipd_process_to_f16,
	"item_attribute_value_to_standard_child": item_attribute_value_to_standard_child,
	"item_variant_to_standard_item": item_variant_to_standard_item,
}

VALUE_TRANSFORMERS = {
	"attribute_value_link_to_data": attribute_value_link_to_data,
	"supplier_to_warehouse": supplier_to_warehouse,
	"purchase_order_status": purchase_order_status,
	"purchase_order_open_status": purchase_order_open_status,
}

POST_TRANSFORMERS = {
	"derive_stock_entry_detail_reference": derive_stock_entry_detail_reference,
	"derive_delivery_challan_fields": derive_delivery_challan_fields,
	"derive_goods_received_note_fields": derive_goods_received_note_fields,
	"derive_purchase_order_fields": derive_purchase_order_fields,
	"derive_purchase_order_item_fields": derive_purchase_order_item_fields,
	"item_to_standard_item": item_to_standard_item,
	"derive_process_fields": derive_process_fields,
	"derive_purchase_invoice_fields": derive_purchase_invoice_fields,
	"derive_product_item_name": derive_product_item_name,
	"remove_empty_ipd_process_placeholders": remove_empty_ipd_process_placeholders,
	"derive_production_order_detail_fields": derive_production_order_detail_fields,
	"derive_workstation_fields": derive_workstation_fields,
	"default_legacy_stitching_category": default_legacy_stitching_category,
	"default_legacy_lot_costing_type": default_legacy_lot_costing_type,
	"derive_grn_deliverable_dimensions": derive_grn_deliverable_dimensions,
}
