"""Reviewed pure transformations for Production API historical data.

These functions do not import Frappe and can be exercised before either live
site is opened.  Site-derived invariants are checked again by the live runner.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from essdee_yrp.migration.engine import (
	MigrationError,
	MigrationPlan,
	MigrationSpec,
	SYSTEM_FIELDS,
)


DEFAULT_RECEIVED_TYPE = "Accepted"


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
	output["doctype"] = "Debit"
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
			"doctype": "IPD Process",
			"process_name": document.get("process_name"),
			"in_stage": stage,
			"out_stage": stage,
		}
	)
	return output


def stock_settings_to_yrp_stock_settings(
	document: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
) -> Mapping[str, Any]:
	return {
		"doctype": "YRP Stock Settings",
		"name": "YRP Stock Settings",
		"transit_warehouse": document.get("transit_warehouse"),
		"default_received_type": document.get("default_received_type"),
		"default_rejected_received_type": document.get("default_rejected_type"),
		"default_fg_lot": document.get("default_fg_lot"),
		"add_finishing_plan_goods_value": document.get(
			"add_finishing_plan_goods_value"
		),
	}


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
	result["delivery_warehouse"] = source.get("default_delivery_location")
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
	if not result.get("against"):
		result["against"] = (
			"Work Order" if source.get("pi_work_order_billed_details") else "Purchase Order"
		)
	return result


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


def default_received_type(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	result = dict(output)
	result["received_type"] = result.get("received_type") or DEFAULT_RECEIVED_TYPE
	return result


def default_legacy_stitching_category(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Backfill rows created before stitching categories were introduced.

	The 796 blank rows stop on 2025-09-18; populated rows start on 2025-09-19.
	The Production API row generator defaults every new row to ``Body`` and the
	operator changes only exceptional panel categories afterwards.
	"""

	result = dict(output)
	result["category"] = result.get("category") or "Body"
	return result


def default_legacy_lot_costing_type(
	output: Mapping[str, Any],
	source: Mapping[str, Any],
	spec: MigrationSpec,
	plan: MigrationPlan,
	parent: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
	"""Preserve the manual costing behavior used before 22-Mar-2024.

	The type field was added with the optional lot-quantity fetch modes. The
	original path maps to the explicit ``Costing`` branch in that same change.
	"""

	result = dict(output)
	result["lot_costing_type"] = result.get("lot_costing_type") or "Costing"
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
	result["received_type"] = result.get("received_type") or DEFAULT_RECEIVED_TYPE
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


TRANSFORMERS = {
	"essdee_debit_to_debit": essdee_debit_to_debit,
	"ipd_process_to_f16": ipd_process_to_f16,
	"stock_settings_to_yrp_stock_settings": stock_settings_to_yrp_stock_settings,
}

VALUE_TRANSFORMERS = {
	"supplier_to_warehouse": supplier_to_warehouse,
	"purchase_order_status": purchase_order_status,
	"purchase_order_open_status": purchase_order_open_status,
}

POST_TRANSFORMERS = {
	"derive_delivery_challan_fields": derive_delivery_challan_fields,
	"derive_goods_received_note_fields": derive_goods_received_note_fields,
	"derive_purchase_order_fields": derive_purchase_order_fields,
	"derive_purchase_invoice_fields": derive_purchase_invoice_fields,
	"derive_product_item_name": derive_product_item_name,
	"remove_empty_ipd_process_placeholders": remove_empty_ipd_process_placeholders,
	"derive_production_order_detail_fields": derive_production_order_detail_fields,
	"derive_workstation_fields": derive_workstation_fields,
	"default_received_type": default_received_type,
	"default_legacy_stitching_category": default_legacy_stitching_category,
	"default_legacy_lot_costing_type": default_legacy_lot_costing_type,
	"derive_grn_deliverable_dimensions": derive_grn_deliverable_dimensions,
}
