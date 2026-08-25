"""Essdee cut-panel movement adapters for generic YRP transactions.

The bundle/panel selection and bundle ledger are Essdee business concepts.
Stock Entry, Delivery Challan, and Goods Received Note remain base-YRP
documents: this module only builds their generic item payloads and mirrors the
selected bundle movement into the Essdee bundle ledger on submit/cancel.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.stock.dimensions import apply_dimension_defaults, get_dimension_fieldnames
from yrp.stock.save_stock_items import group_items_for_ui
from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	_get_warehouse_for_supplier,
)
from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	get_work_order_defaults as get_dc_work_order_defaults,
)
from yrp.yrp.doctype.goods_received_note.goods_received_note import (
	get_work_order_defaults as get_grn_work_order_defaults,
)
from yrp.yrp.doctype.item.item import get_or_create_variant
from yrp.yrp.doctype.item_dependent_attribute_mapping.item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)

_COMPLETION_PURPOSES = {"DC Completion", "GRN Completion"}
_ROOT_TRANSACTION_DOCTYPES = (
	"Stock Entry",
	"Delivery Challan",
	"Goods Received Note",
)


def _json_dict(value):
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	try:
		data = json.loads(value)
	except (TypeError, ValueError, json.JSONDecodeError):
		frappe.throw(_("Invalid Set Combination data in the cut-panel movement."))
	if not isinstance(data, dict):
		frappe.throw(_("Set Combination must be a JSON object."))
	return data


def _json_key(value):
	return json.dumps(_json_dict(value), sort_keys=True, separators=(",", ":"))


def _movement_uses_collapsed(movement):
	return any(
		cint(row.get("moved")) and flt(row.get("move_qty")) > 0
		for row in (movement.get("collapsed_details") or [])
	)


def _require_create_permission(doctype):
	frappe.has_permission(doctype, "create", throw=True)


def get_active_root_transactions(cpm_name, *, exclude_doctype=None, exclude_name=None):
	"""Return non-cancelled root transactions that claim a CPM.

	Completion Stock Entries are follow-up legs of a DC/GRN and intentionally
	share its Cut Panel Movement. They do not compete for root ownership.
	"""
	owners = []
	for doctype in _ROOT_TRANSACTION_DOCTYPES:
		filters = {
			"cut_panel_movement": cpm_name,
			"docstatus": ["<", 2],
		}
		if doctype == exclude_doctype and exclude_name:
			filters["name"] = ["!=", exclude_name]
		if doctype == "Stock Entry":
			filters["purpose"] = ["not in", tuple(_COMPLETION_PURPOSES)]
		for row in frappe.get_all(
			doctype,
			filters=filters,
			fields=["name", "docstatus", "creation"],
		):
			owners.append(
				frappe._dict(
					doctype=doctype,
					name=row.name,
					docstatus=row.docstatus,
					creation=row.creation,
				)
			)
	return sorted(owners, key=lambda row: row.creation)


def _get_active_root_transaction(cpm_name, *, exclude_doctype=None, exclude_name=None):
	owners = get_active_root_transactions(
		cpm_name,
		exclude_doctype=exclude_doctype,
		exclude_name=exclude_name,
	)
	return (owners[0].doctype, owners[0].name) if owners else None


def _throw_active_root_transaction(cpm_name, owner):
	doctype, name = owner
	frappe.throw(
		_(
			"Cut Panel Movement {0} is already used by active {1} {2}. "
			"Cancel or delete that transaction before creating another one."
		).format(cpm_name, doctype, name)
	)


def validate_transaction_link(doc, method=None):
	"""Enforce one active root Stock Entry/DC/GRN per submitted CPM."""
	del method
	cpm_name = doc.get("cut_panel_movement")
	if not cpm_name or (
		doc.doctype == "Stock Entry" and doc.purpose in _COMPLETION_PURPOSES
	):
		return

	cpm = frappe.db.get_value(
		"Cut Panel Movement",
		cpm_name,
		["docstatus", "against", "against_id"],
		as_dict=True,
		for_update=True,
	)
	if not cpm or cpm.docstatus != 1:
		frappe.throw(_("Cut Panel Movement {0} must be submitted.").format(cpm_name))
	if cpm.against_id and (
		cpm.against != doc.doctype or cpm.against_id != doc.name
	):
		frappe.throw(
			_("Cut Panel Movement {0} is already linked to {1} {2}.").format(
				cpm_name, cpm.against, cpm.against_id
			)
		)

	owner = _get_active_root_transaction(
		cpm_name,
		exclude_doctype=doc.doctype,
		exclude_name=doc.name,
	)
	if owner:
		_throw_active_root_transaction(cpm_name, owner)


def _load_movement(doc_name, *, allow_linked=False):
	doc = frappe.get_doc("Cut Panel Movement", doc_name)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Cut Panel Movement {0} must be submitted.").format(doc.name))
	if doc.against_id and not allow_linked:
		frappe.throw(
			_("Cut Panel Movement {0} is already linked to {1} {2}.").format(
				doc.name, doc.against, doc.against_id
			)
		)
	if not allow_linked:
		owner = _get_active_root_transaction(doc.name)
		if owner:
			_throw_active_root_transaction(doc.name, owner)
	if not doc.cut_panel_movement_json:
		frappe.throw(_("Cut Panel Movement {0} has no selected bundles.").format(doc.name))
	return doc


def _get_uom(ipd_doc):
	details = get_dependent_attribute_details(ipd_doc.dependent_attribute_mapping)
	stage = (details.get("attr_list") or {}).get(ipd_doc.stiching_in_stage) or {}
	uom = stage.get("uom")
	if not uom:
		frappe.throw(
			_("UOM is not configured for stitching stage {0} in {1}.").format(
				ipd_doc.stiching_in_stage, ipd_doc.dependent_attribute_mapping
			)
		)
	return uom


def get_grouped_movement_rows(doc_name, target_doctype, *, allow_linked=False):
	"""Return the selected CPM panels/accessories as flat target item rows."""
	if target_doctype not in {"Stock Entry", "Delivery Challan", "Goods Received Note"}:
		frappe.throw(_("Unsupported Cut Panel Movement target {0}.").format(target_doctype))

	doc = _load_movement(doc_name, allow_linked=allow_linked)
	ipd_name, item_name = frappe.db.get_value(
		"Lot", doc.lot, ["production_detail", "item"]
	) or (None, None)
	if not ipd_name or not item_name:
		frappe.throw(_("Lot {0} is missing its Item Production Detail or Item.").format(doc.lot))
	ipd_doc = frappe.get_cached_doc("Item Production Detail", ipd_name)
	uom = _get_uom(ipd_doc)

	panel_qty = {
		row.stiching_attribute_value: flt(row.quantity)
		for row in ipd_doc.get("stiching_item_details") or []
	}
	movement = frappe.parse_json(doc.cut_panel_movement_json)
	if not isinstance(movement, dict):
		frappe.throw(_("Cut Panel Movement data must be a JSON object."))

	variant_totals = defaultdict(float)
	variant_group = {}
	selected_exact = False
	for colour, colour_data in (movement.get("data") or {}).items():
		part = colour_data.get("part")
		panels = (
			(movement.get("panels") or {}).get(part, [])
			if ipd_doc.is_set_item
			else (movement.get("panels") or [])
		)
		for data in colour_data.get("data") or []:
			combination = _json_dict(data.get("set_combination"))
			for grouped_panel in panels:
				if not data.get(grouped_panel) or not data.get(f"{grouped_panel}_moved"):
					continue
				selected_exact = True
				for panel in (p.strip() for p in grouped_panel.split(",") if p.strip()):
					if panel not in panel_qty:
						frappe.throw(_("Panel {0} is not configured in {1}.").format(panel, ipd_name))
					attributes = {
						ipd_doc.primary_item_attribute: data.get("size"),
						ipd_doc.packing_attribute: data.get(f"{grouped_panel}_colour"),
						ipd_doc.dependent_attribute: ipd_doc.stiching_in_stage,
						ipd_doc.stiching_attribute: panel,
					}
					variant = get_or_create_variant(item_name, attributes)
					key = (variant, _json_key(combination))
					variant_totals[key] += flt(data.get(grouped_panel)) * panel_qty[panel]
					variant_group[key] = (panel, colour, combination)

	selected_collapsed = _movement_uses_collapsed(movement)
	if selected_exact and selected_collapsed:
		frappe.throw(
			_(
				"Exact bundles and collapsed quantities cannot be mixed in one Cut Panel Movement. "
				"Create separate movements for the two stock types."
			)
		)
	for collapsed in movement.get("collapsed_details") or []:
		if not cint(collapsed.get("moved")):
			continue
		quantity = flt(collapsed.get("move_qty"), 3)
		available = flt(collapsed.get("quantity"), 3)
		if quantity <= 0:
			continue
		if quantity > available:
			frappe.throw(
				_("Collapsed move qty {0} exceeds available qty {1}.").format(
					quantity, available
				)
			)
		panel = collapsed.get("panel")
		if panel not in panel_qty:
			frappe.throw(_("Panel {0} is not configured in {1}.").format(panel, ipd_name))
		combination = _json_dict(collapsed.get("set_combination"))
		attributes = {
			ipd_doc.primary_item_attribute: collapsed.get("size"),
			ipd_doc.packing_attribute: collapsed.get("colour"),
			ipd_doc.dependent_attribute: ipd_doc.stiching_in_stage,
			ipd_doc.stiching_attribute: panel,
		}
		variant = get_or_create_variant(item_name, attributes)
		key = (variant, _json_key(combination))
		# Collapsed CBML quantities are already stored as physical panel pieces,
		# including the IPD per-garment panel multiplier.
		variant_totals[key] += quantity
		variant_group[key] = (panel, collapsed.get("colour"), combination)

	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	rows = []
	row_index = -1
	table_index = -1
	current_group = None
	for key in sorted(
		variant_totals,
		key=lambda value: (
			variant_group[value][0],
			variant_group[value][1],
			value[1],
			value[0],
		),
	):
		variant, combination_key = key
		combined_panel, colour, combination = variant_group[key]
		group_key = (combined_panel, colour, combination_key)
		if group_key != current_group:
			current_group = group_key
			row_index += 1
			table_index += 1
		row = {
			("item" if target_doctype == "Stock Entry" else "item_variant"): variant,
			("qty" if target_doctype != "Goods Received Note" else "quantity"): flt(variant_totals[key]),
			"uom": uom,
			"table_index": table_index,
			"row_index": row_index,
			"set_combination": combination,
			"lot": doc.lot,
			"received_type": default_received_type,
		}
		rows.append(row)

	table_index += 1
	row_index += 1
	for accessory in movement.get("accessory_data") or []:
		qty = flt(accessory.get("moved_weight"))
		if qty <= 0:
			continue
		cloth_item = accessory.get("cloth_name")
		if not cloth_item:
			frappe.throw(_("A moved accessory is missing its cloth Item."))
		variant = get_or_create_variant(
			cloth_item,
			{
				ipd_doc.packing_attribute: accessory.get("colour"),
				"Dia": accessory.get("dia"),
			},
		)
		accessory_uom = frappe.db.get_value("Item", cloth_item, "default_unit_of_measure")
		row = {
			("item" if target_doctype == "Stock Entry" else "item_variant"): variant,
			("qty" if target_doctype != "Goods Received Note" else "quantity"): qty,
			"uom": accessory_uom,
			"table_index": table_index,
			"row_index": row_index,
			"set_combination": {},
			"lot": doc.lot,
			"received_type": default_received_type,
		}
		rows.append(row)
		row_index += 1

	if not rows:
		frappe.throw(_("No moved panel or accessory quantity was selected."))
	apply_dimension_defaults(rows)
	return doc, ipd_doc, rows


def build_stock_entry_defaults(doc_name):
	_require_create_permission("Stock Entry")
	doc, _ipd, rows = get_grouped_movement_rows(doc_name, "Stock Entry")
	from_warehouse = _get_warehouse_for_supplier(doc.from_warehouse)
	if not from_warehouse:
		frappe.throw(
			_("Exactly one enabled Warehouse must be linked to Supplier {0}.").format(
				doc.from_warehouse
			)
		)
	defaults = {
		"purpose": "Send to Warehouse",
		"from_warehouse": from_warehouse,
		"from_supplier": doc.from_warehouse,
		"cut_panel_movement": doc.name,
		"items": rows,
		"item_details": group_items_for_ui(rows, "Stock Entry"),
	}
	if _movement_uses_collapsed(frappe.parse_json(doc.cut_panel_movement_json)):
		defaults["allow_non_bundle"] = 1
	return defaults


def _movement_details(rows, qty_field):
	details = {}
	for row in rows:
		key = (row.get("item_variant"), _json_key(row.get("set_combination")))
		if key not in details:
			details[key] = frappe._dict(
				qty=0,
				table_index=row.get("table_index"),
				row_index=row.get("row_index"),
			)
		details[key].qty += flt(row.get(qty_field))
	return details


def _overlay_source_rows(source_rows, movement_rows, *, target_doctype):
	qty_field = "quantity" if target_doctype == "Goods Received Note" else "qty"
	details = _movement_details(movement_rows, qty_field)
	matched = 0
	output = []
	for source in source_rows or []:
		as_dict = getattr(source, "as_dict", None)
		row = frappe._dict(as_dict() if callable(as_dict) else dict(source))
		key = (row.get("item_variant"), _json_key(row.get("set_combination")))
		movement = details.pop(key, None)
		qty = flt(movement.qty) if movement else 0
		if not qty:
			continue
		matched += 1
		# Work Order source rows may use a different row_index for every
		# size. Preserve the CPM's panel/colour grouping for the generated
		# transaction instead of inheriting those source display indexes.
		row.table_index = movement.table_index
		row.row_index = movement.row_index
		conversion = flt(row.get("conversion_factor")) or 1
		if target_doctype == "Goods Received Note":
			row.quantity = qty
			row.received_quantity = qty
		else:
			row.qty = qty
			row.delivered_quantity = qty
		row.stock_qty = qty * conversion
		row.amount = flt(row.stock_qty) * flt(row.get("valuation_rate") or row.get("rate"))
		output.append(row)
	if not matched:
		frappe.throw(_("The selected panels do not match any row in the selected Work Order."))
	if details:
		frappe.throw(
			_("Some selected panels do not match any row in the selected Work Order.")
		)
	return output


def _copy_existing_fields(target, source, target_doctype):
	field_map = {
		"supplier_name": "supplier_name",
		"delivery_location_name": "delivery_location_name",
	}
	if target_doctype == "Delivery Challan":
		field_map.update(
			{
				"supplier_address": "supplier_address",
				"supplier_address_details": "supplier_address_details",
				"from_address": "delivery_address",
				"from_address_details": "delivery_address_details",
			}
		)
	else:
		field_map.update(
			{
				"supplier_address": "supplier_address",
				"supplier_address_display": "supplier_address_details",
				"delivery_address": "delivery_address",
				"delivery_address_display": "delivery_address_details",
			}
		)
	for target_field, source_field in field_map.items():
		if source.meta.get_field(source_field) and source.get(source_field) is not None:
			target[target_field] = source.get(source_field)


def build_delivery_challan_defaults(doc_name, work_order):
	_require_create_permission("Delivery Challan")
	cpm, _ipd, movement_rows = get_grouped_movement_rows(doc_name, "Delivery Challan")
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	if wo.docstatus != 1 or wo.open_status == "Close" or wo.lot != cpm.lot:
		frappe.throw(_("Select an open, submitted Work Order for Lot {0}.").format(cpm.lot))
	defaults = get_dc_work_order_defaults(
		work_order, posting_date=cpm.posting_date, posting_time=cpm.posting_time
	)
	items = _overlay_source_rows(
		defaults.get("items"), movement_rows, target_doctype="Delivery Challan"
	)
	defaults["items"] = items
	defaults["item_details"] = group_items_for_ui(items, "Delivery Challan")
	defaults["cut_panel_movement"] = cpm.name
	if _movement_uses_collapsed(frappe.parse_json(cpm.cut_panel_movement_json)):
		defaults["allow_non_bundle"] = 1
	defaults["work_order"] = wo.name
	_copy_existing_fields(defaults, wo, "Delivery Challan")
	return defaults


def build_goods_received_note_defaults(
	doc_name, work_order, return_items=False, delivery_challan=None
):
	_require_create_permission("Goods Received Note")
	cpm, _ipd, movement_rows = get_grouped_movement_rows(
		doc_name, "Goods Received Note", allow_linked=cint(return_items)
	)
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	if wo.docstatus != 1 or wo.open_status == "Close" or wo.lot != cpm.lot:
		frappe.throw(_("Select an open, submitted Work Order for Lot {0}.").format(cpm.lot))

	if cint(return_items):
		source_rows = []
		for row in wo.get("deliverables") or []:
			values = row.as_dict()
			values["quantity"] = values.get("qty")
			values["ref_doctype"] = "Work Order Deliverables"
			values["ref_docname"] = row.name
			source_rows.append(values)
		return _overlay_source_rows(
			source_rows, movement_rows, target_doctype="Goods Received Note"
		)

	delivery_challan_doc = None
	if delivery_challan:
		delivery_challan_doc = frappe.get_doc("Delivery Challan", delivery_challan)
		delivery_challan_doc.check_permission("read")
		if delivery_challan_doc.docstatus != 1:
			frappe.throw(
				_("Delivery Challan {0} must be submitted.").format(delivery_challan)
			)
		if delivery_challan_doc.work_order != wo.name:
			frappe.throw(
				_("Delivery Challan {0} does not belong to Work Order {1}.").format(
					delivery_challan, wo.name
				)
			)

	defaults = get_grn_work_order_defaults(work_order, delivery_challan)
	items = _overlay_source_rows(
		defaults.get("items"), movement_rows, target_doctype="Goods Received Note"
	)
	defaults["items"] = items
	defaults["item_details"] = group_items_for_ui(items, "Goods Received Note")
	defaults["cut_panel_movement"] = cpm.name
	if delivery_challan_doc:
		defaults["delivery_challan"] = delivery_challan_doc.name
	if _movement_uses_collapsed(frappe.parse_json(cpm.cut_panel_movement_json)):
		defaults["allow_non_bundle"] = 1
	defaults["against"] = "Work Order"
	defaults["against_id"] = wo.name
	_copy_existing_fields(defaults, wo, "Goods Received Note")
	return defaults


def set_completion_cut_panel_movement(stock_entry):
	"""Carry the CPM link from an internal DC/GRN into its completion leg."""
	if stock_entry.get("cut_panel_movement") or stock_entry.purpose not in _COMPLETION_PURPOSES:
		return
	if not stock_entry.against or not stock_entry.against_id:
		return
	if frappe.get_meta(stock_entry.against).get_field("cut_panel_movement"):
		stock_entry.cut_panel_movement = frappe.db.get_value(
			stock_entry.against, stock_entry.against_id, "cut_panel_movement"
		)


def add_cancel_link_exemptions(doc):
	has_bundle_entries = frappe.db.exists(
		"Cut Bundle Movement Ledger",
		{
			"voucher_type": doc.doctype,
			"voucher_no": doc.name,
			"is_cancelled": 0,
		},
	)
	if (
		not doc.get("cut_panel_movement")
		and not doc.get("allow_non_bundle")
		and not has_bundle_entries
	):
		return
	exemptions = list(doc.get("ignore_linked_doctypes") or ())
	for doctype in ("Cut Bundle Movement Ledger", "Cut Panel Movement"):
		if doctype not in exemptions:
			exemptions.append(doctype)
	doc.ignore_linked_doctypes = tuple(exemptions)


def _bundle_tracking_disabled(lot):
	value = frappe.db.get_single_value("MRP Settings", "cut_bundle_cancelled_lot") or ""
	return lot in {entry.strip() for entry in value.split(",") if entry.strip()}


def _is_implicit_collapsed_return(doc, lot):
	if doc.doctype != "Goods Received Note" or not doc.get("is_return") or not lot:
		return False
	production_detail = frappe.db.get_value("Lot", lot, "production_detail")
	if not production_detail:
		return False
	stage, dependent_attribute = frappe.db.get_value(
		"Item Production Detail",
		production_detail,
		["stiching_in_stage", "dependent_attribute"],
	) or (None, None)
	if not stage or not dependent_attribute:
		return False
	for row in doc.get("items") or []:
		variant = row.get("item_variant")
		if variant and frappe.db.exists(
			"Item Variant Attribute",
			{
				"parent": variant,
				"attribute": dependent_attribute,
				"attribute_value": stage,
			},
		):
			return True
	return False


def _as_supplier(location):
	if not location:
		return None
	if frappe.db.exists("Supplier", location):
		return location
	supplier = frappe.db.get_value("Warehouse", location, "supplier")
	if not supplier:
		frappe.throw(_("Warehouse {0} is not linked to a Supplier.").format(location))
	return supplier


def _movement_locations(doc):
	transit = frappe.db.get_single_value("YRP Stock Settings", "transit_warehouse")
	if doc.doctype == "Delivery Challan":
		source = doc.from_location or doc.from_warehouse
		target = transit if doc.is_internal_unit else (doc.supplier or doc.to_warehouse)
	elif doc.doctype == "Goods Received Note":
		source = doc.supplier or doc.from_warehouse
		target = transit if doc.is_internal_unit else (doc.delivery_location or doc.to_warehouse)
	elif doc.doctype == "Stock Entry":
		if doc.purpose == "Send to Warehouse":
			source = doc.from_warehouse
			target = doc.to_warehouse if doc.skip_transit else transit
		elif doc.purpose in {"Receive at Warehouse", "DC Completion", "GRN Completion"}:
			source = transit
			target = doc.to_warehouse
		else:
			frappe.throw(_("Purpose {0} cannot move cut bundles.").format(doc.purpose))
	else:
		frappe.throw(_("{0} cannot move cut bundles.").format(doc.doctype))
	return _as_supplier(source), _as_supplier(target)


def _cancel_exact_bundle_entries(doc):
	from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
		_collapsed_set_combination_key,
	)

	rows = frappe.get_all(
		"Cut Bundle Movement Ledger",
		filters={
			"voucher_type": doc.doctype,
			"voucher_no": doc.name,
			"is_cancelled": 0,
		},
		fields=["name", "cbm_key", "posting_datetime", "creation", "set_combination"],
	)
	for row in rows:
		future = None
		for candidate in frappe.get_all(
			"Cut Bundle Movement Ledger",
			filters={
				"cbm_key": row.cbm_key,
				"is_cancelled": 0,
				"transformed": 0,
				"collapsed_bundle": 0,
				"is_collapsed": 0,
			},
			fields=["name", "posting_datetime", "creation", "set_combination"],
		):
			if (
				(candidate.posting_datetime, candidate.creation, candidate.name)
				> (row.posting_datetime, row.creation, row.name)
				and _collapsed_set_combination_key(candidate.set_combination)
				== _collapsed_set_combination_key(row.set_combination)
			):
				future = candidate.name
				break
		if future:
			frappe.throw(
				_("Cancel the later cut-bundle movement {0} first.").format(future)
			)
	for row in rows:
		frappe.db.set_value(
			"Cut Bundle Movement Ledger",
			row.name,
			"is_cancelled",
			1,
			update_modified=False,
		)


def apply_transaction(doc, *, cancelled=False):
	"""Apply/reverse only the Essdee bundle trace for a base transaction."""
	cpm_name = doc.get("cut_panel_movement")
	allow_non_bundle = cint(doc.get("allow_non_bundle"))
	# Stock Entries participate in bundle tracking only when the movement was
	# explicitly linked or the caller opted into collapsed-bundle handling.
	# Finishing/dispatch Stock Entries can point at DocTypes that do not expose a
	# Lot field and must remain completely outside the cutting lifecycle.
	if doc.doctype == "Stock Entry" and not cpm_name and not allow_non_bundle:
		return

	lot = doc.get("lot")
	if not lot and doc.doctype == "Stock Entry" and doc.against and doc.against_id:
		against_meta = frappe.get_meta(doc.against)
		if against_meta.get_field("lot"):
			lot = frappe.db.get_value(doc.against, doc.against_id, "lot")
	if not lot and cpm_name:
		lot = frappe.db.get_value("Cut Panel Movement", cpm_name, "lot")
	if not lot or _bundle_tracking_disabled(lot):
		return
	implicit_collapsed_return = _is_implicit_collapsed_return(doc, lot)
	if not cpm_name and not allow_non_bundle and not implicit_collapsed_return:
		return

	if not cpm_name:
		if allow_non_bundle or implicit_collapsed_return:
			from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
				update_collapsed_bundle,
			)

			update_collapsed_bundle(
				doc.doctype,
				doc.name,
				"on_cancel" if cancelled else "on_submit",
				non_stich_process=doc.doctype == "Goods Received Note",
			)
		return

	cpm = frappe.get_doc("Cut Panel Movement", cpm_name)
	if cpm.docstatus != 1:
		frappe.throw(_("Cut Panel Movement {0} must be submitted.").format(cpm.name))

	if cancelled:
		if allow_non_bundle:
			from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
				update_collapsed_bundle,
			)

			update_collapsed_bundle(doc.doctype, doc.name, "on_cancel")
		else:
			_cancel_exact_bundle_entries(doc)
		if cpm.against == doc.doctype and cpm.against_id == doc.name:
			cpm.db_set({"against": None, "against_id": None}, update_modified=False)
		return

	if frappe.db.exists(
		"Cut Bundle Movement Ledger",
		{"voucher_type": doc.doctype, "voucher_no": doc.name, "is_cancelled": 0},
	):
		return

	is_completion = (
		doc.doctype == "Stock Entry" and doc.purpose in _COMPLETION_PURPOSES
	)
	if not is_completion:
		if cpm.against_id and (cpm.against != doc.doctype or cpm.against_id != doc.name):
			frappe.throw(
				_("Cut Panel Movement {0} is already linked to {1} {2}.").format(
					cpm.name, cpm.against, cpm.against_id
				)
			)
		cpm.db_set({"against": doc.doctype, "against_id": doc.name}, update_modified=False)

	if allow_non_bundle:
		from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
			update_collapsed_bundle,
		)

		update_collapsed_bundle(doc.doctype, doc.name, "on_submit")
		return

	from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
		get_cut_bundle_entry,
		make_cut_bundle_ledger,
	)

	source, target = _movement_locations(doc)
	for location, multiplier in ((source, -1), (target, 1)):
		entries, collapsed = get_cut_bundle_entry(cpm, doc, location, multiplier)
		make_cut_bundle_ledger(entries, collapsed)


def before_cancel(doc, method=None):
	del method
	add_cancel_link_exemptions(doc)


def on_submit(doc, method=None):
	del method
	apply_transaction(doc, cancelled=False)


def on_cancel(doc, method=None):
	del method
	apply_transaction(doc, cancelled=True)
