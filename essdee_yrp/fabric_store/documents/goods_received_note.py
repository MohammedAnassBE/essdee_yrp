"""Goods Received Note coordination service for the Fabric Store workspace.

New ordinary receipts are derived from their live Work Order or Purchase Order.
Saved drafts are deliberately saved-document-first: browser quantities are
merged onto the rows already owned by the draft so Calculate results, Received
Type splits, correction rows, and Essdee special-mode rows are not discarded.
The DocType controllers remain responsible for pending limits, valuation,
freight allocation, stock ledger entries, and lifecycle side effects.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.party_addresses import get_party_address
from yrp.stock.api import get_stock_dimensions_for_ui
from yrp.stock.save_stock_items import (
	group_correction_items_for_ui,
	group_items_for_ui,
	ungroup_correction_items_from_ui,
	ungroup_items_from_ui,
)
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
	get_purchase_order_defaults,
	get_purchase_order_lot_fieldname,
	get_purchase_order_lot_options,
	make_grn_completion,
	validate_purchase_order_lot,
)
from yrp.yrp.doctype.yrp_supplier.yrp_supplier import get_primary_address

from essdee_yrp.additional_grn import get_defaults as get_additional_grn_defaults
from essdee_yrp.fabric_store.documents.common import (
	assert_expected_modified,
	get_allow_on_submit_fields,
	get_draft_completion_stock_entry,
	get_effective_fields,
	get_supplier_notification_capabilities,
	get_workspace_base,
	prepare_supplier_notification,
	send_supplier_notification,
)
from essdee_yrp.garment_grn import (
	calculate_grn_receivables,
	get_grn_calculation_context,
)
from essdee_yrp.overrides.goods_received_note import (
	_lock_versioned_cloth_lot,
	get_empty_draft_rows,
	get_work_order_defaults,
)
from essdee_yrp.overrides.inspection_entry import (
	get_initial_payload as get_inspection_initial_payload,
)

GOODS_RECEIVED_NOTE_FIELDS = (
	"naming_series",
	"against",
	"against_id",
	"delivery_challan",
	"is_return",
	"is_rework",
	"posting_date",
	"posting_time",
	"edit_posting_date_and_time",
	"process_name",
	"item",
	"production_detail",
	"supplier",
	"supplier_name",
	"delivery_location",
	"delivery_location_name",
	"billing_address",
	"billing_address_display",
	"from_warehouse",
	"to_warehouse",
	"supplier_document_no",
	"supplier_document_date",
	"vehicle_no",
	"comments",
	"freight_charges",
	"freight_charge_per_product",
	"purchase_invoice_name",
	"supplier_address",
	"supplier_address_display",
	"contact_person",
	"contact_display",
	"contact_mobile",
	"delivery_address",
	"delivery_address_display",
	"actual_date",
	"letter_head",
	"dc_no",
	"additional_grn",
	"allow_non_bundle",
	"includes_packing",
	"cutting_laysheet",
	"cut_panel_movement",
	"from_closed_wo_sewing_details",
	"from_finishing",
	"is_manual_entry",
	"is_pack",
	"avoid_sewing_plan_qty",
	"is_internal_unit",
	"transfer_complete",
	"ste_transferred",
	"ste_transferred_percent",
	"total_packing_boxes",
	"total_packing_pieces",
	"total_receivable_cost",
	"total_delivered_qty",
)

GOODS_RECEIVED_NOTE_EDITOR_FIELDS = (
	"posting_date",
	"posting_time",
	"edit_posting_date_and_time",
	"delivery_location",
	"from_warehouse",
	"to_warehouse",
	"supplier_document_no",
	"supplier_document_date",
	"vehicle_no",
	"comments",
	"freight_charges",
	"supplier_address",
	"contact_person",
	"delivery_address",
	"actual_date",
	"letter_head",
	"dc_no",
	"allow_non_bundle",
)

RETURN_LOCKED_FIELDS = {
	"delivery_challan",
	"delivery_location",
	"from_warehouse",
	"to_warehouse",
	"freight_charges",
}

GOODS_RECEIVED_NOTE_TOTALS = (
	"total_received_quantity",
	"total",
	"freight_charges",
	"total_tax",
	"grand_total",
	"total_receivable_cost",
	"total_delivered_qty",
)

GOODS_RECEIVED_NOTE_RECORD_FIELDS = (
	"against",
	"against_id",
	"delivery_challan",
	"is_return",
	"is_rework",
	"process_name",
	"item",
	"production_detail",
	"supplier",
	"supplier_name",
	"delivery_location",
	"from_warehouse",
	"to_warehouse",
	"additional_grn",
	"allow_non_bundle",
	"includes_packing",
	"cutting_laysheet",
	"cut_panel_movement",
	"from_closed_wo_sewing_details",
	"from_finishing",
	"is_internal_unit",
	"transfer_complete",
	"ste_transferred",
	"ste_transferred_percent",
)

SPECIAL_SOURCE_FIELDS = (
	"is_return",
	"is_rework",
	"additional_grn",
	"includes_packing",
	"cutting_laysheet",
	"cut_panel_movement",
	"from_closed_wo_sewing_details",
	"from_finishing",
)

INSPECTION_FIELDS = (
	"against",
	"against_id",
	"posting_date",
	"posting_time",
	"inspector",
	"status",
	"is_converted",
	"remarks",
	"amended_from",
)


def _as_mapping(value) -> dict:
	if value in (None, ""):
		return {}
	if isinstance(value, Mapping):
		return dict(value)
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, Mapping):
		frappe.throw(_("Expected an object payload."))
	return dict(parsed)


def _as_list(value) -> list:
	if value in (None, ""):
		return []
	if isinstance(value, list):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, list):
		frappe.throw(_("Expected a list payload."))
	return parsed


def _row_dict(row) -> dict:
	as_dict = getattr(row, "as_dict", None)
	return as_dict() if callable(as_dict) else dict(row)


def _get_grn(name: str, permission: str = "read"):
	doc = frappe.get_doc("YRP Goods Received Note", name)
	doc.check_permission(permission)
	return doc


def _target_permission(doctype: str, ptype: str = "create") -> bool:
	return bool(frappe.has_permission(doctype, ptype=ptype))


def _permission_error(message: str):
	frappe.throw(message, frappe.PermissionError)


def _special_source_context(doc_or_values) -> dict:
	modes = [
		fieldname
		for fieldname in SPECIAL_SOURCE_FIELDS
		if doc_or_values.get(fieldname) not in (None, "", 0, False)
	]
	# An Additional GRN keeps editable receipt rows, like production_api.
	read_only = any(mode != "additional_grn" for mode in modes)
	return {"active": bool(modes), "modes": modes, "read_only": read_only}


def _is_additional_grn_source(values: Mapping) -> bool:
	is_work_order = values.get("work_order") or values.get("against") == "YRP Work Order"
	return bool(is_work_order and cint(values.get("additional_grn")) and not cint(values.get("is_return")))


def _calculate_eligible(doc) -> bool:
	return bool(
		doc.name
		and cint(doc.docstatus) == 0
		and doc.get("against") == "YRP Work Order"
		and doc.get("against_id")
		and not any(doc.get(fieldname) for fieldname in SPECIAL_SOURCE_FIELDS if fieldname != "additional_grn")
	)


def _inspectable(doc) -> bool:
	return bool(
		cint(doc.docstatus) == 1
		and not doc.get("is_return")
		and not doc.get("is_rework")
	)


def _onload_matrices(doc) -> tuple[list, list]:
	doc.run_method("onload")
	get_onload = getattr(doc, "get_onload", None)
	onload = get_onload() if callable(get_onload) else (doc.get("__onload") or {})
	items = onload.get("item_details") or []
	corrections = onload.get("correction_item_details") or []
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if isinstance(corrections, str):
		corrections = frappe.parse_json(corrections)
	if not items and doc.get("items"):
		items = group_items_for_ui(doc.get("items") or [], "YRP Goods Received Note")
	if not corrections and doc.get("correction_items"):
		corrections = group_correction_items_for_ui(
			doc.get("correction_items") or [], "YRP Goods Received Note"
		)
	if _actual_dia_context(doc).get("enabled"):
		_add_actual_dia_row_identity(items, doc.get("items") or [])
	return items or [], corrections or []


def _matrix_cells(groups):
	for group in groups or []:
		for entry in group.get("items") or []:
			values = entry.get("values") or {}
			primary = entry.get("primary_attribute") if "default" not in values else None
			cells = values.items() if primary and values else [("default", values.get("default") or {})]
			for key, value in cells:
				attributes = dict(entry.get("attributes") or {})
				if primary:
					attributes[primary] = key
				yield entry, value, attributes


def _add_actual_dia_row_identity(groups, saved_rows):
	"""Attach saved child identity to cells, independent of display row indexes."""
	from essdee_yrp.fabric_grn import _variant_attrs

	dimensions = _dimension_fieldnames()
	attrs = {}
	planned = {}
	for entry, value, attributes in _matrix_cells(groups):
		browser = {**entry, **(entry.get("dimensions") or {}), **value}
		matches = []
		for saved in saved_rows:
			candidate = {**browser, "item_variant": saved.get("item_variant")}
			if _business_key(saved, dimensions, include_received_type=True) != _business_key(
				candidate, dimensions, include_received_type=True
			):
				continue
			variant = saved.get("item_variant")
			if variant not in attrs:
				attrs[variant] = _variant_attrs(variant)
			if all(attrs[variant].get(key, "") == (val or "") for key, val in attributes.items()):
				matches.append(saved)
		if len(matches) == 1:
			saved = matches[0]
			value["grn_item_name"] = saved.get("name")
			value["original_item_variant"] = saved.get("item_variant")
			reference = saved.get("ref_docname")
			if reference not in planned:
				planned[reference] = frappe.db.get_value("YRP Work Order Receivables", reference, "item_variant")
			value["is_saved_actual_dia"] = bool(
				planned[reference] and saved.get("item_variant") != planned[reference]
			)


def _dimension_projection(doc) -> list[dict]:
	projected = []
	for source in get_stock_dimensions_for_ui():
		dimension = dict(source)
		dimension["fieldtype"] = "Link" if dimension.get("options") else "Data"
		dimension["reqd"] = bool(dimension.get("mandatory"))
		dimension["value"] = doc.get(dimension["fieldname"])
		# GRN dimensions belong to authoritative matrix rows. Advertising a
		# parent-level edit would either be ignored or retarget stock lineage.
		dimension["locked"] = True
		projected.append(dimension)
	return projected


def _purchase_order_lot_context(doc) -> dict:
	if doc.get("against") != "Purchase Order" or not doc.get("against_id") or doc.get("is_return"):
		return {}
	po = frappe.get_doc("Purchase Order", doc.against_id)
	return {
		"lot_options": get_purchase_order_lot_options(po),
		"lot_fieldname": get_purchase_order_lot_fieldname(),
		"purchase_order": po.name,
	}


def _related_documents(doc) -> dict:
	related = {"inspection_entries": [], "completion_entries": []}
	if frappe.has_permission("YRP Inspection Entry", ptype="read"):
		related["inspection_entries"] = [
			dict(row)
			for row in frappe.get_list(
				"YRP Inspection Entry",
				filters={"against": "YRP Goods Received Note", "against_id": doc.name},
				fields=[
					"name",
					"docstatus",
					"posting_date",
					"inspector",
					"status",
					"is_converted",
					"modified",
				],
				order_by="modified desc",
				limit=500,
			)
		]
	if frappe.has_permission("YRP Stock Entry", ptype="read"):
		related["completion_entries"] = [
			dict(row)
			for row in frappe.get_list(
				"YRP Stock Entry",
				filters={
					"against": "YRP Goods Received Note",
					"against_id": doc.name,
					"purpose": "GRN Completion",
				},
				fields=["name", "docstatus", "posting_date", "modified"],
				order_by="modified desc",
				limit=500,
			)
		]
	return related


def _inspection_context(doc, related: Mapping) -> dict:
	context = {
		"initial_payload": [],
		"entries": list(related.get("inspection_entries") or []),
		"reason": "",
		"can_create": False,
		"can_submit": False,
	}
	if not _inspectable(doc) or not _target_permission("YRP Inspection Entry"):
		return context
	try:
		context["initial_payload"] = get_inspection_initial_payload(
			"YRP Goods Received Note", doc.name
		) or []
		context["can_create"] = True
		context["can_submit"] = _target_permission("YRP Inspection Entry", "submit")
	except (frappe.ValidationError, frappe.PermissionError) as error:
		context["reason"] = str(error)
	return context


def _capability_candidates(doc, related: Mapping, inspection: Mapping) -> dict[str, dict]:
	docstatus = cint(doc.docstatus)
	can_complete = bool(
		docstatus == 1
		and doc.get("is_internal_unit")
		and not doc.get("transfer_complete")
		and _target_permission("YRP Stock Entry")
	)
	notifications = get_supplier_notification_capabilities(
		doc,
		"YRP Goods Received Note",
	)
	return {
		"save": {"label": _("Edit"), "permission": "write", "eligible": docstatus == 0},
		"submit": {"label": _("Submit"), "permission": "submit", "eligible": docstatus == 0},
		"cancel": {"label": _("Cancel"), "permission": "cancel", "eligible": docstatus == 1},
		"amend": {"label": _("Amend"), "permission": "amend", "eligible": docstatus == 2},
		"calculate": {
			"label": _("Calculate"),
			"permission": "write",
			"eligible": _calculate_eligible(doc),
		},
		"create_inspection": {
			"label": _("Create Inspection Entry"),
			"eligible": bool(inspection.get("can_create")),
		},
		"view_inspections": {
			"label": _("View Inspection Entries"),
			"eligible": bool(related.get("inspection_entries")),
		},
		"complete_transfer": {"label": _("Complete Transfer"), "eligible": can_complete},
		"prepare_sms": {"label": _("Send SMS"), "eligible": notifications["sms"]},
		"prepare_whatsapp": {
			"label": _("Send WhatsApp"),
			"eligible": notifications["whatsapp"],
		},
	}


def _document_values(doc, readable_fields: set[str]) -> dict:
	return {
		fieldname: doc.get(fieldname)
		for fieldname in GOODS_RECEIVED_NOTE_FIELDS
		if fieldname in readable_fields
	}


def get_goods_received_note_workspace(name: str | None = None, source=None) -> dict:
	"""Return an existing GRN workspace or a new source-derived editor."""

	if not name:
		source_values = _as_mapping(source)
		if source_values.get("duplicate_from"):
			frappe.has_permission("YRP Goods Received Note", ptype="create", throw=True)
			original = _get_grn(source_values["duplicate_from"])
			if _special_source_context(original)["active"]:
				frappe.throw(
					_("This source-managed Goods Received Note cannot be duplicated. Create it from its originating workflow instead.")
				)
			item_matrix, correction_matrix = _onload_matrices(original)
			doc = frappe.new_doc("YRP Goods Received Note")
			doc.update({fieldname: original.get(fieldname) for fieldname in GOODS_RECEIVED_NOTE_FIELDS})
			doc.against = original.get("against")
			doc.against_id = original.get("against_id")
			doc.delivery_challan = original.get("delivery_challan")
			defaults = {
				"item_details": item_matrix,
				"correction_item_details": correction_matrix,
				**_purchase_order_lot_context(original),
			}
			return _new_workspace(
				doc,
				defaults,
				bool(frappe.has_permission("YRP Goods Received Note", ptype="submit")),
			)
		return preview_goods_received_note_source(source)

	doc = _get_grn(name)
	item_matrix, correction_matrix = _onload_matrices(doc)
	related = _related_documents(doc)
	inspection = _inspection_context(doc, related)
	workspace = get_workspace_base(
		doc,
		fieldnames=GOODS_RECEIVED_NOTE_FIELDS,
		totals=GOODS_RECEIVED_NOTE_TOTALS,
		capabilities=_capability_candidates(doc, related, inspection),
	)
	for field in workspace["fields"]:
		if field["fieldname"] in {"against", "against_id", "delivery_challan"}:
			field["read_only"] = True
	readable_fields = {field["fieldname"] for field in workspace["fields"]}
	workspace["record"].update(
		{
			fieldname: doc.get(fieldname)
			for fieldname in GOODS_RECEIVED_NOTE_RECORD_FIELDS
			if fieldname in readable_fields
		}
	)
	workspace["record"]["cut_panel_movement"] = doc.get("cut_panel_movement")
	workspace.update(
		{
			"values": _document_values(doc, readable_fields),
			"matrices": {
				"items": item_matrix,
				"correction_items": correction_matrix,
			},
			"dimensions": _dimension_projection(doc),
			**_purchase_order_lot_context(doc),
			"actual_dia": _actual_dia_context(doc),
			"special_source": _special_source_context(doc),
			"inspection": inspection,
			"related": related,
			# Compatibility keys used by the common popup shell.
			"item_groups": item_matrix,
			"correction_item_groups": correction_matrix,
			"details": workspace["fields"],
		}
	)
	return workspace


def _actual_dia_context(doc):
	from essdee_yrp.fabric_grn import get_actual_dia_context

	if cint(doc.get("docstatus")) or doc.get("against") != "YRP Work Order":
		return {"enabled": False, "dia_options": []}
	if _special_source_context(doc)["active"]:
		return {"enabled": False, "dia_options": []}
	return get_actual_dia_context(doc.get("against_id"))


def _resolve_source(source) -> tuple[dict, str, str, str | None]:
	values = _as_mapping(source)
	against = values.get("against")
	against_id = values.get("against_id")
	if values.get("work_order"):
		against, against_id = "YRP Work Order", values["work_order"]
	elif values.get("purchase_order"):
		against, against_id = "Purchase Order", values["purchase_order"]
	if against not in {"YRP Work Order", "Purchase Order"} or not against_id:
		frappe.throw(_("Select a Work Order or Purchase Order for the Goods Received Note."))
	delivery_challan = values.get("delivery_challan") if against == "YRP Work Order" else None
	if _is_additional_grn_source(values):
		# Additional receipts list every Work Order receivable, not one challan's rows.
		delivery_challan = None
	return values, against, against_id, delivery_challan


def _source_defaults(
	against: str,
	against_id: str,
	delivery_challan: str | None = None,
	additional_grn: bool = False,
) -> dict:
	if additional_grn:
		defaults = get_additional_grn_defaults(against_id)
		defaults["additional_grn"] = 1
	elif against == "YRP Work Order":
		defaults = get_work_order_defaults(against_id, delivery_challan)
	else:
		defaults = get_purchase_order_defaults(against_id)
		if not defaults.get("delivery_location") and defaults.get("to_warehouse"):
			defaults["delivery_location"] = frappe.db.get_value("Warehouse", defaults["to_warehouse"], "supplier")
	if not defaults.get("delivery_address"):
		defaults["delivery_address"] = get_delivery_address(
			defaults.get("delivery_location"), against_id if against == "Purchase Order" else None
		)
	if not defaults.get("supplier_address"):
		defaults["supplier_address"] = get_supplier_address(
			defaults.get("supplier"), against_id if against == "Purchase Order" else None
		)
	return defaults


@frappe.whitelist()
def get_delivery_address(delivery_location=None, purchase_order=None) -> str:
	frappe.has_permission("YRP Goods Received Note", ptype="read", throw=True)
	address = get_party_address(delivery_location, preferred_type="Shipping")
	if address or not purchase_order:
		return address or ""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	return get_primary_address(po.get("default_delivery_location")) or ""


@frappe.whitelist()
def get_supplier_address(supplier=None, purchase_order=None) -> str:
	frappe.has_permission("YRP Goods Received Note", ptype="read", throw=True)
	address = get_party_address(supplier, preferred_type="Billing")
	if address or not purchase_order:
		return address or ""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	return po.get("supplier_address") or ""


def _source_values(defaults: Mapping, browser_values: Mapping | None = None) -> dict:
	values = {
		key: value
		for key, value in defaults.items()
		if key
		not in {
			"items",
			"item_details",
			"correction_items",
			"correction_item_details",
			"lot_options",
			"lot_fieldname",
		}
	}
	for fieldname in GOODS_RECEIVED_NOTE_EDITOR_FIELDS:
		if browser_values and fieldname in browser_values:
			values[fieldname] = browser_values[fieldname]
	return values


def _new_workspace(doc, defaults: Mapping, can_submit: bool) -> dict:
	fields = get_effective_fields(doc, GOODS_RECEIVED_NOTE_FIELDS)
	for field in fields:
		if field["fieldname"] in {"against", "against_id", "delivery_challan"}:
			field["read_only"] = True
	readable_fields = {field["fieldname"] for field in fields}
	permissions = {
		"can_read": True,
		"can_create": True,
		"can_write": False,
		"can_submit": can_submit,
		"can_cancel": False,
		"can_amend": False,
		"can_print": False,
	}
	totals = []
	for fieldname in GOODS_RECEIVED_NOTE_TOTALS:
		field = doc.meta.get_field(fieldname)
		totals.append(
			{
				"fieldname": fieldname,
				"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
				"value": doc.get(fieldname),
			}
		)
	item_matrix = defaults.get("item_details") or []
	correction_matrix = defaults.get("correction_item_details") or []
	workspace = {
		"record": {
			"doctype": "YRP Goods Received Note",
			"name": None,
			"docstatus": 0,
			"status": _("Draft"),
			"modified": None,
			**{
				fieldname: doc.get(fieldname)
				for fieldname in GOODS_RECEIVED_NOTE_RECORD_FIELDS
				if fieldname in readable_fields
			},
		},
		"fields": fields,
		"totals": totals,
		"permissions": permissions,
		"capabilities": {
			"save": {"label": _("Save")},
			**({"submit": {"label": _("Submit")}} if can_submit else {}),
		},
		"print_formats": [],
		"values": _document_values(doc, readable_fields),
		"matrices": {"items": item_matrix, "correction_items": correction_matrix},
		"dimensions": _dimension_projection(doc),
		"lot_options": defaults.get("lot_options") or {},
		"lot_fieldname": defaults.get("lot_fieldname"),
		"actual_dia": _actual_dia_context(doc),
		"special_source": _special_source_context(doc),
		"inspection": {"initial_payload": [], "entries": [], "reason": "", "can_create": False},
		"related": {},
		"item_groups": item_matrix,
		"correction_item_groups": correction_matrix,
	}
	workspace["details"] = workspace["fields"]
	return workspace


def preview_goods_received_note_source(source) -> dict:
	"""Build a new GRN editor exclusively from authoritative source defaults."""

	frappe.has_permission("YRP Goods Received Note", ptype="create", throw=True)
	values, against, against_id, delivery_challan = _resolve_source(source)
	defaults = _source_defaults(
		against, against_id, delivery_challan, _is_additional_grn_source(values)
	)
	doc = frappe.new_doc("YRP Goods Received Note")
	doc.update(_source_values(defaults, values))
	doc.against = against
	doc.against_id = against_id
	if delivery_challan:
		doc.delivery_challan = delivery_challan
	doc.set("items", defaults.get("items") or [])
	doc.set("correction_items", defaults.get("correction_items") or [])
	return _new_workspace(
		doc,
		defaults,
		bool(frappe.has_permission("YRP Goods Received Note", ptype="submit")),
	)


def _stable_row_index(value, received_type=None):
	if value in (None, ""):
		return ""
	text = str(value).strip()
	if received_type and text.endswith(f"::{received_type}"):
		text = text[: -(len(str(received_type)) + 2)]
	return int(text) if text.lstrip("-").isdigit() else text


def _canonical_json(value) -> str:
	if value in (None, ""):
		return ""
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			return value
	return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _dimension_fieldnames() -> tuple[str, ...]:
	return tuple(
		dimension.get("fieldname")
		for dimension in get_stock_dimensions_for_ui()
		if dimension.get("fieldname")
	)


def _lineage_key(row, dimensions: tuple[str, ...]) -> tuple:
	received_type = row.get("received_type") or ""
	return (
		row.get("item_variant"),
		row.get("ref_doctype") or "",
		row.get("ref_docname") or "",
		row.get("delivery_challan_item") or "",
		row.get("work_order_correction") or "",
		_stable_row_index(row.get("row_index"), received_type),
		_canonical_json(row.get("set_combination")),
		tuple(
			(fieldname, row.get(fieldname) or "")
			for fieldname in dimensions
			if fieldname != "received_type"
		),
	)


def _row_key(row, dimensions: tuple[str, ...]) -> tuple:
	return (
		_lineage_key(row, dimensions),
		row.get("received_type") or "",
	)


def _business_key(row, dimensions: tuple[str, ...], *, include_received_type: bool) -> tuple:
	"""Return the source identity that survives matrix group/ungroup.

	The shared stock editor intentionally renumbers ``row_index`` when it
	flattens grouped rows. References and stock dimensions are stable, so they
	are the safe fallback when the saved index and browser index differ.
	"""

	key = (
		row.get("item_variant"),
		row.get("ref_doctype") or "",
		row.get("ref_docname") or "",
		row.get("delivery_challan_item") or "",
		row.get("work_order_correction") or "",
		_canonical_json(row.get("set_combination")),
		tuple(
			(fieldname, row.get(fieldname) or "")
			for fieldname in dimensions
			if fieldname != "received_type"
		),
	)
	return (*key, row.get("received_type") or "") if include_received_type else key


def _number(value, label: str) -> float:
	try:
		value = float(value or 0)
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be a number.").format(label))
	if value < 0:
		frappe.throw(_("{0} cannot be negative.").format(label))
	return value


def _copy_operator_values(source: Mapping, browser: Mapping) -> dict:
	row = _row_dict(source)
	row["quantity"] = _number(browser.get("quantity"), _("Item quantity"))
	if "comments" in browser:
		row["comments"] = browser.get("comments") or ""
	if "secondary_qty" in browser:
		row["secondary_qty"] = _number(browser.get("secondary_qty"), _("Secondary quantity"))
	if "freight_amount" in browser:
		row["freight_amount"] = _number(browser.get("freight_amount"), _("Freight amount"))
	return row


def _row_index_for_received_type(source: Mapping, received_type: str) -> object:
	row_index = source.get("row_index")
	if row_index in (None, ""):
		return row_index
	base = str(_stable_row_index(row_index, source.get("received_type")))
	return f"{base}::{received_type}" if received_type else base


def _merge_purchase_order_rows(authoritative, browser_rows, lot_options, lot_fieldname, purchase_order):
	"""Clone trusted PO siblings with operator-selected lot and received type."""
	dimensions = _dimension_fieldnames()
	lineage_dimensions = tuple(fieldname for fieldname in dimensions if fieldname != lot_fieldname)
	lineages = defaultdict(list)
	for row in authoritative or []:
		lineages[_business_key(row, lineage_dimensions, include_received_type=False)].append(row)
	browser_lineages = {
		_business_key(row, lineage_dimensions, include_received_type=False) for row in browser_rows or []
	}
	# Omitted source lineages retain their rows; submitted lineages replace all prior splits.
	rows = [
		_row_dict(row)
		for row in authoritative or []
		if _business_key(row, lineage_dimensions, include_received_type=False) not in browser_lineages
		and flt(row.get("quantity")) > 0
	]
	seen = set()
	for index, browser in enumerate(browser_rows or [], 1):
		if flt(browser.get("quantity")) <= 0 and flt(browser.get("secondary_qty")) <= 0:
			continue
		key = _business_key(browser, dimensions, include_received_type=True)
		if key in seen:
			frappe.throw(_("The item matrix contains a duplicate lot / Received Type row."))
		siblings = lineages.get(_business_key(browser, lineage_dimensions, include_received_type=False))
		if not siblings:
			frappe.throw(
				_("The available item rows changed. Refresh the editor and enter the quantities again.")
			)
		clone = _clone_purchase_order_split(siblings, browser, lot_fieldname)
		validate_purchase_order_lot(clone, lot_fieldname, lot_options, purchase_order, index)
		rows.append(clone)
		seen.add(key)
	return rows


def _clone_purchase_order_split(siblings, browser, fieldname):
	split_key = (browser.get(fieldname), browser.get("received_type") or "")
	source = next(
		(row for row in siblings if (row.get(fieldname), row.get("received_type") or "") == split_key),
		siblings[0],
	)
	received_type = browser.get("received_type") or ""
	if received_type != (source.get("received_type") or ""):
		if not received_type or not frappe.db.exists("YRP Received Type", received_type):
			frappe.throw(_("Select a valid Received Type."))
	clone = _copy_operator_values(source, browser)
	if (source.get(fieldname), source.get("received_type") or "") != split_key:
		clone.pop("name", None)
	if fieldname:
		clone[fieldname] = browser.get(fieldname)
	clone["received_type"] = received_type
	# Lots already separate matrix entries by dimension. Keep the trusted
	# logical index for existing splits and new lots of the same received type.
	if received_type != (source.get("received_type") or ""):
		clone["row_index"] = _row_index_for_received_type(source, received_type)
	return clone


def _merge_authoritative_rows(
	authoritative,
	browser_rows,
	*,
	lot_options=None,
	lot_fieldname=None,
	purchase_order=None,
	actual_dia_context=None,
) -> list[dict]:
	"""Merge operator values onto trusted receipt rows."""

	if actual_dia_context and actual_dia_context.get("enabled"):
		return _merge_actual_dia_rows(authoritative, browser_rows)
	if lot_options is not None:
		return _merge_purchase_order_rows(
			authoritative, browser_rows, lot_options, lot_fieldname, purchase_order
		)
	return _merge_received_type_rows(authoritative, browser_rows)


def _merge_received_type_rows(authoritative, browser_rows):
	"""Allow received-type splits while retaining source dimensions."""
	dimensions = _dimension_fieldnames()
	authoritative = [_row_dict(row) for row in authoritative or []]
	exact = defaultdict(list)
	business = defaultdict(list)
	lineages = defaultdict(list)
	for index, row in enumerate(authoritative):
		exact[_row_key(row, dimensions)].append(index)
		business[_business_key(row, dimensions, include_received_type=True)].append(index)
		lineages[_business_key(row, dimensions, include_received_type=False)].append(index)

	updates = {}
	additions = []
	addition_keys = set()
	for source in browser_rows or []:
		browser = _row_dict(source)
		full_candidates = exact.get(_row_key(browser, dimensions)) or []
		stable_candidates = business.get(
			_business_key(browser, dimensions, include_received_type=True)
		) or []
		candidates = [index for index in full_candidates if index not in updates]
		if not candidates:
			candidates = [index for index in stable_candidates if index not in updates]
		if len(candidates) == 1:
			updates[candidates[0]] = browser
			continue
		if len(candidates) > 1:
			frappe.throw(_("The item matrix matches more than one source row."))
		if full_candidates or stable_candidates:
			frappe.throw(_("The item matrix contains a duplicate source row."))
		# Grouped matrices pad missing primary-attribute values with zero cells.
		# They have no source lineage because they are display placeholders, not
		# browser-created stock rows.
		if flt(browser.get("quantity")) <= 0 and flt(browser.get("secondary_qty")) <= 0:
			continue

		lineage_key = _business_key(browser, dimensions, include_received_type=False)
		lineage_candidates = lineages.get(lineage_key) or []
		if not lineage_candidates:
			frappe.throw(
				_("The available item rows changed. Refresh the editor and enter the quantities again.")
			)
		received_type = browser.get("received_type") or ""
		if not received_type or not frappe.db.exists("YRP Received Type", received_type):
			frappe.throw(_("Select a valid Received Type."))
		new_key = (*lineage_key, received_type)
		if new_key in addition_keys:
			frappe.throw(_("The item matrix contains a duplicate Received Type row."))
		clone = _copy_operator_values(authoritative[lineage_candidates[0]], browser)
		clone.pop("name", None)
		clone["received_type"] = received_type
		clone["row_index"] = _row_index_for_received_type(
			authoritative[lineage_candidates[0]], received_type
		)
		additions.append(clone)
		addition_keys.add(new_key)

	merged = []
	for index, source in enumerate(authoritative):
		browser = updates.get(index)
		row = _copy_operator_values(source, browser) if browser is not None else source
		if flt(row.get("quantity")) > 0:
			merged.append(row)
	merged.extend(row for row in additions if flt(row.get("quantity")) > 0)
	return merged


def _merge_actual_dia_rows(authoritative, browser_rows):
	"""Replace identified saved rows; omitted and zero-quantity rows are deleted."""
	from essdee_yrp.fabric_grn import validate_actual_dia_variant

	dimensions = _dimension_fieldnames()
	rows = [_row_dict(row) for row in authoritative or []]
	by_name = {row["name"]: row for row in rows if row.get("name")}
	# Reserve saved identities before fallback matching, regardless of browser order.
	identified_names = {
		browser.get("grn_item_name") or browser.get("name")
		for browser in browser_rows or []
		if browser.get("grn_item_name") or browser.get("name")
	}
	used = set()
	merged = []
	next_index = max((cint(row.get("row_index")) for row in rows), default=-1) + 1
	for index, browser in enumerate(browser_rows or [], 1):
		identity = browser.get("grn_item_name") or browser.get("name")
		matches = []
		if identity:
			source = by_name.get(identity)
			if source is None or not _is_actual_dia_lineage(source, browser, dimensions):
				frappe.throw(_("The saved item row changed. Refresh the editor and try again."))
		else:
			original = browser.get("original_item_variant") or browser.get("item_variant")
			candidate = {**browser, "item_variant": original}
			key = _business_key(candidate, dimensions, include_received_type=True)
			matches = [
				row for row in rows
				if row.get("name") not in identified_names
				and _business_key(row, dimensions, include_received_type=True) == key
			]
			if len(matches) > 1:
				frappe.throw(_("The item matrix matches more than one source row."))
			source = matches[0] if matches else None
		if source is not None:
			identity_key = id(source)
			if identity_key in used:
				frappe.throw(_("The item matrix contains a duplicate source row."))
			used.add(identity_key)
		else:
			if browser.get("grn_item_name") or browser.get("original_item_variant"):
				frappe.throw(_("The saved item row changed. Refresh the editor and try again."))
			source = next((row for row in rows if _is_actual_dia_lineage(row, browser, dimensions)), None)
		if source is None:
			if flt(browser.get("quantity")) <= 0 and flt(browser.get("secondary_qty")) <= 0:
				continue
			frappe.throw(_("The available item rows changed. Refresh the editor and enter the quantities again."))
		# Validate edits even on zero rows, before merging can discard their attributes.
		if source.get("item_variant") != browser.get("item_variant"):
			validate_actual_dia_variant(source["item_variant"], browser["item_variant"], index)
		clone = _copy_operator_values(source, browser)
		clone["item_variant"] = browser["item_variant"]
		received_type = browser.get("received_type") or ""
		if received_type != (source.get("received_type") or ""):
			if not received_type or not frappe.db.exists("YRP Received Type", received_type):
				frappe.throw(_("Select a valid Received Type."))
			clone["received_type"] = received_type
			clone["row_index"] = _row_index_for_received_type(source, received_type)
			clone.pop("name", None)
		if not identity and not matches:
			clone.pop("name", None)
			clone["row_index"] = next_index
			next_index += 1
		if flt(clone.get("quantity")) <= 0:
			continue
		merged.append(clone)
	return merged


def _is_actual_dia_lineage(source, browser, dimensions):
	if not browser.get("ref_docname"):
		return False
	candidate = {**browser, "item_variant": source.get("item_variant")}
	return _business_key(source, dimensions, include_received_type=False) == _business_key(
		candidate, dimensions, include_received_type=False
	)


def _browser_rows(values: Mapping, *, corrections: bool, fallback_rows) -> tuple[list, bool]:
	keys = (
		("correction_item_details", "correction_item_groups")
		if corrections
		else ("item_details", "item_groups")
	)
	matrix_key = next((key for key in keys if key in values), None)
	if matrix_key is None:
		return [_row_dict(row) for row in fallback_rows or []], False
	if corrections:
		return (
			ungroup_correction_items_from_ui(
				values.get(matrix_key) or [],
				"YRP Goods Received Note",
				keep_zero=True,
			),
			True,
		)
	groups = _as_list(values.get(matrix_key))
	rows = ungroup_items_from_ui(groups, "YRP Goods Received Note", keep_zero=True)
	# The shared ungroup helper intentionally copies only DocType fields. Keep
	# workspace-only identity beside its cells using the same traversal order.
	for row, (_entry, cell, _attributes) in zip(rows, _matrix_cells(groups), strict=False):
		for field in ("grn_item_name", "original_item_variant"):
			if cell.get(field):
				row[field] = cell[field]
	return rows, True


def _editable_headers(doc, values: Mapping) -> dict:
	fieldnames = GOODS_RECEIVED_NOTE_EDITOR_FIELDS
	if doc.get("is_return"):
		fieldnames = tuple(fieldname for fieldname in fieldnames if fieldname not in RETURN_LOCKED_FIELDS)
	if doc.get("cut_panel_movement"):
		# The Cut Panel Movement decides exact or collapsed bundle handling.
		fieldnames = tuple(fieldname for fieldname in fieldnames if fieldname != "allow_non_bundle")
	return {fieldname: values[fieldname] for fieldname in fieldnames if fieldname in values}


def save_goods_received_note(
	values,
	*,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	"""Save a GRN while retaining controller/source-owned row metadata."""

	values = _as_mapping(values)
	submitted_update = False
	allow_on_submit_fields = set()
	if name:
		doc = _get_grn(name, "write")
		assert_expected_modified(doc, expected_modified)
		docstatus = cint(doc.docstatus)
		if docstatus == 1:
			if cint(submit):
				frappe.throw(_("A submitted Goods Received Note cannot be submitted again."))
			submitted_update = True
			allow_on_submit_fields = set(get_allow_on_submit_fields(doc))
			allowed_payload_fields = {
				fieldname
				for fieldname in GOODS_RECEIVED_NOTE_EDITOR_FIELDS
				if fieldname in allow_on_submit_fields
			}
			if "items" in allow_on_submit_fields:
				allowed_payload_fields.update({"item_details", "item_groups"})
			if "correction_items" in allow_on_submit_fields:
				allowed_payload_fields.update(
					{"correction_item_details", "correction_item_groups"}
				)
			denied = set(values) - allowed_payload_fields
			if denied:
				frappe.throw(
					_("Only Allow on Submit fields can be changed after submission: {0}.").format(
						", ".join(sorted(denied))
					)
				)
		elif docstatus != 0:
			frappe.throw(_("Only Draft Goods Received Notes can be edited."))
		if not submitted_update and (
			"delivery_challan" in values
			and (values.get("delivery_challan") or "") != (doc.get("delivery_challan") or "")
		):
			frappe.throw(
				_("Delivery Challan cannot be changed after a Goods Received Note is saved.")
			)
		authoritative_items = [_row_dict(row) for row in (doc.get("items") or [])]
		authoritative_corrections = [
			_row_dict(row) for row in (doc.get("correction_items") or [])
		]
		# A draft saved without quantities merges onto the rows a new GRN would offer.
		matrix_source_items = authoritative_items or [
			_row_dict(row) for row in (get_empty_draft_rows(doc) or [])
		]
	else:
		frappe.has_permission("YRP Goods Received Note", ptype="create", throw=True)
		_source, against, against_id, delivery_challan = _resolve_source(values)
		defaults = _source_defaults(
			against, against_id, delivery_challan, _is_additional_grn_source(values)
		)
		doc = frappe.new_doc("YRP Goods Received Note")
		doc.update(_source_values(defaults))
		doc.against = against
		doc.against_id = against_id
		if delivery_challan:
			doc.delivery_challan = delivery_challan
		authoritative_items = [_row_dict(row) for row in (defaults.get("items") or [])]
		authoritative_corrections = [
			_row_dict(row) for row in (defaults.get("correction_items") or [])
		]
		matrix_source_items = authoritative_items

	if submitted_update:
		doc.update(
			{
				fieldname: values[fieldname]
				for fieldname in GOODS_RECEIVED_NOTE_EDITOR_FIELDS
				if fieldname in allow_on_submit_fields and fieldname in values
			}
		)
	else:
		doc.update(_editable_headers(doc, values))
	if _special_source_context(doc)["read_only"]:
		# Prepared return/packing/cutting rows belong to their native
		# builders and must not be reconstructed from a generic browser matrix.
		items = authoritative_items
		corrections = authoritative_corrections
	else:
		browser_items, has_item_matrix = _browser_rows(
			values, corrections=False, fallback_rows=authoritative_items
		)
		browser_corrections, has_correction_matrix = _browser_rows(
			values, corrections=True, fallback_rows=authoritative_corrections
		)
		items = (
			_merge_authoritative_rows(
				matrix_source_items,
				browser_items,
				actual_dia_context=_actual_dia_context(doc),
				**(_purchase_order_lot_context(doc) if cint(doc.docstatus) == 0 else {}),
			)
			if has_item_matrix
			else authoritative_items
		)
		corrections = (
			_merge_authoritative_rows(authoritative_corrections, browser_corrections)
			if has_correction_matrix
			else authoritative_corrections
		)
	doc.set("items", items)
	doc.set("correction_items", corrections)
	from essdee_yrp.fabric_grn import validate_actual_dia_rows

	validate_actual_dia_rows(doc)
	doc.set("item_details", None)
	doc.set("correction_item_details", None)

	if cint(submit):
		# Frappe save locks the GRN parent. Enter the same Lot-first order as
		# Desk submit now; submit() reuses the lock recorded on doc.flags.
		_lock_versioned_cloth_lot(doc)
	if name:
		doc.save()
	else:
		doc.insert()
	if cint(submit):
		frappe.has_permission("YRP Goods Received Note", ptype="submit", doc=doc, throw=True)
		doc.submit()
	return get_goods_received_note_workspace(doc.name)


def get_goods_received_note_calculation(name: str) -> dict:
	"""Return the same saved Work Order calculation context used by Desk."""

	doc = _get_grn(name)
	if not _calculate_eligible(doc):
		frappe.throw(_("Calculate is not available for this Goods Received Note mode."))
	return get_grn_calculation_context(name)


def calculate_goods_received_note(
	name: str,
	rows,
	received_type: str,
	expected_modified: str | None,
) -> dict:
	"""Delegate Calculate to Essdee's selected-Received-Type replacement."""

	doc = _get_grn(name, "write")
	if not _calculate_eligible(doc):
		frappe.throw(_("Calculate is not available for this Goods Received Note mode."))
	assert_expected_modified(doc, expected_modified)
	rows = _as_list(rows)
	result = calculate_grn_receivables(name, rows, received_type, expected_modified)
	return {
		"workspace": get_goods_received_note_workspace(name),
		"calculation": result,
	}


def _inspection_sources(doc) -> list:
	doc.run_method("onload")
	get_onload = getattr(doc, "get_onload", None)
	onload = get_onload() if callable(get_onload) else (doc.get("__onload") or {})
	sources = onload.get("item_details") or []
	if isinstance(sources, str):
		sources = frappe.parse_json(sources)
	return sources or []


def _inspection_projection(doc) -> dict:
	doc.check_permission("read")
	sources = _inspection_sources(doc)
	workspace = get_workspace_base(
		doc,
		fieldnames=INSPECTION_FIELDS,
		capabilities={
			"save": {"label": _("Edit"), "permission": "write", "eligible": cint(doc.docstatus) == 0},
			"submit": {"label": _("Submit"), "permission": "submit", "eligible": cint(doc.docstatus) == 0},
			"cancel": {
				"label": _("Cancel"),
				"permission": "cancel",
				"eligible": cint(doc.docstatus) == 1 and not doc.get("is_converted"),
			},
			"amend": {"label": _("Amend"), "permission": "amend", "eligible": cint(doc.docstatus) == 2},
		},
	)
	readable = {field["fieldname"] for field in workspace["fields"]}
	workspace["values"] = {
		fieldname: doc.get(fieldname) for fieldname in INSPECTION_FIELDS if fieldname in readable
	}
	workspace["item_details"] = sources
	return workspace


def _inspection_source_key(source: Mapping) -> tuple:
	return (
		source.get("ref_doctype") or "",
		source.get("ref_docname") or "",
		source.get("item_variant") or "",
	)


def _merge_inspection_sources(authoritative, browser_sources) -> list[dict]:
	browser_by_key = defaultdict(list)
	for source in browser_sources or []:
		browser_by_key[_inspection_source_key(source)].append(source)

	merged = []
	for source in authoritative or []:
		trusted = _row_dict(source)
		matches = browser_by_key.get(_inspection_source_key(trusted)) or []
		browser = matches.pop(0) if matches else None
		if browser is None:
			merged.append(trusted)
			continue
		splits = []
		for split in _as_list(browser.get("splits")):
			target = split.get("target_received_type")
			if not target or not frappe.db.exists("YRP Received Type", target):
				frappe.throw(_("Select a valid target Received Type."))
			splits.append(
				{
					"target_received_type": target,
					"qty": _number(split.get("qty"), _("Inspection quantity")),
					"received_date": split.get("received_date"),
					"comments": split.get("comments") or "",
				}
			)
		available_quantity = flt(trusted.get("grn_qty") or trusted.get("quantity"))
		if sum(flt(split.get("qty")) for split in splits) > available_quantity + 0.0001:
			frappe.throw(
				_("Inspection splits exceed the available quantity for {0}.").format(
					trusted.get("item_variant") or trusted.get("ref_docname")
				)
			)
		trusted["splits"] = splits
		merged.append(trusted)
	if any(matches for matches in browser_by_key.values()):
		frappe.throw(_("The Inspection Entry contains an unknown source row."))
	return merged


def save_goods_received_note_inspection(
	name: str,
	values,
	*,
	inspection_name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	"""Create or update a nested Inspection Entry using trusted GRN bins."""

	values = _as_mapping(values)
	grn = _get_grn(name)
	if not _inspectable(grn):
		frappe.throw(_("Only submitted, non-return Goods Received Notes can be inspected."))
	if inspection_name:
		doc = frappe.get_doc("YRP Inspection Entry", inspection_name)
		doc.check_permission("write")
		if doc.get("against") != "YRP Goods Received Note" or doc.get("against_id") != grn.name:
			frappe.throw(_("Inspection Entry does not belong to Goods Received Note {0}.").format(grn.name))
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Inspection Entries can be edited."))
		assert_expected_modified(doc, expected_modified)
		authoritative = _inspection_sources(doc)
	else:
		frappe.has_permission("YRP Inspection Entry", ptype="create", throw=True)
		assert_expected_modified(grn, expected_modified)
		doc = frappe.new_doc("YRP Inspection Entry")
		doc.against = "YRP Goods Received Note"
		doc.against_id = grn.name
		authoritative = get_inspection_initial_payload("YRP Goods Received Note", grn.name) or []

	for fieldname in ("posting_date", "posting_time", "remarks"):
		if fieldname in values:
			doc.set(fieldname, values[fieldname])
	browser_sources = values.get("item_details") or values.get("sources")
	sources = (
		_merge_inspection_sources(authoritative, _as_list(browser_sources))
		if browser_sources is not None
		else authoritative
	)
	doc.set("item_details", frappe.as_json(sources))
	if inspection_name:
		doc.save()
	else:
		doc.insert()
	if cint(submit):
		frappe.has_permission("YRP Inspection Entry", ptype="submit", doc=doc, throw=True)
		doc.submit()
	return {
		"workspace": get_goods_received_note_workspace(grn.name),
		"inspection": _inspection_projection(doc),
	}


def execute_goods_received_note_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	"""Execute a named, permission-checked GRN lifecycle or transfer action."""

	payload = _as_mapping(payload)
	doc = _get_grn(name)
	assert_expected_modified(doc, expected_modified)

	if command == "complete_transfer":
		if not _target_permission("YRP Stock Entry"):
			_permission_error(_("You do not have permission to create the completion Stock Entry."))
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Goods Received Note must be submitted before completing the transfer."))
		if not doc.get("is_internal_unit"):
			frappe.throw(_("Goods Received Note is not an internal unit transfer."))
		if doc.get("transfer_complete"):
			frappe.throw(_("Transfer is already complete for this Goods Received Note."))
		created = get_draft_completion_stock_entry("YRP Goods Received Note", doc.name) or make_grn_completion(doc.name)
		return {
			"workspace": get_goods_received_note_workspace(doc.name),
			"created": {"doctype": "YRP Stock Entry", "name": created},
		}

	if command in {"prepare_sms", "prepare_whatsapp"}:
		return prepare_supplier_notification(
			doc,
			"YRP Goods Received Note",
			command.removeprefix("prepare_"),
		)
	if command in {"send_sms", "send_whatsapp"}:
		return send_supplier_notification(
			doc,
			"YRP Goods Received Note",
			command.removeprefix("send_"),
			payload,
		)

	if command not in {"submit", "cancel", "amend"}:
		frappe.throw(_("Unsupported Goods Received Note command: {0}").format(command))
	required_status = {"submit": 0, "cancel": 1, "amend": 2}[command]
	if cint(doc.docstatus) != required_status:
		frappe.throw(_("Goods Received Note cannot be {0} from its current state.").format(command))
	frappe.has_permission("YRP Goods Received Note", ptype=command, doc=doc, throw=True)
	if command == "submit":
		doc.submit()
		return get_goods_received_note_workspace(doc.name)
	if command == "cancel":
		doc.cancel()
		return get_goods_received_note_workspace(doc.name)

	amended = frappe.copy_doc(doc)
	amended.docstatus = 0
	amended.amended_from = doc.name
	amended.insert()
	return get_goods_received_note_workspace(amended.name)
