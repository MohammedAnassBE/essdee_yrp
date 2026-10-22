import frappe
from frappe import _
from frappe.utils import flt
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_values import get_mapping_values

from essdee_yrp.finishing.work_order_packing import has_packing_process
from essdee_yrp.production_order_alternative import get_alternative_production_order_issues


def throw_alternative_plan_issues(issues, header=None):
	"""Raise every Alternative Plan blocker in one bulleted message."""
	if not issues:
		return
	frappe.throw(
		(header or _("The Alternative Plan cannot be created yet. Fix the following:"))
		+ "<br>"
		+ "<br>".join(f"• {issue}" for issue in issues),
		title=_("Alternative Plan not ready"),
	)


def get_alternative_plan_issues(
	finishing_plan,
	alternative_item,
	production_detail,
	conversions,
	lot_source="new",
	existing_lot=None,
):
	"""Return the independent pre-checks of creating an Alternative Plan."""
	issues = get_conversion_balance_issues(finishing_plan, conversions)
	issues += get_production_detail_issues(production_detail, alternative_item, conversions, finishing_plan)
	if lot_source == "existing":
		issues += get_existing_lot_issues(existing_lot)
	source_production_order = attribute_db.get_value("SD YRP Lot", finishing_plan.lot, "production_order")
	if not source_production_order:
		issues.append(_("Source Lot {0} has no Production Order").format(finishing_plan.lot))
	else:
		issues += get_alternative_production_order_issues(
			source_production_order,
			finishing_plan.lot,
			alternative_item,
			{_attribute_value(row["size"]) for row in conversions},
		)
	if flt(_production_detail_value(finishing_plan.lot, "packing_combo")) <= 0:
		issues.append(_("Source Lot {0} has no valid Packing Combo").format(finishing_plan.lot))
	return issues


def get_conversion_balance_issues(finishing_plan, conversions):
	data = finishing_plan.get_finishing_plans()["finishing_qty"]["data"]
	issues = []
	for row in conversions:
		colour = _attribute_value(row["colour"])
		size = _attribute_value(row["size"])
		values = ((data.get(colour) or {}).get("values") or {}).get(size) or {}
		available = flt(values.get("balance"))
		if row["qty"] > available + 1e-6:
			issues.append(
				_("{0} / {1}: converting {2}, but only {3} is available").format(
					colour, size, f"{flt(row['qty'], 3):g}", f"{available:g}"
				)
			)
	return issues


def get_production_detail_issues(production_detail, alternative_item, conversions, finishing_plan):
	if not frappe.db.exists("YRP Item Production Detail", production_detail):
		return [_("Item Production Detail {0} does not exist").format(production_detail)]
	ipd = frappe.get_cached_doc("YRP Item Production Detail", production_detail)
	issues = []
	if ipd.item != alternative_item:
		issues.append(
			_("Item Production Detail {0} belongs to {1}, not {2}").format(
				ipd.name, ipd.item, alternative_item
			)
		)
	if ipd.is_set_item:
		issues.append(
			_("Item Production Detail {0} is a Set Item; Set Items cannot be alternatives").format(ipd.name)
		)
	if flt(ipd.packing_combo) <= 0:
		issues.append(_("Item Production Detail {0} has no Packing Combo").format(ipd.name))
	issues += get_packing_process_issues(ipd, finishing_plan)
	mappings = {row.attribute: row.mapping for row in ipd.get("item_attributes") or []}
	for attribute, field in ((ipd.packing_attribute, "colour"), (ipd.primary_item_attribute, "size")):
		issues += get_attribute_value_issues(ipd, attribute, mappings.get(attribute), conversions, field)
	return issues


def get_attribute_value_issues(ipd, attribute, mapping, conversions, field):
	"""List each converted colour or size that the IPD mapping does not contain."""
	if not attribute or not mapping:
		return [_("Item Production Detail {0} has no {1} mapping").format(ipd.name, attribute or field)]
	allowed = set(get_mapping_values(mapping))
	converting = sorted({_attribute_value(row[field]) for row in conversions})
	return [
		_("{0} {1} is not in Item Production Detail {2}").format(attribute, value, ipd.name)
		for value in converting
		if value not in allowed
	]


def get_packing_process_issues(ipd, finishing_plan):
	process_name = frappe.db.get_value("YRP Work Order", finishing_plan.work_order, "process_name")
	if has_packing_process(process_name, ipd.packing_process):
		return []
	return [
		_("Work Order process {0} does not include packing process {1} of Item Production Detail {2}").format(
			process_name, ipd.packing_process, ipd.name
		)
	]


def get_existing_lot_issues(existing_lot):
	if not existing_lot:
		return [_("Select an existing Lot")]
	if not frappe.db.exists("SD YRP Lot", existing_lot):
		return [_("Lot {0} does not exist").format(existing_lot)]
	problems = get_configured_lot_problems(frappe.get_doc("SD YRP Lot", existing_lot))
	if not problems:
		return []
	return [_("Lot {0} is already configured ({1})").format(existing_lot, ", ".join(problems))]


def get_configured_lot_problems(lot_doc):
	problems = []
	if lot_doc.production_detail:
		problems.append(_("Item Production Detail"))
	if lot_doc.production_order:
		problems.append(_("Production Order"))
	if lot_doc.item:
		problems.append(_("Item"))
	if lot_doc.get("lot_order_details"):
		problems.append(_("Lot Order Details"))
	if lot_doc.get("items"):
		problems.append(_("Items"))
	if lot_doc.status == "Closed":
		problems.append(_("Status is Closed"))
	return problems


def _production_detail_value(lot, fieldname):
	production_detail = attribute_db.get_value("SD YRP Lot", lot, "production_detail")
	return attribute_db.get_value("YRP Item Production Detail", production_detail, fieldname)
