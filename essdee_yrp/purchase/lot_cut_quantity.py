import frappe
from frappe import _
from yrp.utils import update_if_string_instance

LOT_CUT_QUANTITY_ROLES = frozenset({"Purchase User", "Purchase Manager", "System Manager"})
MAXIMUM_LOTS = 20


def can_view_lot_cut_quantity():
	return bool(LOT_CUT_QUANTITY_ROLES.intersection(frappe.get_roles()))


def _normalise_lots(lots):
	if isinstance(lots, str):
		try:
			lots = frappe.parse_json(lots)
		except (TypeError, ValueError):
			frappe.throw(_("Lots must be provided as a JSON list."), frappe.ValidationError)
	if not isinstance(lots, (list, tuple)):
		frappe.throw(_("Lots must be provided as a list."), frappe.ValidationError)

	names = []
	seen = set()
	for value in lots:
		name = str(value or "").strip()
		if name and name not in seen:
			seen.add(name)
			names.append(name)
	return names


def _validate_lots(lots):
	names = _normalise_lots(lots)
	if not names:
		frappe.throw(_("Select at least one Lot."), frappe.ValidationError)
	if len(names) > MAXIMUM_LOTS:
		frappe.throw(
			_("Select no more than {0} Lots.").format(MAXIMUM_LOTS),
			frappe.ValidationError,
		)
	return names


def _get_lot_plans(lot):
	plans = frappe.get_all(
		"SD YRP Cutting Plan",
		filters={"lot": lot, "docstatus": ["<", 2]},
		fields=["name", "item", "version", "docstatus", "completed_items_json"],
		order_by="creation asc, name asc",
	)
	return [
		{
			"name": plan["name"],
			"item": plan["item"],
			"version": plan["version"],
			"completed_items": update_if_string_instance(plan["completed_items_json"]),
		}
		for plan in plans
	]


@frappe.whitelist(methods=["GET", "POST"])
def get_lot_cut_quantity(lots):
	"""Return stored completed-cut matrices for permitted Lots."""
	if not can_view_lot_cut_quantity():
		frappe.throw(_("You do not have permission to view Lot Cut Quantity."), frappe.PermissionError)
	lot_names = _validate_lots(lots)

	result = []
	for lot_name in lot_names:
		lot = frappe.get_doc("SD YRP Lot", lot_name)
		if not frappe.has_permission("SD YRP Lot", "read", doc=lot):
			frappe.throw(
				_("You do not have permission to read Lot {0}.").format(lot_name),
				frappe.PermissionError,
			)
		result.append({"lot": lot_name, "cutting_plans": _get_lot_plans(lot_name)})
	return {"lots": result}
