"""Delivery Challan coordination service for the Fabric Store workspace.

The document controller remains the authority for stock, valuation, pending
quantity, and ledger side effects.  This module only projects a safe web
contract and merges operator-entered quantities onto authoritative rows.
"""

from __future__ import annotations

from collections.abc import Mapping

import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.utils import cint, flt
from yrp.stock.api import get_stock_dimensions_for_ui
from yrp.stock.save_stock_items import (
	group_correction_items_for_ui,
	group_items_for_ui,
	ungroup_correction_items_from_ui,
	ungroup_items_from_ui,
)
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
	get_return_delivery_items,
	make_dc_completion,
)

from essdee_yrp.cutting.movement import _load_movement as _load_return_movement
from essdee_yrp.cutting.movement import get_grouped_movement_rows, get_panel_key, get_panel_quantities
from essdee_yrp.delivery_challan_hooks import create_return_grn as create_essdee_return_grn
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
from essdee_yrp.work_order_actions import get_delivery_challan_defaults

DELIVERY_CHALLAN_FIELDS = (
	"naming_series",
	"work_order",
	"purchase_order",
	"posting_date",
	"posting_time",
	"edit_posting_date_and_time",
	"process_name",
	"item",
	"production_detail",
	"lot",
	"is_rework",
	"from_location",
	"from_location_name",
	"supplier",
	"supplier_name",
	"from_warehouse",
	"to_warehouse",
	"from_address",
	"from_address_details",
	"supplier_address",
	"supplier_address_details",
	"vehicle_no",
	"supplier_document_no",
	"comments",
	"actual_date",
	"includes_packing",
	"allow_non_bundle",
	"additional_goods_value",
	"is_internal_unit",
	"transfer_complete",
	"ste_transferred",
	"ste_transferred_percent",
	"from_finishing",
	"cutting_bulk_lay_sheet",
	"cutting_bulk_lay_sheet_detail",
	"cut_panel_movement",
	"loose_piece_dc",
	"pack_piece_dc",
	"letter_head",
)

DELIVERY_CHALLAN_EDITOR_FIELDS = (
	"posting_date",
	"posting_time",
	"edit_posting_date_and_time",
	"from_location",
	"from_warehouse",
	"to_warehouse",
	"from_address",
	"supplier_address",
	"vehicle_no",
	"supplier_document_no",
	"comments",
	"allow_non_bundle",
	"additional_goods_value",
	"letter_head",
)

DELIVERY_CHALLAN_TOTALS = (
	"total_delivered_qty",
	"stock_value",
	"additional_goods_value",
	"total_value",
)

DELIVERY_CHALLAN_RECORD_FIELDS = (
	"work_order",
	"purchase_order",
	"process_name",
	"item",
	"production_detail",
	"lot",
	"supplier",
	"supplier_name",
	"from_location",
	"from_warehouse",
	"to_warehouse",
	"includes_packing",
	"is_internal_unit",
	"transfer_complete",
	"ste_transferred",
	"ste_transferred_percent",
	"from_finishing",
	"cutting_bulk_lay_sheet",
	"cutting_bulk_lay_sheet_detail",
	"cut_panel_movement",
	"loose_piece_dc",
	"pack_piece_dc",
)

SPECIAL_SOURCE_FIELDS = (
	"from_finishing",
	"cutting_bulk_lay_sheet",
	"cutting_bulk_lay_sheet_detail",
	"cut_panel_movement",
	"loose_piece_dc",
	"pack_piece_dc",
)


def _as_mapping(value, *, default=None):
	if value in (None, ""):
		return {} if default is None else default
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


def _get_delivery_challan(name: str, permission: str = "read"):
	doc = frappe.get_doc("YRP Delivery Challan", name)
	doc.check_permission(permission)
	return doc


def _target_create_permission(doctype: str) -> bool:
	return bool(frappe.has_permission(doctype, ptype="create"))


def _validated_purchase_order_source(name: str | None) -> str:
	if not name:
		return ""
	purchase_order = frappe.get_doc("Purchase Order", name)
	purchase_order.check_permission("read")
	if cint(purchase_order.docstatus) != 1:
		frappe.throw(_("Purchase Order must be submitted before linking it to a Delivery Challan."))
	return purchase_order.name


def _warehouse_party(warehouse: str | None) -> str | None:
	if not warehouse:
		return None
	return frappe.db.get_value("Warehouse", warehouse, "supplier")


def _address_display_for_party(address: str, party: str, field_label: str) -> str:
	linked = frappe.db.exists(
		"Dynamic Link",
		{
			"parenttype": "Address",
			"parent": address,
			"link_doctype": "Supplier",
			"link_name": party,
		},
	)
	if not linked:
		frappe.throw(
			_("{0} {1} is not linked to {2}. Select an address belonging to that location.").format(
				field_label,
				address,
				party,
			)
		)
	return get_address_display(address) or ""


def missing_location_address_message(party: str) -> str:
	name = frappe.db.get_value("Supplier", party, "supplier_name") or party
	location = f"{name} ({party})" if name != party else party
	return _("No address is linked to {0}. Create an address for this location first.").format(location)


def location_has_address(party: str) -> bool:
	return bool(frappe.db.exists("Dynamic Link", {
		"parenttype": "Address", "link_doctype": "Supplier", "link_name": party,
	}))


def validate_location_addresses(doc, method=None) -> None:
	for party_field, address_field in (("from_location", "from_address"), ("supplier", "supplier_address")):
		party = doc.get(party_field)
		if party and not doc.get(address_field) and not location_has_address(party):
			frappe.throw(missing_location_address_message(party))


def _validate_and_sync_party_dependencies(doc) -> None:
	"""Keep web-edited warehouse and address values owned by their selected parties."""

	validate_location_addresses(doc)
	dependencies = (
		(
			"from_location", "from_warehouse", "from_address", "from_address_details",
			_("From Location"), _("From Warehouse"), _("From Address"),
		),
		(
			"supplier", "to_warehouse", "supplier_address", "supplier_address_details",
			_("Supplier / Receiver"), _("To Warehouse"), _("Supplier Address"),
		),
	)
	for (
		party_field, warehouse_field, address_field, details_field,
		party_label, warehouse_label, address_label,
	) in dependencies:
		party = doc.get(party_field)
		warehouse = doc.get(warehouse_field)
		address = doc.get(address_field)

		if (warehouse or address) and not party:
			frappe.throw(_("Select {0} before choosing its warehouse or address.").format(party_label))
		if warehouse:
			owner = _warehouse_party(warehouse)
			if owner != party:
				frappe.throw(
					_("{0} {1} does not belong to {2} {3}. Select a warehouse for that location.").format(
						warehouse_label, warehouse, party_label, party,
					)
				)
		if address:
			doc.set(details_field, _address_display_for_party(address, party, address_label))
		else:
			doc.set(details_field, "")


def _permission_error(message: str):
	frappe.throw(message, frappe.PermissionError)


def _special_source_context(doc_or_values) -> dict:
	modes = [
		fieldname
		for fieldname in SPECIAL_SOURCE_FIELDS
		if doc_or_values.get(fieldname) not in (None, "", 0, False)
	]
	return {
		"active": bool(modes),
		"modes": modes,
		"read_only": bool(modes),
	}


def _stable_row_index(value):
	if value in (None, ""):
		return ""
	text = str(value).strip()
	if text.lstrip("-").isdigit():
		return int(text)
	return text


def _row_identity(row) -> tuple:
	combination = row.get("set_combination") or ""
	if isinstance(combination, dict):
		combination = frappe.as_json(combination)
	return (
		row.get("item_variant"),
		_stable_row_index(row.get("row_index")),
		row.get("received_type") or "",
		row.get("delivery_challan_item") or "",
		row.get("work_order_correction") or "",
		str(combination),
	)


def _merge_authoritative_rows(authoritative, browser_rows, *, quantity_field: str = "qty") -> list[dict]:
	"""Copy only user quantities onto trusted rows and reject injected rows."""

	entered = {}
	for row in browser_rows or []:
		entered.setdefault(_row_identity(row), []).append(row)

	merged = []
	for source in authoritative or []:
		row = _row_dict(source)
		matches = entered.get(_row_identity(row)) or []
		browser = matches.pop(0) if matches else {}
		try:
			quantity = float(browser.get(quantity_field) or 0)
		except (TypeError, ValueError):
			frappe.throw(_("Item quantity must be a number."))
		if quantity < 0:
			frappe.throw(_("Item quantity cannot be negative."))
		row[quantity_field] = quantity
		if "comments" in browser:
			row["comments"] = browser.get("comments") or ""
		if quantity_field == "qty":
			row["delivered_quantity"] = quantity
		if "secondary_qty" in browser:
			try:
				secondary_quantity = float(browser.get("secondary_qty") or 0)
			except (TypeError, ValueError):
				frappe.throw(_("Secondary quantity must be a number."))
			if secondary_quantity < 0:
				frappe.throw(_("Secondary quantity cannot be negative."))
			row["secondary_qty"] = secondary_quantity
		merged.append(row)

	remaining_rows = [row for matches in entered.values() for row in matches]
	if any(
		flt(row.get(quantity_field)) > 0 or flt(row.get("secondary_qty")) > 0
		for row in remaining_rows
	):
		frappe.throw(
			_("The available item rows changed. Refresh the editor and enter the quantities again.")
		)
	return merged


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
		items = group_items_for_ui(doc.get("items") or [], "YRP Delivery Challan")
	if not corrections and doc.get("correction_items"):
		corrections = group_correction_items_for_ui(
			doc.get("correction_items") or [], "YRP Delivery Challan"
		)
	return items or [], corrections or []


def _return_variants(doc) -> dict:
	return {
		"normal": True,
		"whole_bundle": bool(doc.get("lot")),
		"cut_panel_movement_filters": {
			"docstatus": 1,
			"lot": doc.get("lot"),
			"from_warehouse": doc.get("supplier"),
			"against_id": ["is", "not set"],
		},
	}


def _return_context(doc) -> dict:
	if cint(doc.docstatus) != 1 or not _target_create_permission("YRP Goods Received Note"):
		return {}
	try:
		context = get_return_delivery_items(doc.name) or {}
	except (frappe.ValidationError, frappe.PermissionError) as error:
		context = {"items": [], "reason": str(error)}
	context["variants"] = _return_variants(doc)
	context["delivery_challan"] = doc.name
	context["return_location"] = doc.get("from_location")
	return context


def _related_documents(doc) -> dict:
	related = {"returns": [], "completion_entries": []}
	if frappe.has_permission("YRP Goods Received Note", ptype="read"):
		related["returns"] = [
			dict(row)
			for row in frappe.get_list(
				"YRP Goods Received Note",
				filters={"delivery_challan": doc.name, "is_return": 1},
				fields=["name", "docstatus", "posting_date", "modified"],
				order_by="modified desc",
				limit_page_length=500,
			)
		]
	if frappe.has_permission("YRP Stock Entry", ptype="read"):
		related["completion_entries"] = [
			dict(row)
			for row in frappe.get_list(
				"YRP Stock Entry",
				filters={
					"against": "YRP Delivery Challan",
					"against_id": doc.name,
					"purpose": "DC Completion",
				},
				fields=["name", "docstatus", "posting_date", "modified"],
				order_by="modified desc",
				limit_page_length=500,
			)
		]
	return related


def _notification_capabilities(doc) -> dict[str, bool]:
	return get_supplier_notification_capabilities(doc, "YRP Delivery Challan")


def _capability_candidates(doc, return_context: Mapping) -> dict[str, dict]:
	docstatus = cint(doc.docstatus)
	can_return = bool(
		docstatus == 1
		and return_context.get("items")
		and _target_create_permission("YRP Goods Received Note")
	)
	can_complete = bool(
		docstatus == 1
		and doc.get("is_internal_unit")
		and not doc.get("transfer_complete")
		and _target_create_permission("YRP Stock Entry")
	)
	notifications = _notification_capabilities(doc)
	return {
		"save": {"label": _("Edit"), "permission": "write", "eligible": docstatus == 0},
		"submit": {"label": _("Submit"), "permission": "submit", "eligible": docstatus == 0},
		"cancel": {"label": _("Cancel"), "permission": "cancel", "eligible": docstatus == 1},
		"amend": {"label": _("Amend"), "permission": "amend", "eligible": docstatus == 2},
		"return": {"label": _("Return"), "eligible": can_return},
		"complete_transfer": {"label": _("Complete Transfer"), "eligible": can_complete},
		"prepare_sms": {"label": _("Send SMS"), "eligible": notifications["sms"]},
		"prepare_whatsapp": {
			"label": _("Send WhatsApp"),
			"eligible": notifications["whatsapp"],
		},
	}


def _dimension_projection(doc) -> list[dict]:
	projected = []
	for source in get_stock_dimensions_for_ui():
		dimension = dict(source)
		dimension["fieldtype"] = "Link" if dimension.get("options") else "Data"
		dimension["reqd"] = bool(dimension.get("mandatory"))
		dimension["value"] = doc.get(dimension["fieldname"])
		dimension["locked"] = bool(cint(doc.docstatus) != 0)
		projected.append(dimension)
	return projected


def _document_values(doc, readable_fields) -> dict:
	return {
		fieldname: doc.get(fieldname)
		for fieldname in DELIVERY_CHALLAN_FIELDS
		if fieldname in readable_fields
	}


def _editable_header_fieldnames() -> tuple[str, ...]:
	"""Return explicit headers plus configured, non-source-owned stock dimensions."""

	dimensions = (
		dimension.get("fieldname")
		for dimension in get_stock_dimensions_for_ui()
	)
	return tuple(
		dict.fromkeys(
			(
				*DELIVERY_CHALLAN_EDITOR_FIELDS,
				*(
					fieldname
					for fieldname in dimensions
					if fieldname
					and fieldname not in DELIVERY_CHALLAN_RECORD_FIELDS
					and fieldname not in SPECIAL_SOURCE_FIELDS
				),
			)
		)
	)


def _source_values(defaults: Mapping, browser_values: Mapping | None = None) -> dict:
	values = {
		key: value
		for key, value in defaults.items()
		if key not in {"items", "item_details", "correction_items", "correction_item_details"}
	}
	for fieldname in _editable_header_fieldnames():
		if browser_values and fieldname in browser_values:
			values[fieldname] = browser_values[fieldname]
	return values


def get_delivery_challan_workspace(
	name: str | None = None,
	source=None,
) -> dict:
	"""Return an existing DC workspace or a new source-derived editor."""

	if not name:
		source_values = _as_mapping(source)
		if source_values.get("duplicate_from"):
			frappe.has_permission("YRP Delivery Challan", ptype="create", throw=True)
			original = _get_delivery_challan(source_values["duplicate_from"])
			if _special_source_context(original)["active"]:
				frappe.throw(
					_("This source-managed Delivery Challan cannot be duplicated. Create it from its originating workflow instead.")
				)
			item_matrix, correction_matrix = _onload_matrices(original)
			doc = frappe.new_doc("YRP Delivery Challan")
			doc.update({fieldname: original.get(fieldname) for fieldname in DELIVERY_CHALLAN_FIELDS})
			doc.work_order = original.get("work_order")
			doc.purchase_order = original.get("purchase_order")
			return _new_delivery_challan_workspace(
				doc,
				item_matrix,
				correction_matrix,
				bool(frappe.has_permission("YRP Delivery Challan", ptype="submit")),
			)
		work_order = source_values.get("work_order")
		if not work_order:
			frappe.throw(_("Work Order is required to create a Delivery Challan."))
		return preview_delivery_challan_source(work_order, source_values)

	doc = _get_delivery_challan(name)
	item_matrix, correction_matrix = _onload_matrices(doc)
	return_context = _return_context(doc)
	if return_context:
		return_context.setdefault("variants", _return_variants(doc))
	workspace = get_workspace_base(
		doc,
		fieldnames=DELIVERY_CHALLAN_FIELDS,
		totals=DELIVERY_CHALLAN_TOTALS,
		capabilities=_capability_candidates(doc, return_context),
	)
	readable_fields = {field["fieldname"] for field in workspace["fields"]}
	workspace["record"].update(
		{
			fieldname: doc.get(fieldname)
			for fieldname in DELIVERY_CHALLAN_RECORD_FIELDS
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
			"return_context": return_context,
			"special_source": _special_source_context(doc),
			"related": _related_documents(doc),
			# Compatibility names used by the first popup implementation.
			"item_groups": item_matrix,
			"correction_item_groups": correction_matrix,
			"details": workspace["fields"],
		}
	)
	return workspace


def preview_delivery_challan_source(work_order: str, values=None) -> dict:
	"""Refresh a new editor from the selected Work Order authority."""

	frappe.has_permission("YRP Delivery Challan", ptype="create", throw=True)
	browser_values = _as_mapping(values)
	defaults = get_delivery_challan_defaults(work_order)
	doc = frappe.new_doc("YRP Delivery Challan")
	doc.update(_source_values(defaults, browser_values))
	if browser_values.get("purchase_order"):
		doc.purchase_order = _validated_purchase_order_source(browser_values.get("purchase_order"))
	doc.set("items", defaults.get("items") or [])
	doc.set("correction_items", defaults.get("correction_items") or [])
	can_submit = bool(frappe.has_permission("YRP Delivery Challan", ptype="submit"))
	return _new_delivery_challan_workspace(
		doc,
		defaults.get("item_details") or [],
		defaults.get("correction_item_details") or [],
		can_submit,
		defaults,
	)


def _new_delivery_challan_workspace(
	doc,
	item_matrix,
	correction_matrix,
	can_submit: bool,
	special_source=None,
) -> dict:
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
	for fieldname in DELIVERY_CHALLAN_TOTALS:
		field = doc.meta.get_field(fieldname)
		totals.append(
			{
				"fieldname": fieldname,
				"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
				"value": doc.get(fieldname),
			}
		)
	fields = get_effective_fields(doc, DELIVERY_CHALLAN_FIELDS)
	readable_fields = {field["fieldname"] for field in fields}
	workspace = {
		"record": {
			"doctype": "YRP Delivery Challan",
			"name": None,
			"docstatus": 0,
			"status": _("Draft"),
			"modified": None,
			**{
				fieldname: doc.get(fieldname)
				for fieldname in DELIVERY_CHALLAN_RECORD_FIELDS
				if fieldname in readable_fields
			},
		},
		"fields": fields,
		"totals": totals,
		"permissions": permissions,
		"print_formats": [],
		"related": {},
		"return_context": {},
		"values": _document_values(doc, readable_fields),
		"matrices": {
			"items": item_matrix,
			"correction_items": correction_matrix,
		},
		"dimensions": _dimension_projection(doc),
		"capabilities": {
			"save": {"label": _("Save")},
			**(
				{"submit": {"label": _("Submit")}}
				if can_submit
				else {}
			),
		},
		"special_source": _special_source_context(special_source or doc),
		"item_groups": item_matrix,
		"correction_item_groups": correction_matrix,
	}
	workspace["details"] = workspace["fields"]
	return workspace


def _browser_rows(values: Mapping, *, corrections: bool, fallback_rows) -> list:
	keys = (
		("correction_item_details", "correction_item_groups")
		if corrections
		else ("item_details", "item_groups")
	)
	matrix_key = next((key for key in keys if key in values), None)
	if matrix_key is None:
		return [_row_dict(row) for row in fallback_rows or []]
	if corrections:
		return ungroup_correction_items_from_ui(
			values.get(matrix_key) or [],
			"YRP Delivery Challan",
			keep_zero=True,
		)
	return ungroup_items_from_ui(
		values.get(matrix_key) or [],
		"YRP Delivery Challan",
		keep_zero=True,
	)


def save_delivery_challan(
	values,
	*,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	"""Save a DC while trusting only controller/source-owned data and quantities."""

	values = _as_mapping(values)
	submitted_update = False
	allow_on_submit_fields = set()
	if name:
		doc = _get_delivery_challan(name, "write")
		frappe.has_permission("YRP Delivery Challan", ptype="write", doc=doc, throw=True)
		assert_expected_modified(doc, expected_modified)
		docstatus = cint(doc.docstatus)
		if docstatus == 1:
			if cint(submit):
				frappe.throw(_("A submitted Delivery Challan cannot be submitted again."))
			submitted_update = True
			allow_on_submit_fields = set(get_allow_on_submit_fields(doc))
			allowed_payload_fields = {
				fieldname
				for fieldname in _editable_header_fieldnames()
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
			frappe.throw(_("Only Draft Delivery Challans can be edited."))
		authoritative_items = [_row_dict(row) for row in (doc.get("items") or [])]
		authoritative_corrections = [
			_row_dict(row) for row in (doc.get("correction_items") or [])
		]
	else:
		frappe.has_permission("YRP Delivery Challan", ptype="create", throw=True)
		work_order = values.get("work_order")
		if not work_order:
			frappe.throw(_("Work Order is required."))
		defaults = get_delivery_challan_defaults(work_order)
		doc = frappe.new_doc("YRP Delivery Challan")
		doc.update(_source_values(defaults))
		if values.get("purchase_order"):
			doc.purchase_order = _validated_purchase_order_source(values.get("purchase_order"))
		authoritative_items = [_row_dict(row) for row in (defaults.get("items") or [])]
		authoritative_corrections = [
			_row_dict(row) for row in (defaults.get("correction_items") or [])
		]

	header_fieldnames = (
		allow_on_submit_fields
		if submitted_update
		else set(_editable_header_fieldnames())
	)
	header = {
		fieldname: values[fieldname]
		for fieldname in header_fieldnames
		if fieldname in values
	}
	doc.update(header)
	if not submitted_update:
		_validate_and_sync_party_dependencies(doc)
	if _special_source_context(doc)["active"]:
		# Cutting, finishing, packing, and movement builders own these rows. A
		# generic web matrix may display them, but it must never rewrite them.
		items = authoritative_items
		corrections = authoritative_corrections
	else:
		browser_items = _browser_rows(values, corrections=False, fallback_rows=authoritative_items)
		browser_corrections = _browser_rows(
			values,
			corrections=True,
			fallback_rows=authoritative_corrections,
		)
		items = _merge_authoritative_rows(authoritative_items, browser_items)
		corrections = _merge_authoritative_rows(authoritative_corrections, browser_corrections)
	doc.set("items", items)
	doc.set("correction_items", corrections)
	# The controller must validate the trusted flat children directly.  Leaving
	# browser matrices attached would make before_validate expand them a second time.
	doc.set("item_details", None)
	doc.set("correction_item_details", None)

	if name:
		doc.save()
	else:
		doc.insert()
	if cint(submit):
		frappe.has_permission("YRP Delivery Challan", ptype="submit", doc=doc, throw=True)
		doc.submit()
	return get_delivery_challan_workspace(doc.name)


def _require_submitted(doc, action: str) -> None:
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Delivery Challan must be submitted before {0}.").format(action))


def _validate_return_variant(
	doc,
	*,
	return_whole_bundles: bool,
	cut_panel_movement: str | None,
) -> str | None:
	if return_whole_bundles and not cut_panel_movement:
		frappe.throw(_("Select the Return Cut Panel Movement."))
	if cut_panel_movement and not return_whole_bundles:
		frappe.throw(_("Enable Return Whole Bundles before selecting a Cut Panel Movement."))
	if not return_whole_bundles:
		return None

	movement = _load_return_movement(cut_panel_movement)
	if movement.get("lot") != doc.get("lot"):
		frappe.throw(
			_("Cut Panel Movement {0} belongs to Lot {1}, not {2}.").format(
				movement.name,
				movement.get("lot") or _("an unspecified Lot"),
				doc.get("lot") or _("an unspecified Lot"),
			)
		)
	if movement.get("from_warehouse") != doc.get("supplier"):
		frappe.throw(
			_("Cut Panel Movement {0} is from {1}, but this return comes back from {2}.").format(
				movement.name, movement.get("from_warehouse"), doc.get("supplier")
			)
		)
	return movement.name


def get_return_movement_quantities(doc, cut_panel_movement: str) -> dict:
	"""Map every panel of a return CPM onto this DC's returnable rows, or explain why it cannot."""
	cut_panel_movement = _validate_return_variant(
		doc, return_whole_bundles=True, cut_panel_movement=cut_panel_movement
	)
	_movement, ipd_doc, movement_rows = get_grouped_movement_rows(
		cut_panel_movement, "YRP Goods Received Note"
	)
	returnable = {
		row["delivery_challan_item"]: flt(row.get("returnable_quantity"))
		for row in (get_return_delivery_items(doc.name) or {}).get("items") or []
	}
	dc_rows = [(row, get_panel_key(row, ipd_doc)) for row in doc.get("items") or [] if row.name in returnable]
	quantities = {}
	problems = []
	for key, quantity in get_panel_quantities(movement_rows, ipd_doc, "quantity").items():
		variant, remaining = key[0], quantity
		for row, row_key in dc_rows:
			if remaining <= 0 or row_key != key:
				continue
			allocated = min(remaining, returnable[row.name])
			if allocated > 0:
				quantities[row.name] = allocated
				remaining = flt(remaining - allocated, 3)
		if remaining > 0:
			problems.append(
				_("{0}: Cut Panel Movement has {1}, this Delivery Challan can return {2}").format(
					variant, quantity, flt(quantity - remaining, 3)
				)
			)
	if problems:
		frappe.throw(
			_(
				"Cut Panel Movement {0} cannot be returned in full against Delivery Challan {1}.<br>{2}"
			).format(cut_panel_movement, doc.name, "<br>".join(problems)),
			title=_("Return the whole Cut Panel Movement"),
		)
	return {
		"cut_panel_movement": cut_panel_movement,
		"quantities": quantities,
		"panel_rows": [row.name for row, row_key in dc_rows if row_key],
	}


def _prepare_notification(doc, payload: Mapping) -> dict:
	return prepare_supplier_notification(
		doc,
		"YRP Delivery Challan",
		payload.get("channel"),
	)


def execute_delivery_challan_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	"""Execute one permission/state checked DC command through native services."""

	payload = _as_mapping(payload)
	doc = _get_delivery_challan(name)
	assert_expected_modified(doc, expected_modified)

	if command == "return":
		if not _target_create_permission("YRP Goods Received Note"):
			_permission_error(_("You do not have permission to create a return Goods Received Note."))
		_require_submitted(doc, _("creating a return"))
		if doc.get("is_internal_unit") and not doc.get("transfer_complete"):
			frappe.throw(_("Complete the internal-unit transfer before returning items."))
		items = _as_list(payload.get("items"))
		return_whole_bundles = bool(cint(payload.get("return_whole_bundles")))
		cut_panel_movement = _validate_return_variant(
			doc,
			return_whole_bundles=return_whole_bundles,
			cut_panel_movement=payload.get("cut_panel_movement"),
		)
		created = create_essdee_return_grn(
			doc.name,
			items,
			payload.get("received_type"),
			cut_panel_movement,
		)
		return {
			"workspace": get_delivery_challan_workspace(doc.name),
			"created": {"doctype": "YRP Goods Received Note", "name": created},
		}

	if command == "complete_transfer":
		if not _target_create_permission("YRP Stock Entry"):
			_permission_error(_("You do not have permission to create the completion Stock Entry."))
		_require_submitted(doc, _("completing the transfer"))
		if not doc.get("is_internal_unit"):
			frappe.throw(_("Delivery Challan is not an internal unit transfer."))
		if doc.get("transfer_complete"):
			frappe.throw(_("Transfer is already complete for this Delivery Challan."))
		created = get_draft_completion_stock_entry("YRP Delivery Challan", doc.name) or make_dc_completion(doc.name)
		return {
			"workspace": get_delivery_challan_workspace(doc.name),
			"created": {"doctype": "YRP Stock Entry", "name": created},
		}

	if command in {"prepare_sms", "prepare_whatsapp"}:
		payload["channel"] = command.removeprefix("prepare_")
		return _prepare_notification(doc, payload)

	if command == "prepare_notification":
		return _prepare_notification(doc, payload)

	if command in {"send_sms", "send_whatsapp"}:
		return send_supplier_notification(
			doc,
			"YRP Delivery Challan",
			command.removeprefix("send_"),
			payload,
		)

	if command not in {"submit", "cancel", "amend"}:
		frappe.throw(_("Unsupported Delivery Challan command: {0}").format(command))

	required_status = {"submit": 0, "cancel": 1, "amend": 2}[command]
	if cint(doc.docstatus) != required_status:
		frappe.throw(_("Delivery Challan cannot be {0} from its current state.").format(command))
	frappe.has_permission("YRP Delivery Challan", ptype=command, doc=doc, throw=True)
	if command == "submit":
		doc.submit()
		return get_delivery_challan_workspace(doc.name)
	if command == "cancel":
		doc.cancel()
		return get_delivery_challan_workspace(doc.name)

	amended = frappe.copy_doc(doc)
	amended.docstatus = 0
	amended.amended_from = doc.name
	amended.insert()
	return get_delivery_challan_workspace(amended.name)
