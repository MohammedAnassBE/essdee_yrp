"""Work Order coordination service for the Fabric Store workspace."""

from __future__ import annotations


from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp import attribute_links as attribute_db
from yrp.attribute_read_context import attribute_read_scope
from yrp.stock.api import get_stock_dimensions_for_ui
from yrp.stock.save_stock_items import group_items_for_ui
from yrp.yrp.doctype.yrp_debit.yrp_debit import (
	approve_debit,
	create_debit,
	has_debit_request_permission,
)
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import (
	create_rework_work_order,
	get_close_permission,
	get_debits,
)

from essdee_yrp.api.work_order import (
	calculate_fabric_deliverables,
	fetch_summary_details,
	get_fabric_deliverable_context,
	get_work_order_selection_context,
)
from essdee_yrp.fabric_store.documents.common import (
	assert_expected_modified,
	filter_authorized_capabilities,
	get_document_permissions,
	get_effective_fields,
	get_workspace_base,
)
from essdee_yrp.garment_work_order import (
	calculate_garment_work_order,
	get_garment_work_order_context,
)
from essdee_yrp.rework_work_order import get_rework_source_rows
from essdee_yrp.time_and_action.tracking import update_expected_date
from essdee_yrp.work_order_actions import (
	apply_bom_accessory_changes,
	get_delivery_challan_defaults,
	get_goods_received_note_defaults,
	get_wo_bom_accessory_change_preview,
	get_wo_bom_accessory_items,
	get_wo_recut_defaults,
	get_work_order_action_context,
)
from essdee_yrp.work_order_close import SD_CLOSE_REASONS, close_work_order
from essdee_yrp.work_order_piece_tracking import calculate_completed_pieces

WORK_ORDER_FIELDS = (
	"status",
	"naming_series",
	"wo_date",
	"supplier",
	"supplier_name",
	"includes_packing",
	"no_receivables",
	"process_name",
	"lot",
	"item",
	"production_detail",
	"delivery_location",
	"delivery_location_name",
	"planned_start_date",
	"planned_end_date",
	"expected_delivery_date",
	"start_date",
	"end_date",
	"supplier_address",
	"supplier_address_details",
	"delivery_address",
	"delivery_address_details",
	"terms_and_condition",
	"open_status",
	"close_reason",
	"sd_close_reason",
	"close_other_reason",
	"close_remarks",
	"closed_by",
	"is_rework",
	"parent_wo",
	"supplier_type",
	"rework_type",
	"comments",
)

WORK_ORDER_EDITOR_FIELDS = (
	"naming_series",
	"edit_wo_date",
	"wo_date",
	"supplier",
	"no_receivables",
	"process_name",
	"lot",
	"item",
	"production_detail",
	"delivery_location",
	"planned_start_date",
	"planned_end_date",
	"expected_delivery_date",
	"supplier_address",
	"delivery_address",
	"terms_and_condition",
	"comments",
	"planned_quantity",
	"is_rework",
	"parent_wo",
	"supplier_type",
	"rework_type",
)

# Rework identity and planned quantity are shown so the sectioned editor is
# complete, but their values belong to the rework/calculation services.  Keep
# the browser write contract narrower than the display contract.
WORK_ORDER_EDITOR_WRITABLE_FIELDS = (
	"naming_series",
	"edit_wo_date",
	"wo_date",
	"supplier",
	"no_receivables",
	"process_name",
	"lot",
	"item",
	"production_detail",
	"delivery_location",
	"planned_start_date",
	"planned_end_date",
	"expected_delivery_date",
	"supplier_address",
	"delivery_address",
	"terms_and_condition",
	"comments",
)

WORK_ORDER_EDITOR_COPY_FIELDS = WORK_ORDER_EDITOR_WRITABLE_FIELDS
WORK_ORDER_EDITOR_PROTECTED_FIELDS = frozenset(
	set(WORK_ORDER_EDITOR_FIELDS) - set(WORK_ORDER_EDITOR_WRITABLE_FIELDS)
)

WORK_ORDER_RECORD_FIELDS = (
	"status",
	"open_status",
	"supplier",
	"supplier_name",
	"includes_packing",
	"no_receivables",
	"process_name",
	"item",
	"production_detail",
	"delivery_location",
	"lot",
	"is_rework",
	"parent_wo",
	"sd_close_reason",
	"close_other_reason",
	"close_remarks",
)

WORK_ORDER_TOTALS = (
	"planned_quantity",
	"total_quantity",
	"total_no_of_pieces_delivered",
	"total_no_of_pieces_received",
)

RELATED_DOCTYPES = {
	"delivery_challan": "YRP Delivery Challan",
	"goods_received_note": "YRP Goods Received Note",
}

RELATED_FIELDS = (
	"name",
	"docstatus",
	"posting_date",
	"posting_time",
	"item",
	"modified",
)


def _get_work_order(name: str, permission: str = "read"):
	doc = frappe.get_doc("YRP Work Order", name)
	doc.check_permission(permission)
	return doc


def _dependency(adapter, name: str, default):
	return getattr(adapter, name, default) if adapter is not None else default


def _as_dict(row) -> dict:
	as_dict = getattr(row, "as_dict", None)
	if callable(as_dict):
		return as_dict()
	return dict(row)


def _work_order_header_dimensions(doc, dimensions) -> list[dict]:
	"""Return production-group Link fields that really exist on the WO header."""

	get_field = getattr(getattr(doc, "meta", None), "get_field", None)
	if not callable(get_field):
		return []
	applicable = []
	for source in dimensions or []:
		dimension = dict(source)
		fieldname = dimension.get("fieldname")
		if not fieldname or not dimension.get("is_production_group"):
			continue
		field = get_field(fieldname)
		if not field or field.get("fieldtype") != "Link":
			continue
		applicable.append(dimension)
	return applicable


def _target_create_permission(doctype: str, adapter=None) -> bool:
	if adapter is not None:
		if doctype in getattr(adapter, "SUPPORTED_DOCTYPES", ()):
			return bool(adapter._permission_flags(doctype).get("can_create"))
		return bool(adapter.frappe.has_permission(doctype, ptype="create"))
	return bool(frappe.has_permission(doctype, ptype="create"))


def _target_read_permission(doctype: str, adapter=None) -> bool:
	if adapter is not None:
		if doctype in getattr(adapter, "SUPPORTED_DOCTYPES", ()):
			return bool(adapter._permission_flags(doctype).get("can_read"))
		return bool(adapter.frappe.has_permission(doctype, ptype="read"))
	return bool(frappe.has_permission(doctype, ptype="read"))


def _settings_role_allowed(fieldname: str) -> bool:
	role = attribute_db.get_single_value("YRP Settings", fieldname)
	return bool(role and role in frappe.get_roles(frappe.session.user))


def _dimension_projection(doc, dimensions=None) -> list[dict]:
	projected = []
	for source in dimensions if dimensions is not None else get_stock_dimensions_for_ui():
		dimension = dict(source)
		dimension["value"] = doc.get(dimension["fieldname"])
		dimension["locked"] = bool(cint(doc.docstatus) != 0)
		projected.append(dimension)
	return projected


def _selection_context(doc, loader=get_work_order_selection_context) -> dict:
	if not doc.get("lot") or not doc.get("process_name"):
		return {}
	return loader(doc.lot, doc.process_name)


def _summary(doc, loader=fetch_summary_details) -> dict:
	if not doc.get("production_detail"):
		return {
			"item_detail": [],
			"deliverables": [],
			"work_order_docstatus": doc.docstatus,
		}
	return loader(doc.name, doc.production_detail)


def _related_documents(work_order: str, key: str, adapter=None) -> list[dict]:
	if adapter is not None:
		return adapter._related_work_order_documents(work_order, key)
	doctype = RELATED_DOCTYPES[key]
	if not _target_read_permission(doctype):
		return []
	filters = (
		{"work_order": work_order}
		if key == "delivery_challan"
		else {"against": "YRP Work Order", "against_id": work_order}
	)
	fields = [*RELATED_FIELDS, *(["is_return"] if key == "goods_received_note" else [])]
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit_page_length=500,
	)
	return [_as_dict(row) for row in rows]


def _load_action_context(doc) -> dict:
	# A process is mandatory on persisted Work Orders. The guard also keeps the
	# compatibility adapter tolerant of old partially-migrated draft records.
	if not doc.get("process_name"):
		return {}
	return get_work_order_action_context(doc.name)


def _close_context(doc, action_context: Mapping) -> dict:
	if cint(doc.docstatus) != 1 or doc.get("open_status") == "Close" or not action_context:
		return {}
	return get_close_permission() or {}


def _capability_candidates(
	doc,
	selection: Mapping,
	action_context: Mapping,
	close_context: Mapping,
	*,
	adapter=None,
) -> dict[str, dict]:
	docstatus = cint(doc.docstatus)
	is_open = bool(docstatus == 1 and doc.get("open_status") == "Open")
	is_close_request = bool(docstatus == 1 and doc.get("open_status") == "Close Request")
	is_close_manager = bool(close_context.get("is_close_manager"))
	has_close_role = bool(close_context.get("approver_role"))
	is_fabric = bool(selection.get("process_is_cloth_process") or selection.get("is_cloth_process"))
	has_calculation_context = bool(
		doc.get("lot") and doc.get("process_name") and doc.get("production_detail")
	)
	can_create_dc = bool(
		action_context.get("can_make_delivery_challan")
		and _target_create_permission("YRP Delivery Challan", adapter)
	)
	can_create_grn = bool(
		action_context.get("can_make_goods_received_note")
		and _target_create_permission("YRP Goods Received Note", adapter)
	)
	can_create_rework = bool(
		is_open
		and not doc.get("is_rework")
		and _target_create_permission("YRP Work Order", adapter)
	)
	can_create_debit = bool(is_open and has_debit_request_permission())
	return {
		"save": {"label": _("Edit"), "permission": "write", "eligible": docstatus == 0},
		"submit": {"label": _("Submit"), "permission": "submit", "eligible": docstatus == 0},
		"cancel": {"label": _("Cancel Document"), "permission": "cancel", "eligible": docstatus == 1},
		"amend": {"label": _("Amend"), "permission": "amend", "eligible": docstatus == 2},
		"calculate_fabric": {
			"label": _("Calculate Fabric Deliverables"),
			"permission": "write",
			"eligible": bool(
				docstatus == 0 and not doc.get("is_rework") and has_calculation_context and is_fabric
			),
		},
		"calculate_garment": {
			"label": _("Calculate Items"),
			"permission": "write",
			"eligible": bool(
				docstatus == 0
				and not doc.get("is_rework")
				and has_calculation_context
				and not is_fabric
			),
		},
		"request_close": {
			"label": _("Request Close"),
			"eligible": bool(is_open and has_close_role and not is_close_manager),
		},
		"close": {
			"label": _("Close"),
			"eligible": bool(is_open and has_close_role and is_close_manager),
		},
		"approve_close": {
			"label": _("Approve Close"),
			"eligible": bool(is_close_request and is_close_manager),
		},
		"create_debit": {"label": _("Create Debit"), "eligible": can_create_debit},
		"create_rework": {"label": _("Create Rework"), "eligible": can_create_rework},
		"calculate_pieces": {
			"label": _("Calculate Pieces"),
			"eligible": bool(action_context.get("can_calculate_pieces")),
		},
		"change_delivery_date": {
			"label": _("Change Delivery Date"),
			"eligible": bool(action_context.get("can_change_delivery_date")),
		},
		"change_item": {
			"label": _("Change Item"),
			"eligible": bool(action_context.get("can_change_item")),
		},
		"create_delivery_challan": {
			"label": _("Make DC"),
			"eligible": can_create_dc,
			"source_context": {"work_order": doc.name},
		},
		"create_goods_received_note": {
			"label": _("Make GRN"),
			"eligible": can_create_grn,
			"requires_delivery_challan": bool(doc.get("is_rework")),
			"source_context": {"work_order": doc.name},
		},
		"create_material_issue": {
			"label": _("Material Issue"),
			"eligible": bool(action_context.get("can_make_material_issue")),
			"source_context": {
				"work_order": doc.name,
				"purpose": "Material Issue",
				"against": "YRP Work Order",
				"against_id": doc.name,
				"from_warehouse": action_context.get("material_issue_warehouse"),
				"from_supplier": doc.get("supplier"),
				"to_supplier": doc.get("supplier"),
			},
		},
		"create_cutting_plan": {
			"label": _("Make Cutting Plan"),
			"eligible": bool(action_context.get("can_make_cutting_plan")),
			"source_context": {"work_order": doc.name, "lot": doc.get("lot"), "item": doc.get("item")},
		},
		"create_recut": {
			"label": _("Create Recut"),
			"eligible": bool(action_context.get("can_make_recut")),
			"source_context": {"work_order": doc.name, "lot": doc.get("lot")},
		},
		"create_sewing_plan": {
			"label": _("Create Sewing Plan"),
			"eligible": bool(
				action_context.get("can_create_sewing_plan") and not action_context.get("sewing_plan")
			),
		},
		"open_sewing_plan": {
			"label": _("Open Sewing Plan"),
			"eligible": bool(
				action_context.get("can_create_sewing_plan") and action_context.get("sewing_plan")
			),
			"name": action_context.get("sewing_plan"),
		},
	}


def _legacy_workspace_base(doc, capabilities: Mapping, adapter) -> dict:
	record = adapter._serialize_document(doc, fields=WORK_ORDER_RECORD_FIELDS)
	permissions = record["permissions"]
	has_permission = getattr(doc, "has_permission", None)
	fields = get_effective_fields(doc, WORK_ORDER_FIELDS)
	readable_fields = {field["fieldname"] for field in fields}
	record.update(
		{
			fieldname: doc.get(fieldname)
			for fieldname in WORK_ORDER_RECORD_FIELDS
			if fieldname in readable_fields
		}
	)
	totals = []
	for fieldname in WORK_ORDER_TOTALS:
		field = doc.meta.get_field(fieldname)
		totals.append(
			{
				"fieldname": fieldname,
				"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
				"value": doc.get(fieldname),
			}
		)
	return {
		"record": record,
		"fields": fields,
		"totals": totals,
		"permissions": permissions,
		"capabilities": filter_authorized_capabilities(capabilities, permissions),
		"print_formats": adapter.get_document_print_formats(doc) if callable(has_permission) else [],
	}


def get_work_order_workspace(name: str, *, _adapter=None) -> dict:
	"""Return the complete permission-filtered Work Order workspace."""
	with attribute_read_scope():
		return _build_work_order_workspace(name, _adapter=_adapter)


def _build_work_order_workspace(name: str, *, _adapter=None) -> dict:
	get_doc = _dependency(
		_adapter,
		"_get_supported_document",
		lambda doctype, docname: _get_work_order(docname),
	)
	doc = get_doc("YRP Work Order", name)
	selection_loader = _dependency(_adapter, "get_work_order_selection_context", get_work_order_selection_context)
	summary_loader = _dependency(_adapter, "fetch_summary_details", fetch_summary_details)
	group_items = _dependency(_adapter, "group_items_for_ui", group_items_for_ui)
	dimension_loader = _dependency(_adapter, "get_stock_dimensions_for_ui", get_stock_dimensions_for_ui)

	selection = _selection_context(doc, selection_loader)
	action_context = _load_action_context(doc)
	close_context = _close_context(doc, action_context)
	capabilities = _capability_candidates(
		doc,
		selection,
		action_context,
		close_context,
		adapter=_adapter,
	)
	if _adapter is not None:
		workspace = _legacy_workspace_base(doc, capabilities, _adapter)
	else:
		workspace = get_workspace_base(
			doc,
			fieldnames=WORK_ORDER_FIELDS,
			totals=WORK_ORDER_TOTALS,
			capabilities=capabilities,
		)

	deliverables = group_items(doc.get("deliverables") or [], "YRP Work Order Deliverables")
	receivables = group_items(doc.get("receivables") or [], "YRP Work Order Receivables")
	summary = _summary(doc, summary_loader)
	dimensions = _dimension_projection(doc, dimension_loader()) if doc.get("process_name") else []
	delivery_challans = _related_documents(doc.name, "delivery_challan", _adapter)
	goods_received_notes = _related_documents(doc.name, "goods_received_note", _adapter)
	calculated_items = [_as_dict(row) for row in (doc.get("work_order_calculated_items") or [])]
	readable_fields = {field["fieldname"] for field in workspace["fields"]}
	workspace["record"].update(
		{
			fieldname: doc.get(fieldname)
			for fieldname in WORK_ORDER_RECORD_FIELDS
			if fieldname in readable_fields
		}
	)
	related_permissions = (
		{
			key: _adapter._work_order_related_permissions(doc, doctype)
			for key, doctype in RELATED_DOCTYPES.items()
		}
		if _adapter is not None
		else {
			key: {
				**get_document_permissions(doctype),
				"can_create": bool(
					workspace["capabilities"].get(
						"create_delivery_challan" if key == "delivery_challan" else "create_goods_received_note"
					)
				),
			}
			for key, doctype in RELATED_DOCTYPES.items()
		}
	)
	workspace.update(
		{
			"matrices": {"deliverables": deliverables, "receivables": receivables},
			"dimensions": dimensions,
			"selection_context": selection,
			"action_context": action_context,
			"close_context": close_context,
			"calculated_items": calculated_items,
			"summary": summary,
			"related": {
				"delivery_challans": delivery_challans,
				"goods_received_notes": goods_received_notes,
			},
			# Compatibility aliases consumed by the current Work Order page.
			"details": workspace["fields"],
			"deliverables": deliverables,
			"receivables": receivables,
			"delivery_challans": delivery_challans,
			"goods_received_notes": goods_received_notes,
			"related_permissions": related_permissions,
		}
	)
	return workspace


def _calculation_contexts(doc, selection: Mapping) -> dict:
	if not doc.get("name") or cint(doc.docstatus) != 0 or doc.get("is_rework"):
		return {}
	if not doc.get("lot") or not doc.get("process_name") or not doc.get("production_detail"):
		return {}
	if selection.get("process_is_cloth_process") or selection.get("is_cloth_process"):
		return {"fabric": get_fabric_deliverable_context(doc.name)}
	return {"garment": get_garment_work_order_context(doc.name)}


def get_work_order_editor(name: str | None = None, source=None, *, _adapter=None) -> dict:
	"""Return the grouped editor contract for a new or Draft Work Order."""

	frappe_api = _dependency(_adapter, "frappe", frappe)
	group_items = _dependency(_adapter, "group_items_for_ui", group_items_for_ui)
	dimension_loader = _dependency(_adapter, "get_stock_dimensions_for_ui", get_stock_dimensions_for_ui)
	selection_loader = _dependency(_adapter, "get_work_order_selection_context", get_work_order_selection_context)
	permission_flags = _dependency(_adapter, "_permission_flags", get_document_permissions)
	if name:
		get_doc = _dependency(
			_adapter,
			"_get_supported_document",
			lambda doctype, docname: _get_work_order(docname),
		)
		doc = get_doc("YRP Work Order", name)
		frappe_api.has_permission("YRP Work Order", ptype="write", doc=doc, throw=True)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Work Orders can be edited."))
		permissions = permission_flags("YRP Work Order", doc)
	else:
		frappe_api.has_permission("YRP Work Order", ptype="create", throw=True)
		doc = frappe_api.new_doc("YRP Work Order")
		permissions = {
			"can_create": True,
			"can_write": False,
			"can_submit": bool(frappe_api.has_permission("YRP Work Order", ptype="submit")),
		}
		source = _mapping(source, _("Source"))
		duplicate_from = source.get("duplicate_from")
		if duplicate_from:
			original = _get_work_order(duplicate_from)
			doc.update({fieldname: original.get(fieldname) for fieldname in WORK_ORDER_EDITOR_COPY_FIELDS})
			# Deliverables, receivables, and calculated items are derived together
			# from Lot + Process + IPD. A new copy keeps the editable setup and uses
			# the normal Calculate action after its first Save to rebuild trusted
			# rows, instead of displaying stale source-owned lineage.
			for table_field in ("deliverables", "receivables", "work_order_calculated_items"):
				doc.set(table_field, [])
		else:
			doc.update(
				{
					fieldname: source.get(fieldname)
					for fieldname in ("lot", "process_name", "item", "production_detail", "supplier")
					if source.get(fieldname) not in (None, "")
				}
			)

	selection = _selection_context(doc, selection_loader)
	values = {fieldname: doc.get(fieldname) for fieldname in WORK_ORDER_EDITOR_FIELDS}
	return {
		"doctype": "YRP Work Order",
		"name": doc.get("name") or "",
		"modified": doc.get("modified") or "",
		"values": values,
		"fields": get_effective_fields(doc, WORK_ORDER_EDITOR_FIELDS),
		"condition_values": {"edit_wo_date": doc.get("edit_wo_date")},
		"deliverable_details": group_items(
			doc.get("deliverables") or [], "YRP Work Order Deliverables"
		),
		"receivable_details": group_items(
			doc.get("receivables") or [], "YRP Work Order Receivables"
		),
		"calculated_items": [_as_dict(row) for row in (doc.get("work_order_calculated_items") or [])],
		"selection_context": selection,
		"calculation_contexts": _calculation_contexts(doc, selection),
		"dimensions": _dimension_projection(
			doc,
			_work_order_header_dimensions(doc, dimension_loader()),
		),
		"permissions": permissions,
	}


def save_work_order_document(
	values,
	*,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
	_adapter=None,
) -> dict:
	"""Save grouped rows through the Work Order controller's own synchronizer."""

	frappe_api = _dependency(_adapter, "frappe", frappe)
	dimension_loader = _dependency(_adapter, "get_stock_dimensions_for_ui", get_stock_dimensions_for_ui)
	values = _mapping(values, _("Work Order values"))
	if name:
		get_doc = _dependency(
			_adapter,
			"_get_supported_document",
			lambda doctype, docname: _get_work_order(docname),
		)
		doc = get_doc("YRP Work Order", name)
		frappe_api.has_permission("YRP Work Order", ptype="write", doc=doc, throw=True)
		assert_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Work Orders can be edited."))
	else:
		frappe_api.has_permission("YRP Work Order", ptype="create", throw=True)
		doc = frappe_api.new_doc("YRP Work Order")

	if submit:
		frappe_api.has_permission("YRP Work Order", ptype="submit", doc=doc, throw=True)

	dimension_fields = {
		dimension.get("fieldname")
		for dimension in _work_order_header_dimensions(doc, dimension_loader())
		if dimension.get("fieldname")
	} - WORK_ORDER_EDITOR_PROTECTED_FIELDS
	header_fields = set(WORK_ORDER_EDITOR_WRITABLE_FIELDS) | dimension_fields
	header = {
		fieldname: values.get(fieldname)
		for fieldname in header_fields
		if fieldname in values
	}
	doc.update(header)
	for payload_field in ("deliverable_details", "receivable_details"):
		if payload_field in values:
			groups = values.get(payload_field)
			if not isinstance(groups, list):
				frappe.throw(_("{0} must be a grouped item list.").format(payload_field))
			doc.set(payload_field, frappe.as_json(groups))
	if name:
		doc.save()
	else:
		doc.insert()
	if submit:
		doc.submit()
	workspace_loader = _dependency(_adapter, "get_work_order_workspace", get_work_order_workspace)
	return workspace_loader(doc.name)


def _payload(value) -> dict:
	value = value if isinstance(value, dict) else frappe.parse_json(value or "{}")
	if not isinstance(value, dict):
		frappe.throw(_("Command payload must be an object."))
	return value


def _mapping(value, label: str) -> dict:
	value = value if isinstance(value, dict) else frappe.parse_json(value or "{}")
	if not isinstance(value, dict):
		frappe.throw(_("{0} must be an object.").format(label))
	return value


def _assert_open_submitted(doc) -> None:
	if cint(doc.docstatus) != 1 or doc.get("open_status") != "Open":
		frappe.throw(
			_("Work Order {0} must be submitted and open.").format(frappe.bold(doc.name))
		)


def _assert_close_command(doc, command: str) -> None:
	permission = get_close_permission() or {}
	if not permission.get("approver_role"):
		frappe.throw(_("Configure Work Order Closing Approver Role in YRP Settings."))
	is_manager = bool(permission.get("is_close_manager"))
	if command == "request_close":
		_assert_open_submitted(doc)
		if is_manager:
			frappe.throw(_("Close managers must use the Close action."))
		return
	if not is_manager:
		frappe.throw(_("You do not have permission to close Work Orders."), frappe.PermissionError)
	if command == "approve_close":
		if cint(doc.docstatus) != 1 or doc.get("open_status") != "Close Request":
			frappe.throw(_("Only a pending close request can be approved."))
		return
	_assert_open_submitted(doc)


def _require_system_manager() -> None:
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only System Managers can rebuild Work Order pieces."), frappe.PermissionError)


def execute_work_order_command(
	name: str,
	command: str,
	payload=None,
	expected_modified: str | None = None,
) -> dict:
	"""Execute one allowlisted Work Order command through its owner service."""

	commands = {
		"submit",
		"cancel",
		"amend",
		"get_close_context",
		"close",
		"request_close",
		"approve_close",
		"create_debit",
		"approve_debit",
		"get_rework_context",
		"create_rework",
		"calculate_garment",
		"calculate_fabric",
		"calculate_pieces",
		"change_delivery_date",
		"get_change_item_context",
		"preview_change_item",
		"change_item",
		"prepare_delivery_challan",
		"prepare_goods_received_note",
		"prepare_recut",
		"create_recut",
		"create_sewing_plan",
	}
	if command not in commands:
		frappe.throw(_("Unsupported Work Order command: {0}").format(command))
	doc = _get_work_order(name)
	assert_expected_modified(doc, expected_modified)
	payload = _payload(payload)

	if command == "get_close_context":
		can_read_debits = _target_read_permission("YRP Debit")
		permission = get_close_permission()
		return {
			"permission": permission,
			"debits": get_debits(name) if can_read_debits else [],
			"reason_options": list(SD_CLOSE_REASONS),
			"close_reason": doc.get("sd_close_reason") or "",
			"close_other_reason": doc.get("close_other_reason") or "",
			"close_remarks": doc.get("close_remarks") or "",
			"can_create_debit": bool(
				permission.get("is_close_manager") and _target_create_permission("YRP Debit")
			),
			"can_approve_debit": bool(
				can_read_debits and _settings_role_allowed("debit_approval_role")
			),
		}
	if command == "get_rework_context":
		return {"rows": get_rework_source_rows(name)}
	if command == "get_change_item_context":
		return get_wo_bom_accessory_items(name)
	if command == "preview_change_item":
		return get_wo_bom_accessory_change_preview(name, payload.get("selected") or [])
	if command == "prepare_delivery_challan":
		return get_delivery_challan_defaults(
			name,
			posting_date=payload.get("posting_date"),
			posting_time=payload.get("posting_time"),
		)
	if command == "prepare_goods_received_note":
		return get_goods_received_note_defaults(name, payload.get("delivery_challan"))
	if command == "prepare_recut":
		return {
			**get_wo_recut_defaults(name),
			"can_submit": bool(frappe.has_permission("SD YRP WO Recut", ptype="submit")),
		}

	result_name = name
	if command == "submit":
		frappe.has_permission("YRP Work Order", ptype="submit", doc=doc, throw=True)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Work Order can be submitted."))
		doc.submit()
	elif command == "cancel":
		frappe.has_permission("YRP Work Order", ptype="cancel", doc=doc, throw=True)
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Only a submitted Work Order can be cancelled."))
		doc.cancel()
	elif command == "amend":
		frappe.has_permission("YRP Work Order", ptype="amend", doc=doc, throw=True)
		if cint(doc.docstatus) != 2:
			frappe.throw(_("Only a cancelled Work Order can be amended."))
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.amended_from = doc.name
		amended.insert()
		result_name = amended.name
	elif command in {"close", "request_close", "approve_close"}:
		_assert_close_command(doc, command)
		if payload.get("with_debit"):
			frappe.has_permission("YRP Debit", ptype="create", throw=True)
			create_debit(
				name,
				debit_no=payload.get("debit_no"),
				debit_value=payload.get("debit_value"),
				reason=payload.get("debit_reason"),
				on_close=1,
			)
		close_work_order(
			name,
			sd_close_reason=payload.get("close_reason"),
			close_other_reason=payload.get("close_other_reason"),
			close_remarks=payload.get("close_remarks"),
		)
	elif command == "create_debit":
		_assert_open_submitted(doc)
		if not has_debit_request_permission():
			frappe.throw(_("You do not have permission to request a Debit."), frappe.PermissionError)
		create_debit(
			name,
			debit_no=payload.get("debit_no"),
			debit_value=payload.get("debit_value"),
			reason=payload.get("reason"),
			debit_document=payload.get("debit_document") or None,
			on_close=0,
		)
	elif command == "approve_debit":
		debit = payload.get("debit")
		if not debit or frappe.db.get_value("YRP Debit", debit, "work_order") != name:
			frappe.throw(
				_("Debit {0} does not belong to Work Order {1}.").format(debit or "", name),
				frappe.PermissionError,
			)
		approve_debit(debit)
	elif command == "create_rework":
		result_name = create_rework_work_order(
			name,
			payload.get("rows") or [],
			supplier_type=payload.get("supplier_type") or "Same Supplier",
			supplier=payload.get("supplier"),
		)
	elif command == "calculate_garment":
		calculate_garment_work_order(
			name,
			payload.get("rows") or [],
			modified=expected_modified,
		)
	elif command == "calculate_fabric":
		calculate_fabric_deliverables(
			name,
			payload.get("rows") or [],
			modified=expected_modified,
			source_process=payload.get("source_process"),
		)
	elif command == "calculate_pieces":
		_require_system_manager()
		calculate_completed_pieces(name)
	elif command == "change_delivery_date":
		update_expected_date(
			name,
			payload.get("expected_date"),
			payload.get("reason"),
			_return=False,
		)
	elif command == "change_item":
		apply_bom_accessory_changes(name, payload.get("selected") or [])
	elif command == "create_recut":
		frappe.has_permission("SD YRP WO Recut", ptype="create", throw=True)
		item_details = payload.get("item_details") or []
		if not any(
			flt(value.get("qty")) > 0
			for group in item_details
			for row in (group.get("items") or [])
			for value in (row.get("values") or {}).values()
		):
			frappe.throw(_("Enter a Recut quantity greater than zero."))
		recut = frappe.new_doc("SD YRP WO Recut")
		recut.work_order = doc.name
		recut.lot = doc.get("lot")
		recut.recut_item_details = frappe.as_json(item_details)
		recut.insert()
		if payload.get("submit"):
			frappe.has_permission("SD YRP WO Recut", ptype="submit", doc=recut, throw=True)
			recut.submit()
		workspace = get_work_order_workspace(name)
		workspace["created"] = {"doctype": recut.doctype, "name": recut.name, "docstatus": recut.docstatus}
		return workspace
	elif command == "create_sewing_plan":
		from essdee_yrp.sewing.plan import create_sewing_plan

		sewing_plan = create_sewing_plan(name)
		return {"name": sewing_plan}

	return get_work_order_workspace(result_name)
