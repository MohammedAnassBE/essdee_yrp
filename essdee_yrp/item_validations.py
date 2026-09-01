"""Item-master validation owned by the Essdee YRP customization layer."""

import frappe
from frappe import _
from frappe.utils import cint, flt


def validate(doc, method=None):
	"""Require a complete reusable yarn recipe whenever Item is a cloth."""
	if getattr(doc.flags, "skip_cloth_yarn_ratio_validation", False):
		return
	if not cint(doc.get("is_cloth_item")):
		return
	_validate_yarn_rows(doc.get("yarn_ratio_details") or [], cloth_item=doc.name)


def validate_sync_payload(data):
	"""Validate Item yarn rows before the DB-level SD YRP sync bypasses hooks.

	Older producers do not send ``yarn_ratio_details``. In that case the
	consumer preserves its current value and skips this check. Once the field is
	present in the payload, a cloth Item must carry a complete 100% recipe.
	"""
	if "yarn_ratio_details" not in data:
		return
	if not cint(data.get("is_cloth_item")) and not data.get("yarn_ratio_details"):
		return
	_validate_yarn_rows(
		data.get("yarn_ratio_details") or [],
		cloth_item=data.get("name"),
	)


def _validate_yarn_rows(rows, cloth_item=None):
	if not rows:
		frappe.throw(_("Add at least one Yarn Ratio row for a Cloth Item."))

	seen = set()
	total = 0.0
	for index, row in enumerate(rows, 1):
		row_number = row.get("idx") or index
		yarn_item = row.get("yarn_item")
		ratio = flt(row.get("ratio"))
		if not yarn_item:
			frappe.throw(_("Row {0}: select a Yarn Item.").format(row_number))
		if yarn_item == cloth_item:
			frappe.throw(
				_("Row {0}: a Cloth Item cannot use itself as yarn.").format(row_number)
			)
		if yarn_item in seen:
			frappe.throw(
				_("Row {0}: Yarn Item {1} is duplicated.").format(
					row_number, yarn_item
				)
			)
		if ratio <= 0:
			frappe.throw(
				_("Row {0}: Ratio must be greater than zero.").format(row_number)
			)
		if (
			frappe.get_meta("Item").has_field("is_cloth_item")
			and frappe.db.get_value("Item", yarn_item, "is_cloth_item")
		):
			frappe.throw(
				_("Row {0}: Cloth Item {1} cannot be selected as yarn.").format(
					row_number, yarn_item
				)
			)
		attributes = set(frappe.get_all(
			"Item Item Attribute",
			filters={"parent": yarn_item, "parenttype": "Item"},
			pluck="attribute",
		))
		unsupported = sorted(attributes - {"Colour"})
		if unsupported:
			frappe.throw(
				_(
					"Row {0}: Yarn Item {1} may only use the Colour variant "
					"attribute; remove {2}."
				).format(row_number, yarn_item, ", ".join(unsupported))
			)
		seen.add(yarn_item)
		total += ratio

	if abs(total - 100.0) > 0.001:
		frappe.throw(
			_("Yarn Ratio total must be exactly 100%. Current total is {0}%.").format(
				flt(total, 3)
			)
		)
