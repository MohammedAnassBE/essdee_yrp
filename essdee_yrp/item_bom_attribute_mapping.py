"""Essdee Desk combination source for Item BOM Attribute Mapping.

Base YRP can generate a Cartesian product from the Item master's attribute
values. Essdee garment colours, however, are owned by the linked Item
Production Detail (IPD), and the IPD combination engine also preserves
non-Cartesian relationships between attributes. The Desk adapter calls this
module whenever an Item BOM Attribute Mapping belongs to an IPD.
"""

from __future__ import annotations

from collections.abc import Sequence

import frappe
from frappe import _

from essdee_yrp import ipd_ui


def _as_attribute_list(value, label: str) -> list[str]:
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if value is None:
		return []
	if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
		frappe.throw(_("{0} must be a list").format(label))

	attributes = []
	for attribute in value:
		if not isinstance(attribute, str) or not attribute.strip():
			frappe.throw(_("{0} contains an invalid attribute").format(label))
		attribute = attribute.strip()
		if attribute not in attributes:
			attributes.append(attribute)
	return attributes


def _build_mapping_rows(
	combination_data: dict,
	item_attributes: list[str],
	bom_attributes: list[str],
) -> list[dict]:
	rows = []
	seen = set()
	for source in combination_data.get("items") or []:
		key = tuple(source.get(attribute) for attribute in item_attributes)
		if any(value in (None, "") for value in key):
			continue
		if key in seen:
			continue
		seen.add(key)

		row = {
			f"item_{attribute}": source.get(attribute)
			for attribute in item_attributes
		}
		row.update({f"bom_{attribute}": None for attribute in bom_attributes})
		row["quantity"] = 0
		row["included"] = True
		rows.append(row)
	return rows


@frappe.whitelist()
def get_item_bom_mapping_combinations(
	ipd: str,
	item: str,
	item_attributes=None,
	bom_attributes=None,
):
	"""Return the exact Cutting combinations for an IPD-backed BOM mapping."""

	item_attributes = _as_attribute_list(item_attributes, _("Item Attributes"))
	bom_attributes = _as_attribute_list(bom_attributes, _("BOM Item Attributes"))
	if not item_attributes:
		return []
	if not ipd:
		frappe.throw(_("Item Production Detail is required to generate combinations"))

	ipd_doc = frappe.get_doc("Item Production Detail", ipd)
	ipd_doc.check_permission("read")
	if item and ipd_doc.item != item:
		frappe.throw(
			_("Item Production Detail {0} belongs to Item {1}, not {2}").format(
				frappe.bold(ipd_doc.name),
				frappe.bold(ipd_doc.item),
				frappe.bold(item),
			)
		)

	combination_data = ipd_ui.get_combination(
		ipd_doc.name,
		item_attributes,
		"Cutting",
	)
	available_attributes = set(combination_data.get("attributes") or [])
	missing_attributes = [
		attribute for attribute in item_attributes if attribute not in available_attributes
	]
	if missing_attributes:
		frappe.throw(
			_("IPD {0} cannot generate the selected attribute(s): {1}").format(
				frappe.bold(ipd_doc.name),
				frappe.bold(", ".join(missing_attributes)),
			)
		)

	rows = _build_mapping_rows(combination_data, item_attributes, bom_attributes)
	if not rows:
		frappe.throw(
			_("IPD {0} has no valid combinations for: {1}").format(
				frappe.bold(ipd_doc.name),
				frappe.bold(", ".join(item_attributes)),
			)
		)
	return rows
