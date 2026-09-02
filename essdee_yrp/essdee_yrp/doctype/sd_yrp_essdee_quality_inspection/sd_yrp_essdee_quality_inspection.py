# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from yrp.utils import get_variant_attr_details, update_if_string_instance


VALID_RESULTS = {"Pass", "Fail", "Hold"}
VALID_CHECKING_LEVELS = {"Level 1", "Level 2"}


class SDYRPEssdeeQualityInspection(Document):
	def onload(self):
		self.set_onload(
			"colour_size_data",
			{
				"colours": [
					{"colour": row.colour, "selected": bool(row.selected)}
					for row in self.essdee_quality_inspection_colours
				],
				"sizes": [
					{"size": row.size, "selected": bool(row.selected)}
					for row in self.essdee_quality_inspection_sizes
				],
			},
		)
		self.set_onload(
			"debit_details",
			[] if self.is_new() else get_debit_details(self.name),
		)

	def before_validate(self):
		if flt(self.offer_qty) <= 0:
			frappe.throw(_("Offer Qty must be greater than zero."))

		limits = _get_aql_limits(
			self.checking_level,
			self.offer_qty,
			self.major_aql_level,
			self.minor_aql_level,
		)
		self.sample_piece_count = limits["sample"]
		self.major_defect_maximum_allowed = limits["major_allowed"]
		self.minor_defect_maximum_allowed = limits["minor_allowed"]

		selection = self.get("colour_and_size_data")
		if selection:
			selection = update_if_string_instance(selection)
			self.set(
				"essdee_quality_inspection_colours",
				[
					{"colour": row.get("colour"), "selected": cint(row.get("selected"))}
					for row in selection.get("colours") or []
					if row.get("colour")
				],
			)
			self.set(
				"essdee_quality_inspection_sizes",
				[
					{"size": row.get("size"), "selected": cint(row.get("selected"))}
					for row in selection.get("sizes") or []
					if row.get("size")
				],
			)

		calculated_result = (
			"Pass"
			if cint(self.major_defect_found) <= cint(self.major_defect_maximum_allowed)
			and cint(self.minor_defect_found) <= cint(self.minor_defect_maximum_allowed)
			else "Fail"
		)
		if not self.result or self.result == self.calculated_result:
			self.result = calculated_result
		self.calculated_result = calculated_result

		work_order = _get_work_order(self.against, self.against_id)
		self.order_qty = _selected_order_quantity(work_order, self)

	def before_submit(self):
		if self.result not in VALID_RESULTS:
			frappe.throw(_("Result must be Pass, Fail, or Hold."))

		self.inspector = frappe.session.user
		self.inspector_name = frappe.db.get_value(
			"User", frappe.session.user, "full_name"
		)


def get_debit_details(quality_inspection: str) -> list[dict]:
	"""Return visible active Debit requests created from one inspection."""

	if not frappe.get_meta('YRP Debit').has_field("quality_inspection"):
		return []
	if not frappe.has_permission('YRP Debit', "read"):
		return []

	return frappe.get_list(
		'YRP Debit',
		filters={
			"quality_inspection": quality_inspection,
			"docstatus": ["!=", 2],
		},
		fields=[
			"name",
			"debit_type",
			"debit_no",
			"debit_value",
			"reason",
			"debit_document",
			"status",
			"approved_by",
			"creation",
		],
		order_by="creation desc",
	)


@frappe.whitelist()
def get_max_minor_defect_allowed(
	level: str,
	offer_qty: int,
	major_aql_level: str,
	minor_aql_level: str,
) -> dict:
	_require_quality_access()
	return _get_aql_limits(level, offer_qty, major_aql_level, minor_aql_level)


@frappe.whitelist()
def get_against_details(against: str, against_id: str) -> dict:
	_require_quality_access()
	work_order = _get_work_order(against, against_id)
	colours, sizes = _fetch_colours_and_sizes(work_order)
	return {
		"colours": colours,
		"sizes": sizes,
		"supplier": work_order.supplier,
		"lot": work_order.lot,
		"item": work_order.item,
		"order_qty": sum(
			flt(row.delivered_quantity)
			for row in work_order.get("work_order_calculated_items") or []
		),
	}


@frappe.whitelist()
def get_default_aql_level() -> dict:
	_require_quality_access()
	return {
		"major": frappe.db.get_single_value(
			'SD YRP MRP Settings', "default_major_aql_level"
		),
		"minor": frappe.db.get_single_value(
			'SD YRP MRP Settings', "default_minor_aql_level"
		),
	}


@frappe.whitelist()
def create_inspection_debit(
	quality_inspection: str,
	debit_value: float,
	reason: str,
	debit_document: str,
) -> dict:
	"""Create the mapped base-YRP Debit through an inspection-authorized action."""

	inspection = frappe.get_doc('SD YRP Essdee Quality Inspection', quality_inspection)
	inspection.check_permission("read")
	if inspection.docstatus != 1:
		frappe.throw(_("Submit the Quality Inspection before creating a Debit."))

	request_role = frappe.db.get_single_value('YRP YRP Settings', "debit_request_role")
	if not request_role or request_role not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("You do not have permission to request a Debit."))

	if flt(debit_value) <= 0:
		frappe.throw(_("Debit Value must be greater than zero."))
	if not reason:
		frappe.throw(_("Reason is required."))
	if not debit_document:
		frappe.throw(_("Debit Document is required."))

	debit = frappe.get_doc(
		{
			"doctype": 'YRP Debit',
			"work_order": inspection.against_id,
			"debit_type": "Permanent",
			"debit_value": debit_value,
			"reason": reason,
			"debit_document": debit_document,
			"inspection": 1,
			"quality_inspection": inspection.name,
		}
	)
	# The configured request role is the authoritative permission, matching the
	# base Debit.create_debit endpoint. Document validation and submission still run.
	debit.insert(ignore_permissions=True)
	debit.submit()
	return debit.as_dict()


def _require_quality_access() -> None:
	if not (
		frappe.has_permission('SD YRP Essdee Quality Inspection', "read")
		or frappe.has_permission('SD YRP Essdee Quality Inspection', "create")
	):
		frappe.throw(_("You do not have access to Quality Inspection."), frappe.PermissionError)


def _get_work_order(against: str, against_id: str):
	if against != 'YRP Work Order' or not against_id:
		frappe.throw(_("Quality Inspection must be against a Work Order."))
	work_order = frappe.get_doc('YRP Work Order', against_id)
	work_order.check_permission("read")
	return work_order


def _get_aql_limits(
	level: str,
	offer_qty: int,
	major_aql_level: str,
	minor_aql_level: str,
) -> dict:
	if level not in VALID_CHECKING_LEVELS:
		frappe.throw(_("Checking Level must be Level 1 or Level 2."))
	if not major_aql_level or not minor_aql_level:
		frappe.throw(_("Major AQL Level and Minor AQL Level are required."))

	quantity = cint(offer_qty)
	major = _matching_aql_row(major_aql_level, quantity)
	minor = _matching_aql_row(minor_aql_level, quantity)
	level_suffix = "1" if level == "Level 1" else "2"
	return {
		"sample": cint(major.get(f"sample_qty_level_{level_suffix}")),
		"major_allowed": cint(major.get(f"level_{level_suffix}")),
		"minor_allowed": cint(minor.get(f"level_{level_suffix}")),
	}


def _matching_aql_row(aql_level: str, offer_qty: int):
	doc = frappe.get_cached_doc('SD YRP AQL Level', aql_level)
	for row in doc.get("aql_level_limit_details") or []:
		if cint(row.min_qty) <= offer_qty <= cint(row.max_qty):
			return row
	# Preserve the reviewed F15 contract: an uncovered quantity produces zero
	# sample/allowance values. Historical inspections rely on this behavior.
	return frappe._dict()


def _fetch_colours_and_sizes(work_order) -> tuple[list[dict], list[dict]]:
	config = _inspection_attributes(work_order)
	colours = []
	sizes = []
	seen_colours = set()
	seen_sizes = set()

	for row in work_order.get("work_order_calculated_items") or []:
		if flt(row.delivered_quantity) == 0:
			continue
		attributes = get_variant_attr_details(row.item_variant)
		colour = _display_colour(attributes, row, config)
		size = attributes.get(config["size_attribute"])
		if colour and colour not in seen_colours:
			seen_colours.add(colour)
			colours.append({"colour": colour, "selected": False})
		if size and size not in seen_sizes:
			seen_sizes.add(size)
			sizes.append({"size": size, "selected": False})

	return colours, sizes


def _selected_order_quantity(work_order, inspection) -> float:
	config = _inspection_attributes(work_order)
	selected_colours = {
		row.colour
		for row in inspection.get("essdee_quality_inspection_colours") or []
		if row.selected
	}
	selected_sizes = {
		row.size
		for row in inspection.get("essdee_quality_inspection_sizes") or []
		if row.selected
	}
	quantity = 0.0

	for row in work_order.get("work_order_calculated_items") or []:
		if flt(row.delivered_quantity) == 0:
			continue
		attributes = get_variant_attr_details(row.item_variant)
		colour = _display_colour(attributes, row, config)
		size = attributes.get(config["size_attribute"])
		if colour in selected_colours and size in selected_sizes:
			quantity += flt(row.delivered_quantity)

	return quantity


def _inspection_attributes(work_order) -> dict:
	if not work_order.production_detail:
		frappe.throw(_("Work Order {0} has no Item Production Detail.").format(work_order.name))

	values = frappe.db.get_value(
		'YRP Item Production Detail',
		work_order.production_detail,
		[
			"primary_item_attribute",
			"packing_attribute",
			"is_set_item",
			"set_item_attribute",
			"major_attribute_value",
		],
		as_dict=True,
	)
	if not values or not values.primary_item_attribute or not values.packing_attribute:
		frappe.throw(
			_("Item Production Detail {0} is missing Size/Colour configuration.").format(
				work_order.production_detail
			)
		)
	return {
		"size_attribute": values.primary_item_attribute,
		"colour_attribute": values.packing_attribute,
		"is_set_item": cint(values.is_set_item),
		"set_attribute": values.set_item_attribute,
		"major_attribute_value": values.major_attribute_value,
	}


def _display_colour(attributes: dict, row, config: dict) -> str | None:
	colour = attributes.get(config["colour_attribute"])
	if not colour or not config["is_set_item"]:
		return colour
	if attributes.get(config["set_attribute"]) == config["major_attribute_value"]:
		return colour
	combination = update_if_string_instance(row.set_combination)
	major_colour = combination.get("major_colour")
	return f"{colour}({major_colour})" if major_colour else colour


EssdeeQualityInspection = SDYRPEssdeeQualityInspection
