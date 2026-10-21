import frappe
from frappe import _
from frappe.utils import flt
from yrp.yrp.utils import ipd_engine

from essdee_yrp import production_order_workflow
from essdee_yrp.api import cloth_program
from essdee_yrp.cloth_program_access import has_cloth_program_role
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot import sd_yrp_lot
from essdee_yrp.garment_bom_matrix import is_on_demand_garment_ipd
from essdee_yrp.purchase import lot_editor, lot_workspace
from essdee_yrp.web_common import action, assert_expected_modified, parse_mapping, permission_flags

DOCTYPE = "SD YRP Lot"
IPD_FACTS = ("tech_pack_version", "pattern_version", "packing_combo")
BOM_FIELDS = ("name", "item_name", "process_name", "uom", "required_qty")
COMMAND_LABELS = {
	"build_cloth_programs": "Build Cloth Program",
	"recalculate_cloth_program": "Recalculate Cloth Program",
	"calculate_bom": "Calculate BOM",
	"calculate_order_items": "Calculate Order Items",
	"change_ppo": "Change PPO",
	"update_bom_additional_items": "Edit BOM Additional Items",
}
BOX_LABELS = {"qty": "Qty", "ratio": "Ratio", "mrp": "MRP"}


def is_order_locked(doc):
	return bool(doc.get("lot_time_and_action_details") or doc.get("is_transferred"))


def get_cloth_block(doc):
	if doc.docstatus == 2:
		return _("The Lot is cancelled.")
	if doc.get("is_transferred"):
		return _("The Lot was transferred.")
	if not doc.production_detail:
		return _("Select an Item Production Detail first.")
	return ""


def get_build_block(doc):
	if reason := get_cloth_block(doc):
		return reason
	if not any(flt(row.quantity) > 0 for row in doc.get("lot_order_details") or []):
		return _("Run Calculate Order Items first.")
	try:
		demand = cloth_program.compute_cloth_demand(doc.name, apply_allowance=False)
	except frappe.ValidationError as error:
		return str(error)
	return "" if demand else _("Run Calculate Order Items first: no cloth demand.")


def get_command_blocks(doc):
	return {
		"build_cloth_programs": get_build_block(doc),
		"recalculate_cloth_program": get_cloth_block(doc)
		or ("" if doc.get("lot_fabric_details") else _("No Fabric Details exist.")),
		"calculate_bom": get_bom_block(doc),
		"calculate_order_items": _("Time & Action exists.")
		if doc.get("lot_time_and_action_details")
		else get_cloth_block(doc),
		"change_ppo": _("Already linked to {0}").format(doc.production_order) if doc.production_order else "",
		"update_bom_additional_items": "" if doc.docstatus == 0 else _("The Lot must be in Draft."),
	}


def get_bom_block(doc):
	if doc.docstatus != 0:
		return _("The Lot must be in Draft.")
	if not doc.production_detail:
		return _("Select an Item Production Detail first.")
	if not any(flt(row.quantity) > 0 for row in doc.get("lot_order_details") or []):
		return _("Run Calculate Order Items first.")
	if is_on_demand_garment_ipd(doc.production_detail):
		return ""
	if not ipd_engine._get_process_matrices(doc.production_detail):
		return _("No IPD Process Matrix found for IPD {0}.").format(doc.production_detail)
	return ""


def get_lot_capabilities(doc):
	can_write = permission_flags(DOCTYPE, ("write",), doc)["can_write"]
	can_change_ppo = can_write and production_order_workflow.user_can_manage_production_order()
	can_manage_cloth_program = can_write and has_cloth_program_role()
	blocks = (
		get_command_blocks(doc)
		if can_write
		else dict.fromkeys(COMMAND_LABELS, _("Write permission required."))
	)
	capabilities = {"edit": {**action(can_write, _("Edit")), "visible": can_write}}
	for command, label in COMMAND_LABELS.items():
		visible = can_change_ppo if command == "change_ppo" else can_write
		if command in ("build_cloth_programs", "recalculate_cloth_program"):
			visible = can_manage_cloth_program
		capabilities[command] = {
			**action(visible and not blocks[command], _(label), blocks[command]),
			"visible": visible,
		}
	return capabilities


def get_ppo_lot_quantities(rows):
	reference_lots = {row.get("reference_name") for row in rows if row.get("reference_doctype") == DOCTYPE}
	quantities = {}
	for row in rows:
		is_reference = row.get("reference_doctype") == DOCTYPE
		name = row.get("reference_name") if is_reference else row.get("lot")
		if not name or (not is_reference and name in reference_lots):
			continue
		quantities[name] = quantities.get(name, 0) + flt(row.quantity)
	return quantities


def get_ppo_block(doc):
	if not doc.production_order:
		return None
	production_order = frappe.get_doc("YRP Production Order", doc.production_order)
	if not frappe.has_permission("YRP Production Order", "read", doc=production_order):
		return {"name": doc.production_order}
	quantities = get_ppo_lot_quantities(production_order.get("production_ordered_details") or [])
	return {
		"name": production_order.name,
		"status": production_order.status,
		"delivery_date": production_order.delivery_date,
		"item": production_order.item,
		"quantity": sum(flt(row.quantity) for row in production_order.get("production_order_details") or []),
		"lot_quantity": quantities.get(doc.name, 0),
		"other_lots": [
			{"name": name, "quantity": quantity} for name, quantity in quantities.items() if name != doc.name
		],
	}


@frappe.whitelist()
def get_merch_lot_workspace(name: str) -> dict:
	payload = lot_workspace.get_lot_workspace(name)
	doc = frappe.get_doc(DOCTYPE, name)
	return {
		**payload,
		"capabilities": get_lot_capabilities(doc),
		"ppo": get_ppo_block(doc),
		"header": get_record_facts(doc, lot_workspace.HEADER_FIELDS),
		"details": get_record_facts(doc, lot_workspace.ORDER_DETAIL_FACTS + lot_workspace.BOM_FACTS),
		"ipd_facts": get_record_facts(doc, IPD_FACTS),
		"locks": {"order_details": is_order_locked(doc)},
		"bom_additional_items": [
			{field: row.get(field) for field in BOM_FIELDS} for row in doc.get("bom_additional_items") or []
		],
	}


def get_record_facts(doc, fields):
	facts = lot_workspace.get_facts(doc, fields)
	present = {field["fieldname"] for field in facts}
	for fieldname in fields:
		if fieldname in present:
			continue
		field = doc.meta.get_field(fieldname)
		facts.append(
			{
				"fieldname": fieldname,
				"label": field.label,
				"fieldtype": field.fieldtype,
				"value": 0 if field.fieldtype in ("Check", "Int", "Float", "Percent") else doc.get(fieldname),
				**lot_workspace.link_fact_metadata(doc, field),
			}
		)
	return facts


@frappe.whitelist()
def get_merch_lot_editor(name: str | None = None) -> dict:
	payload = lot_editor.get_lot_form(name)
	doc = lot_editor.load_writable_lot(name)
	if name:
		payload["locks"]["production_order"] = True
		for field in payload["fields"]:
			if field["fieldname"] == "production_order":
				field["read_only"] = True
	payload["derived"].update({field: doc.get(field) for field in IPD_FACTS})
	payload["box_locked"] = is_order_locked(doc) or bool(
		doc.production_order and doc.get("lot_order_details")
	)
	payload["workspace"] = (
		{
			"order_details": lot_workspace.get_order_details(doc),
			"fabrics": lot_workspace.get_fabrics(doc),
			"other_conversions": lot_workspace.get_other_conversions(doc),
		}
		if name
		else {}
	)
	return payload


def box_values(details):
	return [
		{
			"item": group.get("item"),
			"dependent_attribute": group.get("dependent_attribute"),
			"final_state": group.get("final_state"),
			"items": [
				{
					"attributes": row["attributes"],
					"primary_attribute": row.get("primary_attribute"),
					"values": row["values"],
				}
				for row in group.get("items", [])
			],
		}
		for group in details
		if group.get("items")
	]


def reject_locked_boxes(doc, values):
	if not is_order_locked(doc):
		return
	stored = sd_yrp_lot.fetch_item_details(doc.items, doc.production_detail) if doc.items else None
	incoming = box_values(values.get("item_details") or [])
	if lot_editor.normalise_order_numbers(incoming) != lot_editor.normalise_order_numbers(
		box_values([stored] if stored else [])
	):
		frappe.throw(
			_("Locked: Time & Action exists or the Lot was transferred. Box quantities cannot be changed.")
		)


def reject_negative_boxes(details):
	for group in details:
		for index, row in enumerate(group.get("items") or [], 1):
			values = row.get("values") or {}
			cells = [values] if any(field in values for field in BOX_LABELS) else values.values()
			for cell in cells:
				for field, label in BOX_LABELS.items():
					if flt(cell.get(field)) < 0:
						frappe.throw(
							_("Order Items row {0}: {1} cannot be negative.").format(index, _(label))
						)


def reject_removed_order_items(doc, values):
	if doc.get("lot_order_details") and not values.get("order_item_details"):
		frappe.throw(_("Order Items cannot be removed here."))


@frappe.whitelist(methods=["POST"])
def save_merch_lot(values, name: str | None = None, expected_modified: str | None = None) -> dict:
	values = parse_mapping(values, _("Lot values"))
	doc = lot_editor.load_writable_lot(name)
	if name:
		assert_expected_modified(doc, expected_modified)
		if (values.get("production_order", doc.production_order) or "") != (doc.production_order or ""):
			frappe.throw(_("Use Change PPO to link an existing Lot to a Production Order."))
	reject_negative_boxes(values.get("item_details") or [])
	if name:
		reject_locked_boxes(doc, values)
		reject_removed_order_items(doc, values)
	result = lot_editor.save_lot(values, name=name, expected_modified=expected_modified)
	return get_merch_lot_workspace(result["name"])


def update_bom_additional_items(doc, rows):
	if not isinstance(rows, list):
		frappe.throw(_("BOM Additional Items must be a list."))
	stored = {row.name: row for row in doc.get("bom_additional_items") or []}
	seen = set()
	for index, row in enumerate(rows, 1):
		validate_additional_row(row, index, stored, seen)
	doc.set("bom_additional_items", [])
	for row in rows:
		child = doc.append("bom_additional_items", stored.get(row.get("name"), {}))
		for field in BOM_FIELDS[1:]:
			child.set(field, row.get(field))
	doc.save()


def validate_additional_row(row, index, stored, seen):
	if not isinstance(row, dict):
		frappe.throw(_("Invalid BOM Additional Items row {0}.").format(index))
	name = row.get("name")
	if name and (name not in stored or name in seen):
		frappe.throw(_("Unknown or duplicate BOM Additional Items row: {0}").format(name))
	seen.add(name)
	for field in BOM_FIELDS[1:]:
		if not row.get(field):
			label = frappe.get_meta("SD YRP Lot BOM").get_label(field)
			frappe.throw(_("Row {0}: {1} is required.").format(index, label))
	if flt(row["required_qty"]) <= 0:
		frappe.throw(_("Row {0}: Required Qty must be greater than zero.").format(index))


def run_lot_command(doc, command, payload, expected_modified):
	if command == "build_cloth_programs":
		return cloth_program.build_cloth_programs(
			doc.name,
			payload.get("selections"),
			modified=expected_modified,
			excess_percentage=payload.get("excess_percentage", 0),
		)
	if command == "recalculate_cloth_program":
		return cloth_program.recalculate_cloth_program(doc.name, modified=expected_modified)
	if command == "calculate_bom":
		return sd_yrp_lot.calculate_bom(doc.name)
	if command == "calculate_order_items":
		return sd_yrp_lot.update_order_details(doc.name)
	if command == "change_ppo":
		return change_ppo(doc, payload.get("production_order"))
	return update_bom_additional_items(doc, payload.get("rows"))


def change_ppo(doc, production_order):
	if not production_order:
		frappe.throw(_("Production Order is required."))
	order = frappe.get_doc("YRP Production Order", production_order)
	order.check_permission("read")
	if order.docstatus != 1 or (doc.item and order.item != doc.item):
		frappe.throw(_("Select a submitted Production Order for this Item."))
	return production_order_workflow.link_lot(production_order, doc.name)


@frappe.whitelist(methods=["POST"])
def execute_merch_lot_command(name: str, command: str, payload=None, expected_modified=None) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	capability = get_lot_capabilities(doc).get(command)
	if command not in COMMAND_LABELS or not capability or not capability["allowed"]:
		frappe.throw(_("This Lot action is not permitted."), frappe.PermissionError)
	run_lot_command(doc, command, parse_mapping(payload or {}, _("Lot command")), expected_modified)
	return get_merch_lot_workspace(name)
