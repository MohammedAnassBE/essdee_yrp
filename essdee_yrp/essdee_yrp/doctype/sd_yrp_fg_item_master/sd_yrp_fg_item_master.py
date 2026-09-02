# Copyright (c) 2026, Essdee and contributors

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_item_size_range.sd_yrp_fg_item_size_range import (
	get_sizes,
)
from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant, rename_item
from yrp.yrp.doctype.yrp_item_dependent_attribute_mapping.yrp_item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)


class SDYRPFGItemMaster(Document):
	def validate(self):
		if frappe.flags.in_patch:
			return
		self.validate_sizes()
		self.available_sizes = ",".join(
			row.attribute_value for row in self.sizes if row.attribute_value
		)

	def validate_sizes(self):
		if not self.size_range:
			frappe.throw(_("Please set Size Range."))
		expected = get_sizes(self.size_range)
		current = [row.attribute_value for row in self.sizes if row.attribute_value]
		if current != expected:
			self.set("sizes", [{"attribute_value": size} for size in expected])

	def sync_item(self, rename=False):
		"""Create/update the local F16 Item and every configured Size variant.

		The retired OMS/DC HTTP calls are deliberately not hidden in this method.
		If an external integration is approved later it must be a separate,
		explicit service; local master generation remains deterministic.
		"""
		if self.is_temp_item:
			frappe.throw(_("Temporary FG Items cannot create a YRP Item."))
		if rename:
			if not self.item:
				frappe.throw(_("Create the YRP Item before renaming it."))
			new_name = rename_item(self.item, self.name1, brand=self.brand)
			if new_name and self.item != new_name:
				self.db_set("item", new_name, update_modified=False)
			return new_name or self.item
		return create_or_update_item(self)


@frappe.whitelist()
def sync_fg_item(name, rename=False):
	doc = frappe.get_doc('SD YRP FG Item Master', name)
	doc.check_permission("write")
	return doc.sync_item(rename=cint(rename))


@frappe.whitelist()
def sync_fg_items(names, rename=False):
	names = frappe.parse_json(names) if isinstance(names, str) else names
	names = list(dict.fromkeys(names or []))
	if not names:
		frappe.throw(_("Select at least one FG Item Master."))
	for name in names:
		frappe.get_doc('SD YRP FG Item Master', name).check_permission("write")
	job = frappe.enqueue(
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_item_master.sd_yrp_fg_item_master.sync_fg_items_background",
		queue="long",
		names=names,
		rename=cint(rename),
		job_name=_("Sync FG Item Masters"),
	)
	return {"queued": len(names), "job_id": getattr(job, "id", None)}


def sync_fg_items_background(names, rename=False):
	failures = {}
	for name in names or []:
		try:
			frappe.get_doc('SD YRP FG Item Master', name).sync_item(rename=cint(rename))
		except Exception:
			failures[name] = frappe.get_traceback(with_context=True)
	if failures:
		frappe.log_error(
			title="FG Item Master local sync failed",
			message=frappe.as_json(failures, indent=2),
		)
	return {"processed": len(names or []) - len(failures), "failed": failures}


def create_or_update_item(fg_item):
	fg_item.check_permission("write")
	if not fg_item.template:
		frappe.throw(_("Set an FG Item Master Template."))

	if fg_item.item:
		item = frappe.get_doc('YRP Item', fg_item.item)
		item.check_permission("write")
	else:
		item = create_item(fg_item)
		fg_item.db_set("item", item.name, update_modified=False)

	item.name1 = fg_item.name1
	item.brand = fg_item.brand
	item.item_group = "Products"
	item.hsn_code = fg_item.hsn
	item.disabled = fg_item.disabled
	item.is_stock_item = 1
	item.is_purchase_item = 1
	item.is_sales_item = 1
	if item.meta.get_field("product_category"):
		item.product_category = fg_item.product_category

	_ensure_size_mapping(item, fg_item.sizes)
	_ensure_box_conversion(item, fg_item.pcs_per_box)
	item.save()
	_create_size_variants(item, fg_item.sizes)
	return item.name


def create_item(fg_item):
	template = frappe.get_doc('SD YRP FG Item Master Template', fg_item.template)
	template.check_permission("read")
	item = frappe.new_doc('YRP Item')
	item.name1 = fg_item.name1
	item.brand = fg_item.brand
	item.item_group = "Products"
	for fieldname in (
		"default_unit_of_measure",
		"secondary_unit_of_measure",
		"uom_conversion_details",
		"primary_attribute",
		"dependent_attribute",
		"dependent_attribute_mapping",
		"attributes",
		"additional_parameters",
	):
		item.set(fieldname, template.get(fieldname))
	item.insert()
	return item


def _ensure_size_mapping(item, sizes):
	attribute_row = next(
		(row for row in item.attributes if row.attribute == "Size"), None
	)
	if not attribute_row or not attribute_row.mapping:
		frappe.throw(_("Item {0} has no Size attribute mapping.").format(item.name))
	mapping = frappe.get_doc('YRP Item Item Attribute Mapping', attribute_row.mapping)
	existing = {row.attribute_value for row in mapping.values}
	changed = False
	for size in (row.attribute_value for row in sizes if row.attribute_value):
		if size not in existing:
			mapping.append("values", {"attribute_value": size})
			existing.add(size)
			changed = True
	if changed:
		mapping.save(ignore_permissions=True)


def _ensure_box_conversion(item, pieces_per_box):
	if cint(pieces_per_box) <= 0:
		frappe.throw(_("Pieces Per Box must be greater than zero."))
	row = next((row for row in item.uom_conversion_details if row.uom == "Box"), None)
	if row:
		row.conversion_factor = cint(pieces_per_box)
	else:
		item.append(
			"uom_conversion_details",
			{"uom": "Box", "conversion_factor": cint(pieces_per_box)},
		)


def _create_size_variants(item, sizes):
	dependent_value = None
	if item.dependent_attribute:
		details = get_dependent_attribute_details(item.dependent_attribute_mapping)
		dependent_value = next(
			(
				value
				for value, detail in details.get("attr_list", {}).items()
				if detail.get("attributes") == ["Size"]
			),
			None,
		)
		if not dependent_value:
			frappe.throw(
				_("Item {0} has no dependent stage mapped only to Size.").format(item.name)
			)
	for row in sizes:
		if not row.attribute_value:
			continue
		attributes = {"Size": row.attribute_value}
		if dependent_value:
			attributes[item.dependent_attribute] = dependent_value
		get_or_create_variant(item.name, attributes)


FGItemMaster = SDYRPFGItemMaster
