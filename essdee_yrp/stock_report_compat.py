"""Source presentation rules shared by the two legacy lot stock reports."""

import frappe
from frappe.utils import flt


def item_group_aliases(groups=None):
	"""Recognize copied M_ groups only when their original group still exists."""
	if groups is None:
		groups = frappe.get_all("Item Group", fields=["name", "parent_item_group", "is_group"])
	names = {row.name for row in groups}
	return {name: name[2:] if name.startswith("M_") and name[2:] in names else name for name in names}


def mrp_flt(value, precision=None):
	"""MRP's unset rounding method uses Frappe's legacy half-tie behavior."""
	return flt(value, precision, rounding_method="Banker's Rounding (legacy)")
