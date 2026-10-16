"""Permission-safe service contract for the Fabric Store web workspace.

The module exposes UI capabilities and shared document guards. Business rules
remain in the existing DocType controllers; this layer only coordinates those
controllers for the web workspace.
"""

from __future__ import annotations

import sys

import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import cint, flt
from yrp.stock.api import get_stock_dimensions_for_ui
from yrp.stock.save_stock_items import (
	group_items_for_ui,
	ungroup_items_from_ui,
)
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
	get_return_delivery_items,
	make_dc_completion,
)
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
	get_purchase_order_defaults,
	make_grn_completion,
)
from yrp.yrp.doctype.yrp_purchase_order.yrp_purchase_order import apply_price_details

from essdee_yrp.api.work_order import fetch_summary_details
from essdee_yrp.delivery_challan_hooks import create_return_grn
from essdee_yrp.fabric_store.documents import delivery_challan as delivery_challan_service
from essdee_yrp.fabric_store.documents import goods_received_note as goods_received_note_service
from essdee_yrp.fabric_store.documents import purchase_order as purchase_order_service
from essdee_yrp.fabric_store.documents import work_order as work_order_service
from essdee_yrp.fabric_store.documents.common import (
	assert_expected_modified,
	filter_authorized_capabilities,
	get_document_permissions,
	get_draft_completion_stock_entry,
	get_effective_fields,
	get_workspace_base,
)
from essdee_yrp.print_registry import get_document_print_formats
from essdee_yrp.purchase.lot_cut_quantity import can_view_lot_cut_quantity

DOCUMENT_KEYS = {
	"work_orders": "YRP Work Order",
	"purchase_orders": "Purchase Order",
}

STOCK_OPERATION_DOCTYPES = {
	"stock_entry": "YRP Stock Entry",
	"stock_reconciliation": "YRP Stock Reconciliation",
	"stock_update": "YRP Stock Update",
	"lot_transfer": "SD YRP Lot Transfer",
}

RELATED_DOCUMENT_DOCTYPES = {
	"delivery_challan": "YRP Delivery Challan",
	"goods_received_note": "YRP Goods Received Note",
}

SUPPORTED_DOCTYPES = set(
	[
		*DOCUMENT_KEYS.values(),
		*STOCK_OPERATION_DOCTYPES.values(),
		*RELATED_DOCUMENT_DOCTYPES.values(),
	]
)

SECTION_LABELS = {
	"work_orders": _("Work Orders"),
	"purchase_orders": _("Purchase Orders"),
	"stock_transfers": _("Stock Transfers"),
	"reports": _("Reports"),
}

OPERATION_LABELS = {
	"stock_entry": _("Stock Entry"),
	"stock_reconciliation": _("Stock Reconciliation"),
	"stock_update": _("Stock Update"),
	"lot_transfer": _("Lot Transfer"),
}

WORK_ORDER_DETAIL_FIELDS = (
	"wo_date",
	"process_name",
	"delivery_location",
	"delivery_location_name",
	"planned_start_date",
	"planned_end_date",
	"expected_delivery_date",
	"start_date",
	"end_date",
	"open_status",
	"planned_quantity",
	"total_quantity",
	"is_rework",
	"parent_wo",
	"comments",
)

RELATED_DOCUMENT_FIELDS = (
	"name",
	"docstatus",
	"posting_date",
	"posting_time",
	"item",
	"modified",
)

ITEM_TABLE_FIELDS = {
	"Purchase Order": "items",
	"YRP Stock Entry": "items",
	"YRP Stock Reconciliation": "items",
	"YRP Stock Update": "stock_update_details",
	"SD YRP Lot Transfer": "items",
	"YRP Delivery Challan": "items",
	"YRP Goods Received Note": "items",
}

DETAIL_FIELD_TYPES = {
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Select",
	"Link",
	"Dynamic Link",
	"Date",
	"Datetime",
	"Time",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Check",
}

PURCHASE_ORDER_RECORD_FIELDS = (
	"status",
	"open_status",
	"is_yrp_managed",
	"supplier",
	"supplier_name",
	"transaction_date",
	"schedule_date",
	"set_warehouse",
	"currency",
	"total",
	"grand_total",
)

PURCHASE_ORDER_DETAIL_FIELDS = {
	"supplier",
	"supplier_name",
	"transaction_date",
	"schedule_date",
	"set_warehouse",
	"currency",
	"total",
	"total_taxes_and_charges",
	"grand_total",
	"open_status",
}

PURCHASE_ORDER_EDITOR_FIELDS = {
	"supplier",
	"transaction_date",
	"schedule_date",
	"company",
	"set_warehouse",
	"deliver_to_supplier",
	"default_delivery_location",
	"currency",
	"terms_and_condition",
	"comments",
}

FABRIC_STOCK_ENTRY_PURPOSES = ("Material Issue", "Material Consumed", "Send to Warehouse")
FABRIC_STOCK_COMPLETION_PURPOSES = ("DC Completion", "GRN Completion")
FABRIC_STOCK_RECONCILIATION_PURPOSES = ("Stock Reconciliation", "Opening Stock")
FABRIC_STOCK_UPDATE_TYPES = ("Add", "Reduce")

STOCK_OPERATION_FIELDS = {
	"stock_entry": {
		"purpose",
		"against",
		"against_id",
		"posting_date",
		"posting_time",
		"edit_posting_date_and_time",
		"from_warehouse",
		"to_warehouse",
		"from_supplier",
		"to_supplier",
		"transfer_supplier",
		"vehicle_no",
		"comments",
	},
	"stock_reconciliation": {
		"purpose",
		"posting_date",
		"posting_time",
		"edit_posting_date_and_time",
		"default_warehouse",
		"default_supplier",
		"comments",
	},
	"stock_update": {
		"update_type",
		"posting_date",
		"posting_time",
		"edit_posting_date_and_time",
		"warehouse",
		"supplier",
		"comments",
	},
	"lot_transfer": {
		"posting_date",
		"posting_time",
		"edit_posting_date_and_time",
		"comments",
	},
}


def _require_supported_doctype(doctype: str) -> str:
	if doctype not in SUPPORTED_DOCTYPES:
		frappe.throw(_("Unsupported Fabric Store document: {0}").format(doctype))
	return doctype


def _require_supported_operation(operation: str) -> str:
	if operation not in STOCK_OPERATION_DOCTYPES:
		frappe.throw(_("Unsupported Fabric Store operation: {0}").format(operation))
	return STOCK_OPERATION_DOCTYPES[operation]


def _permission_flags(doctype: str, doc=None) -> dict[str, bool]:
	_require_supported_doctype(doctype)
	return get_document_permissions(doctype, doc)


def _get_supported_document(doctype: str, name: str, permission: str = "read"):
	_require_supported_doctype(doctype)
	doc = frappe.get_doc(doctype, name)
	frappe.has_permission(doctype, ptype=permission, doc=doc, throw=True)
	return doc


def _document_status(doc) -> str:
	return {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(
		cint(doc.docstatus),
		_("Draft"),
	)


def _serialize_document(doc, fields=()) -> dict:
	"""Serialize a deliberately small, allowlisted document projection."""

	_require_supported_doctype(doc.doctype)
	payload = {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"status": _document_status(doc),
		"modified": doc.get("modified"),
		"permissions": _permission_flags(doc.doctype, doc),
	}
	for fieldname in fields:
		if fieldname not in payload:
			payload[fieldname] = doc.get(fieldname)
	return payload


def _assert_not_stale(doc, expected_modified=None) -> None:
	assert_expected_modified(doc, expected_modified)


def _document_details(doc) -> list[dict]:
	permitted = set(get_permitted_fields(doc.doctype, permission_type="read"))
	details = []
	for field in doc.meta.fields:
		if (
			field.fieldname not in permitted
			or field.hidden
			or field.fieldtype not in DETAIL_FIELD_TYPES
			or field.fieldname in {"amended_from"}
		):
			continue
		value = doc.get(field.fieldname)
		if value in (None, ""):
			continue
		details.append(
			{
				"fieldname": field.fieldname,
				"label": field.label or field.fieldname,
				"fieldtype": field.fieldtype,
				"options": field.options or "",
				"value": value,
				"read_only": bool(field.read_only or doc.docstatus != 0),
			}
		)
	return details


def _document_item_groups(doc) -> tuple[list, int]:
	table_field = ITEM_TABLE_FIELDS.get(doc.doctype)
	permitted = set(get_permitted_fields(doc.doctype, permission_type="read"))
	if not table_field or not ({table_field, "item_details"} & permitted):
		return [], 0
	rows = doc.get(table_field) or []
	doc.run_method("onload")
	onload = doc.get("__onload") or {}
	item_groups = onload.get("item_details") or []
	if isinstance(item_groups, str):
		item_groups = frappe.parse_json(item_groups)
	if not item_groups and rows:
		item_groups = group_items_for_ui(rows, doc.doctype)
	return item_groups or [], len(rows)


def _purchase_order_grn_capability(doc) -> dict:
	permissions = _permission_flags("YRP Goods Received Note")
	if not permissions["can_create"]:
		return {"can_create": False, "reason": _("You do not have permission to create Goods Received Notes.")}
	if cint(doc.docstatus) != 1:
		return {"can_create": False, "reason": _("Submit this Purchase Order before creating a Goods Received Note.")}
	if doc.get("open_status") == "Close":
		return {"can_create": False, "reason": _("This Purchase Order is closed.")}
	if not doc.get("is_yrp_managed"):
		return {"can_create": False, "reason": _("Only YRP managed Purchase Orders can create a Goods Received Note here.")}
	try:
		defaults = get_purchase_order_defaults(doc.name)
	except (frappe.ValidationError, frappe.PermissionError) as error:
		return {"can_create": False, "reason": str(error)}
	if not defaults.get("items"):
		return {"can_create": False, "reason": _("No pending quantities remain to receive.")}
	return {"can_create": True, "reason": ""}


@frappe.whitelist()
def get_purchase_order_workspace(purchase_order: str) -> dict:
	return purchase_order_service.get_purchase_order_workspace(
		purchase_order,
		_adapter=sys.modules[__name__],
	)


@frappe.whitelist()
def get_purchase_order_editor(purchase_order: str | None = None, source=None) -> dict:
	return purchase_order_service.get_purchase_order_editor(
		purchase_order,
		source,
		_adapter=sys.modules[__name__],
	)


@frappe.whitelist()
def get_purchase_order_item_schema(item: str, purchase_order: str | None = None) -> dict:
	"""Return the common attribute matrix schema for a Purchase Order item."""

	if purchase_order:
		doc = _get_supported_document("Purchase Order", purchase_order)
		frappe.has_permission("Purchase Order", ptype="write", doc=doc, throw=True)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Purchase Orders can be edited."))
	else:
		frappe.has_permission("Purchase Order", ptype="create", throw=True)
	frappe.has_permission("Item", ptype="read", throw=True)
	if not item:
		frappe.throw(_("Item is required."))
	from essdee_yrp.cutting.web_workspace import _get_stock_item_schema_data

	return _get_stock_item_schema_data(item)


@frappe.whitelist()
def search_purchase_order_additional_parameter_values(
	item: str,
	parameter_key: str,
	txt: str = "",
	purchase_order: str | None = None,
	page_length: int = 20,
) -> list[dict]:
	"""Search an Item's configured PO parameter values under Purchase Order permission.

	The value DocType is intentionally administrator-managed. Purchase users still
	need to select its values, so this endpoint exposes only the key configured on
	the selected Item instead of granting broad read access to the master.
	"""

	if not item:
		frappe.throw(_("Item is required."))
	parameter_key = str(parameter_key or "").strip()
	if not parameter_key:
		frappe.throw(_("Additional Parameter is required."))

	schema = get_purchase_order_item_schema(item, purchase_order)
	configured_keys = {
		str(row.get("additional_parameter_key") or "").strip()
		for row in schema.get("additional_parameters") or []
	}
	legacy_keys = (
		_purchase_order_historical_parameter_keys(
			purchase_order,
			schema.get("item") or item,
		)
		if purchase_order and parameter_key not in configured_keys
		else set()
	)
	if parameter_key not in configured_keys and parameter_key not in legacy_keys:
		frappe.throw(
			_("Additional Parameter {0} is not configured for Item {1}.").format(
				frappe.bold(parameter_key),
				frappe.bold(item),
			)
		)

	filters = {"key": parameter_key}
	txt = str(txt or "").strip()
	if txt:
		filters["value"] = ["like", f"%{txt}%"]
	rows = frappe.get_all(
		"YRP Additional Parameter Value",
		filters=filters,
		fields=["name", "value"],
		order_by="value asc",
		limit_page_length=min(max(cint(page_length), 1), 50),
	)
	return [
		{"name": row.name, "label": row.value or row.name}
		for row in rows
	]


def _purchase_order_historical_parameter_keys(purchase_order: str, item: str) -> set[str]:
	"""Return legacy keys already stored for an Item on an authorized draft PO."""

	doc = _get_supported_document("Purchase Order", purchase_order)
	frappe.has_permission("Purchase Order", ptype="write", doc=doc, throw=True)
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Only Draft Purchase Orders can be edited."))

	keys = set()
	for row in doc.get("items") or []:
		item_code = row.get("item_code") or row.get("item_variant")
		if not item_code:
			continue
		parent_item = frappe.get_cached_value("Item", item_code, "variant_of") or item_code
		if item_code != item and parent_item != item:
			continue
		parameters = row.get("additional_parameters") or []
		if isinstance(parameters, str):
			try:
				parameters = frappe.parse_json(parameters)
			except (TypeError, ValueError):
				parameters = []
		for parameter in parameters or []:
			key = str(parameter.get("additional_parameter_key") or "").strip()
			if key:
				keys.add(key)
	return keys


@frappe.whitelist()
def get_purchase_order_item_price(item_detail, supplier: str, purchase_order: str | None = None) -> dict:
	"""Resolve the same authoritative supplier Item Price used by the Desk PO editor."""

	item_detail = item_detail if isinstance(item_detail, dict) else frappe.parse_json(item_detail or "{}")
	_assert_purchase_order_price_preview_access(purchase_order)
	if not supplier:
		frappe.throw(_("Select Supplier before adding Purchase Order items."))
	if not item_detail.get("name"):
		frappe.throw(_("Item is required."))

	preview = _preview_purchase_order_prices([{"items": [item_detail]}], supplier)
	row = (preview.get("rows") or [{}])[0]
	values = row.get("values") or {}
	result = {
		"status": row.get("status") or "missing",
		"tax": row.get("tax"),
		"tax_rate": row.get("tax_rate") or 0,
		"lead_time_days": row.get("lead_time_days"),
	}
	if set(values) == {"default"}:
		result["rate"] = values["default"].get("rate")
		result["tier"] = values["default"].get("tier")
	else:
		result["rates"] = {key: value.get("rate") for key, value in values.items()}
		result["tiers"] = {key: value.get("tier") for key, value in values.items()}
	return result


@frappe.whitelist()
def preview_purchase_order_prices(
	items,
	supplier: str,
	purchase_order: str | None = None,
) -> dict:
	"""Preview whole-draft rates with the same grouping used by PO validation."""

	items = items if isinstance(items, list) else frappe.parse_json(items or "[]")
	if not isinstance(items, list):
		frappe.throw(_("Items must be a list."))
	_assert_purchase_order_price_preview_access(purchase_order)
	if not supplier:
		frappe.throw(_("Select Supplier before adding Purchase Order items."))
	return _preview_purchase_order_prices(items, supplier)


def _assert_purchase_order_price_preview_access(purchase_order):
	if purchase_order:
		doc = _get_supported_document("Purchase Order", purchase_order)
		frappe.has_permission("Purchase Order", ptype="write", doc=doc, throw=True)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Purchase Orders can be edited."))
	else:
		frappe.has_permission("Purchase Order", ptype="create", throw=True)
	frappe.has_permission("Item", ptype="read", throw=True)


def _preview_purchase_order_prices(items, supplier):
	rows, contexts, targets, preview_rows = _build_purchase_order_price_rows(items)
	application = apply_price_details(
		rows,
		supplier=supplier,
		strict=False,
		preview_context=contexts,
	)
	for target, result in zip(targets, application["rows"], strict=True):
		row = preview_rows[target[0]]
		row["values"][target[1]] = dict(result)

	for row in preview_rows:
		value_results = list(row["values"].values())
		if not value_results:
			continue
		row["status"] = max(
			(value.get("status") or "missing" for value in value_results),
			key=lambda status: {"ok": 0, "no_slab": 1, "missing": 2, "ambiguous": 3}.get(
				status, 2
			),
		)
		priced = [value for value in value_results if value.get("tax") is not None]
		if priced:
			row["tax"] = priced[0].get("tax")
			row["tax_rate"] = priced[0].get("tax_rate") or 0
		lead_times = [
			flt(value.get("lead_time_days"))
			for value in value_results
			if value.get("lead_time_days") is not None
		]
		row["lead_time_days"] = max(lead_times, default=None)
	return {"rows": preview_rows, "warnings": application["warnings"]}


def _build_purchase_order_price_rows(items):
	rows = []
	contexts = []
	targets = []
	preview_rows = []
	for group_index, group in enumerate(items):
		for item_index, item in enumerate(group.get("items") or []):
			row_index = len(preview_rows)
			preview_rows.append(
				{
					"group_index": group_index,
					"item_index": item_index,
					"item": item.get("name"),
					"status": "no_slab",
					"tax": None,
					"tax_rate": 0,
					"lead_time_days": None,
					"values": {},
				}
			)
			primary_attribute = item.get("primary_attribute") or group.get("primary_attribute")
			for value_key, value in (item.get("values") or {}).items():
				if flt(value.get("qty")) <= 0:
					continue
				attributes = dict(item.get("attributes") or {})
				if primary_attribute and value_key != "default":
					attributes[primary_attribute] = value_key
				rows.append(
					frappe._dict(
						item_code=item.get("name"),
						qty=value.get("qty"),
					)
				)
				contexts.append(
					{"parent_item": item.get("name"), "attributes": attributes}
				)
				targets.append((row_index, value_key))
	return rows, contexts, targets, preview_rows


@frappe.whitelist()
def save_purchase_order(
	values,
	purchase_order: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	return purchase_order_service.save_purchase_order_document(
		values,
		name=purchase_order,
		submit=submit,
		expected_modified=expected_modified,
		_adapter=sys.modules[__name__],
	)


@frappe.whitelist()
def execute_purchase_order_command(
	purchase_order: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	return purchase_order_service.execute_purchase_order_command(
		purchase_order,
		command,
		payload=payload,
		expected_modified=expected_modified,
	)


def _fabric_stock_dimensions(operation: str) -> list[dict]:
	if operation == "lot_transfer":
		return [
			{"fieldname": "from_lot", "label": _("From Lot"), "options": "SD YRP Lot", "mandatory": 1},
			{"fieldname": "to_lot", "label": _("To Lot"), "options": "SD YRP Lot", "mandatory": 1},
			{"fieldname": "warehouse", "label": _("Warehouse"), "options": "Warehouse", "mandatory": 1},
			{"fieldname": "received_type", "label": _("Received Type"), "options": "YRP Received Type", "mandatory": 1},
		]
	result = []
	for source in get_stock_dimensions_for_ui():
		dimension = dict(source)
		dimension["locked"] = False
		dimension["default_value"] = None
		result.append(dimension)
	return result


@frappe.whitelist()
def get_stock_operation_editor(operation: str, name: str | None = None, source_context=None) -> dict:
	"""Return a context-free grouped editor for a new or existing Draft stock document."""

	doctype = _require_supported_operation(operation)
	frappe.has_permission("Item", ptype="read", throw=True)
	if name:
		doc = _get_supported_document(doctype, name)
		frappe.has_permission(doctype, ptype="write", doc=doc, throw=True)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft documents can be edited."))
		defaults = {key: doc.get(key) for key in STOCK_OPERATION_FIELDS[operation]}
		item_groups, _row_count = _document_item_groups(doc)
		permissions = {
			**_permission_flags(doctype, doc),
			"can_delete": bool(frappe.has_permission(doctype, ptype="delete", doc=doc)),
		}
	else:
		frappe.has_permission(doctype, ptype="create", throw=True)
		defaults = {
			"purpose": "Stock Reconciliation" if operation == "stock_reconciliation" else "",
			"update_type": "",
		}
		source_context = source_context if isinstance(source_context, dict) else frappe.parse_json(source_context or "{}")
		defaults.update(
			{
				key: value
				for key, value in (source_context or {}).items()
				if key in STOCK_OPERATION_FIELDS[operation] and value not in (None, "")
			}
		)
		item_groups = []
		permissions = {
			"can_create": True,
			"can_write": False,
			"can_submit": bool(frappe.has_permission(doctype, ptype="submit")),
		}
	purpose_options = list(FABRIC_STOCK_ENTRY_PURPOSES)
	if name and operation == "stock_entry" and defaults.get("purpose") in FABRIC_STOCK_COMPLETION_PURPOSES:
		purpose_options.insert(0, defaults["purpose"])
	return {
		"operation": operation,
		"doctype": doctype,
		"dimensions": _fabric_stock_dimensions(operation),
		"default_dimensions": {},
		"locked_dimensions": [],
		"name": name,
		"modified": doc.get("modified") if name else None,
		"defaults": defaults,
		"item_groups": item_groups,
		"purpose_options": (
			purpose_options
			if operation == "stock_entry"
			else list(FABRIC_STOCK_RECONCILIATION_PURPOSES)
			if operation == "stock_reconciliation"
			else []
		),
		"update_type_options": list(FABRIC_STOCK_UPDATE_TYPES) if operation == "stock_update" else [],
		"item_filters": {"is_stock_item": 1, "disabled": 0},
		"purpose_locked": bool(
			name
			and operation == "stock_entry"
			and defaults.get("purpose") in FABRIC_STOCK_COMPLETION_PURPOSES
		),
		"protected_completion": bool(
			name
			and operation == "stock_entry"
			and defaults.get("purpose") in FABRIC_STOCK_COMPLETION_PURPOSES
		),
		"permissions": permissions,
	}


def _normalize_lot_transfer_groups(item_details) -> list:
	groups = frappe.parse_json(frappe.as_json(item_details or []))
	required = ("from_lot", "to_lot", "warehouse", "received_type")
	for group in groups:
		for entry in group.get("items") or []:
			dimensions = entry.get("dimensions") or {}
			for fieldname in required:
				entry[fieldname] = entry.get(fieldname) or dimensions.get(fieldname)
				if not entry[fieldname]:
					frappe.throw(_("{0} is required for every Lot Transfer item.").format(fieldname.replace("_", " ").title()))
	return groups


@frappe.whitelist()
def get_stock_item_schema(operation: str, item: str) -> dict:
	"""Return the same authoritative item schema used by Cutting, without plan context."""

	doctype = _require_supported_operation(operation)
	frappe.has_permission(doctype, ptype="create", throw=True)
	frappe.has_permission("Item", ptype="read", throw=True)
	if not item:
		frappe.throw(_("Item is required."))
	from essdee_yrp.cutting.web_workspace import _get_stock_item_schema_data

	return _get_stock_item_schema_data(item)


def _validate_stock_operation_options(operation: str, values: dict, existing_doc=None) -> None:
	if operation == "stock_entry":
		allowed_purposes = set(FABRIC_STOCK_ENTRY_PURPOSES)
		existing_purpose = existing_doc.get("purpose") if existing_doc else None
		if existing_purpose in FABRIC_STOCK_COMPLETION_PURPOSES:
			allowed_purposes.add(existing_purpose)
		if values.get("purpose") not in allowed_purposes:
			frappe.throw(_("Select a supported Stock Entry purpose."))
	if operation == "stock_reconciliation" and values.get("purpose", "Stock Reconciliation") not in FABRIC_STOCK_RECONCILIATION_PURPOSES:
		frappe.throw(_("Select a supported Stock Reconciliation purpose."))
	if operation == "stock_update" and values.get("update_type") not in FABRIC_STOCK_UPDATE_TYPES:
		frappe.throw(_("Select Add or Reduce for Stock Update."))


@frappe.whitelist()
def save_stock_operation(
	operation: str,
	values,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	"""Save one unrestricted stock document through its native controller."""

	doctype = _require_supported_operation(operation)
	values = values if isinstance(values, dict) else frappe.parse_json(values or "{}")
	item_details = values.get("item_details") or []
	if not isinstance(item_details, list) or not item_details:
		frappe.throw(_("Add at least one Item."))

	if name:
		doc = _get_supported_document(doctype, name)
		_validate_stock_operation_options(operation, values, existing_doc=doc)
		frappe.has_permission(doctype, ptype="write", doc=doc, throw=True)
		_assert_not_stale(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft documents can be edited."))
		if operation == "stock_entry" and doc.get("purpose") in FABRIC_STOCK_COMPLETION_PURPOSES:
			if not submit:
				frappe.throw(_("Completion Stock Entries can only be reviewed and submitted here."))
			frappe.has_permission(doctype, ptype="submit", doc=doc, throw=True)
			doc.submit()
			return get_document(doctype, doc.name)
	else:
		_validate_stock_operation_options(operation, values)
		frappe.has_permission(doctype, ptype="create", throw=True)
		doc = frappe.new_doc(doctype)

	header = {
		key: values.get(key)
		for key in STOCK_OPERATION_FIELDS[operation]
		if key in values
	}
	if operation == "stock_reconciliation" and not header.get("purpose"):
		header["purpose"] = "Stock Reconciliation"
	doc.update(header)
	if operation == "stock_reconciliation":
		rows = ungroup_items_from_ui(
			item_details,
			"YRP Stock Reconciliation",
			keep_zero=True,
		)
		doc.set("items", [])
		for row in rows:
			row.setdefault("warehouse", header.get("default_warehouse"))
			doc.append("items", row)
	else:
		if operation == "lot_transfer":
			item_details = _normalize_lot_transfer_groups(item_details)
		doc.item_details = frappe.as_json(item_details)
	if name:
		doc.save()
	else:
		doc.insert()
	if submit:
		frappe.has_permission(doctype, ptype="submit", doc=doc, throw=True)
		doc.submit()
	return get_document(doctype, doc.name)


def _capability(doctype: str, label: str) -> dict:
	return {
		"doctype": doctype,
		"label": label,
		**_permission_flags(doctype),
	}


def _work_order_details(doc) -> list[dict]:
	details = []
	for fieldname in WORK_ORDER_DETAIL_FIELDS:
		field = doc.meta.get_field(fieldname)
		value = doc.get(fieldname)
		if not field or value in (None, ""):
			continue
		details.append(
			{
				"fieldname": fieldname,
				"label": field.label or fieldname,
				"fieldtype": field.fieldtype or "Data",
				"options": field.options or "",
				"value": value,
			}
		)
	return details


def _work_order_related_permissions(doc, doctype: str) -> dict:
	permissions = dict(_permission_flags(doctype))
	if not permissions["can_create"]:
		return permissions
	if cint(doc.docstatus) != 1:
		permissions["can_create"] = False
		permissions["create_reason"] = _("The Work Order must be submitted before creating related documents.")
	elif doc.get("open_status") == "Close":
		permissions["can_create"] = False
		permissions["create_reason"] = _("Closed Work Orders cannot create related documents.")
	return permissions


def _related_work_order_documents(work_order: str, key: str) -> list[dict]:
	doctype = RELATED_DOCUMENT_DOCTYPES[key]
	if not _permission_flags(doctype)["can_read"]:
		return []
	filters = (
		{"work_order": work_order}
		if key == "delivery_challan"
		else {"against": "YRP Work Order", "against_id": work_order}
	)
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=[*RELATED_DOCUMENT_FIELDS, *(["is_return"] if key == "goods_received_note" else [])],
		order_by="modified desc",
		limit_page_length=500,
	)
	return [
		{
			**dict(row),
			"status": _document_status(row),
		}
		for row in rows
	]


def _document_actions(doc) -> dict[str, bool]:
	if cint(doc.docstatus) != 1:
		return {}
	if doc.doctype == "YRP Stock Entry":
		return {"can_make_delivery_challan": bool(frappe.has_permission("YRP Delivery Challan", ptype="create"))}
	if doc.doctype == "YRP Delivery Challan":
		return {
			"can_return": bool(frappe.has_permission("YRP Goods Received Note", ptype="create")),
			"can_complete_transfer": bool(
				doc.get("is_internal_unit")
				and not doc.get("transfer_complete")
				and frappe.has_permission("YRP Stock Entry", ptype="create")
			),
		}
	if doc.doctype == "YRP Goods Received Note":
		return {
			"can_complete_transfer": bool(
				doc.get("is_internal_unit")
				and not doc.get("transfer_complete")
				and frappe.has_permission("YRP Stock Entry", ptype="create")
			),
		}
	return {}


def _document_context(doc) -> dict:
	if doc.doctype == "YRP Delivery Challan":
		work_order = doc.get("work_order")
	elif doc.doctype == "YRP Goods Received Note" and doc.get("against") == "YRP Work Order":
		work_order = doc.get("against_id")
	else:
		work_order = None
	if not work_order:
		return {}
	item = doc.get("item")
	lot = doc.get("lot")
	if not item or not lot:
		work_order_context = frappe.db.get_value(
			"YRP Work Order",
			work_order,
			("item", "lot"),
			as_dict=True,
		) or {}
		item = item or work_order_context.get("item")
		lot = lot or work_order_context.get("lot")
	return {
		key: value
		for key, value in {
			"work_order": work_order,
			"item": item,
			"lot": lot,
		}.items()
		if value not in (None, "")
	}


@frappe.whitelist()
def get_document(doctype: str, name: str) -> dict:
	"""Return one supported document through a permission-filtered projection."""

	doc = _get_supported_document(doctype, name)
	item_groups, item_row_count = _document_item_groups(doc)
	record = _serialize_document(
		doc,
		fields=("is_return", "is_internal_unit", "transfer_complete"),
	)
	return {
		"record": record,
		"context": _document_context(doc),
		"details": _document_details(doc),
		"item_groups": item_groups,
		"item_row_count": item_row_count,
		"permissions": record["permissions"],
		"print_formats": get_document_print_formats(doc),
		"actions": _document_actions(doc),
	}


@frappe.whitelist()
def get_delivery_challan_workspace(name: str | None = None, source=None) -> dict:
	"""Load the focused routed/embedded Delivery Challan workspace."""

	return delivery_challan_service.get_delivery_challan_workspace(name, source)


@frappe.whitelist()
def preview_delivery_challan_source(work_order: str, values=None) -> dict:
	"""Refresh a new Delivery Challan from its authoritative Work Order."""

	return delivery_challan_service.preview_delivery_challan_source(work_order, values)


@frappe.whitelist()
def save_delivery_challan(
	values,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	return delivery_challan_service.save_delivery_challan(
		values,
		name=name,
		submit=cint(submit),
		expected_modified=expected_modified,
	)


@frappe.whitelist()
def execute_delivery_challan_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	return delivery_challan_service.execute_delivery_challan_command(
		name,
		command,
		payload,
		expected_modified,
	)


@frappe.whitelist()
def get_goods_received_note_workspace(name: str | None = None, source=None) -> dict:
	"""Load the focused routed/embedded Goods Received Note workspace."""

	return goods_received_note_service.get_goods_received_note_workspace(name, source)


@frappe.whitelist()
def preview_goods_received_note_source(source) -> dict:
	"""Refresh a new Goods Received Note from its authoritative source."""

	return goods_received_note_service.preview_goods_received_note_source(source)


@frappe.whitelist()
def save_goods_received_note(
	values,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	return goods_received_note_service.save_goods_received_note(
		values,
		name=name,
		submit=cint(submit),
		expected_modified=expected_modified,
	)


@frappe.whitelist()
def get_goods_received_note_calculation(name: str) -> dict:
	return goods_received_note_service.get_goods_received_note_calculation(name)


@frappe.whitelist()
def calculate_goods_received_note(
	name: str,
	rows,
	received_type: str,
	expected_modified: str | None = None,
) -> dict:
	return goods_received_note_service.calculate_goods_received_note(
		name,
		rows,
		received_type,
		expected_modified,
	)


@frappe.whitelist()
def save_goods_received_note_inspection(
	name: str,
	values,
	inspection_name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	return goods_received_note_service.save_goods_received_note_inspection(
		name,
		values,
		inspection_name=inspection_name,
		submit=cint(submit),
		expected_modified=expected_modified,
	)


@frappe.whitelist()
def execute_goods_received_note_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	return goods_received_note_service.execute_goods_received_note_command(
		name,
		command,
		payload,
		expected_modified,
	)


@frappe.whitelist()
def get_delivery_challan_return_editor(delivery_challan: str) -> dict:
	"""Return authoritative returnable DC rows for the nested web popup."""

	doc = _get_supported_document("YRP Delivery Challan", delivery_challan)
	frappe.has_permission("YRP Goods Received Note", ptype="create", throw=True)
	data = get_return_delivery_items(delivery_challan)
	return {
		"delivery_challan": delivery_challan,
		"items": data.get("items") or [],
		"has_received_type": bool(data.get("has_received_type")),
		"default_received_type": data.get("default_received_type"),
		"variants": delivery_challan_service._return_variants(doc),
		"permissions": {"can_create": True},
	}


@frappe.whitelist()
def create_delivery_challan_return(
	delivery_challan: str,
	items,
	received_type: str | None = None,
	return_whole_bundles: bool = False,
	cut_panel_movement: str | None = None,
) -> dict:
	"""Create a Draft Return GRN and return its popup projection."""

	doc = _get_supported_document("YRP Delivery Challan", delivery_challan)
	frappe.has_permission("YRP Goods Received Note", ptype="create", throw=True)
	items = items if isinstance(items, list) else frappe.parse_json(items or "[]")
	cut_panel_movement = delivery_challan_service._validate_return_variant(
		doc,
		return_whole_bundles=bool(cint(return_whole_bundles)),
		cut_panel_movement=cut_panel_movement,
	)
	if cut_panel_movement:
		name = create_return_grn(
			delivery_challan,
			items,
			received_type,
			cut_panel_movement,
		)
	else:
		name = create_return_grn(delivery_challan, items, received_type)
	return get_document("YRP Goods Received Note", name)


@frappe.whitelist()
def complete_work_order_document_transfer(doctype: str, name: str) -> dict:
	"""Create the native completion Stock Entry and return its popup projection."""

	if doctype not in {"YRP Delivery Challan", "YRP Goods Received Note"}:
		frappe.throw(_("Complete Transfer is not supported for {0}.").format(doctype))
	_get_supported_document(doctype, name)
	stock_entry = get_draft_completion_stock_entry(doctype, name)
	if not stock_entry and doctype == "YRP Delivery Challan":
		stock_entry = make_dc_completion(name)
	elif not stock_entry:
		stock_entry = make_grn_completion(name)
	return get_document("YRP Stock Entry", stock_entry)


@frappe.whitelist()
def discard_completion_draft(name: str, expected_modified: str | None = None) -> dict:
	"""Delete a draft DC or GRN completion Stock Entry so a fresh one can be prepared."""

	doc = _get_supported_document("YRP Stock Entry", name, "delete")
	if cint(doc.docstatus) != 0 or doc.get("purpose") not in FABRIC_STOCK_COMPLETION_PURPOSES:
		frappe.throw(_("Only draft completion Stock Entries can be discarded."))
	_assert_not_stale(doc, expected_modified)
	frappe.delete_doc("YRP Stock Entry", doc.name)
	return {"deleted": doc.name}


@frappe.whitelist()
def change_document_status(
	doctype: str,
	name: str,
	action: str,
	expected_modified: str | None = None,
) -> dict:
	"""Submit, cancel, or amend a supported document through its controller."""

	_require_supported_doctype(doctype)
	if action not in {"submit", "cancel", "amend"}:
		frappe.throw(_("Unsupported document action: {0}").format(action))
	doc = _get_supported_document(doctype, name)
	_assert_not_stale(doc, expected_modified)
	frappe.has_permission(doctype, ptype=action, doc=doc, throw=True)
	required_status = {"submit": 0, "cancel": 1, "amend": 2}[action]
	if cint(doc.docstatus) != required_status:
		frappe.throw(
			_("{0} cannot be {1} from its current state.").format(doc.name, action),
		)

	if action == "submit":
		doc.submit()
	elif action == "cancel":
		doc.cancel()
	else:
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.amended_from = doc.name
		amended.insert()
		name = amended.name

	return get_document(doctype, name)


@frappe.whitelist()
def get_work_order_workspace(work_order: str) -> dict:
	"""Load the complete routed Work Order workspace without business scoping."""

	return work_order_service.get_work_order_workspace(
		work_order,
		_adapter=sys.modules[__name__],
	)


@frappe.whitelist()
def get_work_order_editor(name: str | None = None, source=None) -> dict:
	return work_order_service.get_work_order_editor(
		name,
		source,
		_adapter=sys.modules[__name__],
	)


@frappe.whitelist()
def save_work_order_document(
	values,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	return work_order_service.save_work_order_document(
		values,
		name=name,
		submit=cint(submit),
		expected_modified=expected_modified,
		_adapter=sys.modules[__name__],
	)


@frappe.whitelist()
def execute_work_order_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	return work_order_service.execute_work_order_command(
		name,
		command,
		payload,
		expected_modified,
	)


@frappe.whitelist()
def get_capabilities() -> dict:
	"""Return the current user's unscoped Fabric Store UI capabilities.

	No warehouse, process, supplier, item, or department filter belongs here.
	Lists use Frappe's normal record permissions and user-selected filters only.
	"""

	sections = {}
	for key, doctype in DOCUMENT_KEYS.items():
		capability = _capability(doctype, SECTION_LABELS[key])
		if capability["can_read"]:
			sections[key] = capability

	operations = {}
	for key, doctype in STOCK_OPERATION_DOCTYPES.items():
		capability = _capability(doctype, OPERATION_LABELS[key])
		if capability["can_read"]:
			operations[key] = capability
	if operations:
		sections["stock_transfers"] = {
			"label": SECTION_LABELS["stock_transfers"],
			"operations": operations,
		}

	reports = {}
	if can_run_report("YRP Stock Balance"):
		reports["stock_balance"] = {"label": _("Stock Balance"), "can_read": True}

	if can_run_report("SD YRP Purchase Order Itemwise"):
		reports["purchase_order_itemwise"] = {
			"label": _("Purchase Order Itemwise"),
			"can_read": True,
		}

	if can_view_lot_cut_quantity():
		reports["lot_cut_quantity"] = {
			"label": _("Lot Cut Quantity"),
			"can_read": True,
			"can_read_cutting_plan": bool(
				frappe.has_permission("SD YRP Cutting Plan", ptype="read")
			),
		}

	if reports:
		sections["reports"] = {
			"label": SECTION_LABELS["reports"],
			"reports": reports,
		}

	return {
		"sections": sections,
		"related_documents": {
			key: {"doctype": doctype, **_permission_flags(doctype)}
			for key, doctype in RELATED_DOCUMENT_DOCTYPES.items()
		},
	}


def can_run_report(report_name: str) -> bool:
	"""Mirror query-report access checks without queueing permission errors."""
	try:
		report = frappe.get_doc("Report", report_name)
	except frappe.DoesNotExistError:
		return False
	return bool(
		not report.disabled
		and report.is_permitted()
		and frappe.has_permission(report.ref_doctype, ptype="read")
		and frappe.has_permission(report.ref_doctype, ptype="report")
	)
