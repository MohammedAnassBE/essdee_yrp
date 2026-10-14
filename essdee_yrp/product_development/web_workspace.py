"""Permission-safe web contract for the PD (Product Development) workspace."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cstr

from essdee_yrp.web_common import assert_expected_modified, parse_mapping, permission_flags

PRODUCT = "SD YRP Product"
RELEASE = "SD YRP Product Release"
LOTWISE = "SD YRP Lotwise Item Profit"
COLOUR_CODE = "SD YRP Product Colour Code"
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")
PERMISSION_TYPES = ("read", "create", "write", "delete", "print")
SECTIONS = {
	"products": (PRODUCT, "Products"),
	"product_releases": (RELEASE, "Product Releases"),
	"lotwise_item_profits": (LOTWISE, "Lotwise Item Profit"),
}
PRODUCT_FIELDS = (
	"style_no",
	"item_name",
	"product_group",
	"description",
	"season",
	"fabric_details",
	"gsm",
	"dia",
	"brand",
	"sub_brand",
	"category",
	"product_category",
	"fg_item_category",
	"template",
	"pieces_per_box",
	"is_set_item",
	"size_range",
	"measurement",
	"top_measurement",
	"bottom_measurement",
	"product_image",
	"top_image",
	"bottom_image",
)
PRODUCT_TABLES = (
	"sizes",
	"product_fabric_composition_details",
	"product_colours",
	"product_set_colours",
	"product_designs",
	"product_box_details",
	"product_info_extras",
)
IMAGE_PAYLOAD_KEYS = ("placement_images", "product_trims_images", "trim_comb", "accessory_images")
PRODUCT_LINK_FILTERS = {
	"measurement": {"docstatus": 1},
	"top_measurement": {"docstatus": 1},
	"bottom_measurement": {"docstatus": 1},
	"product_colours.product_colour": {"docstatus": 1},
	"product_set_colours.top_colour": {"docstatus": 1},
	"product_set_colours.bottom_colour": {"docstatus": 1},
}
CHILD_FIELDS_TO_DROP = {
	"creation",
	"docstatus",
	"doctype",
	"modified",
	"modified_by",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
}


def readable_doc(doctype: str, name: str):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.run_method("onload")
	return doc


def image_payload(onload) -> dict:
	return {
		"placement": onload.get("placement_images") or [],
		"trims": onload.get("trims_images") or [],
		"combination": onload.get("trims_combination") or [],
		"accessories": onload.get("accessory_images") or [],
	}


def size_labels(rows, fieldname: str = "attribute_value") -> dict[str, str]:
	names = [row.get(fieldname) for row in rows or [] if row.get(fieldname)]
	if not names:
		return {}
	return {
		row.name: row.attribute_value
		for row in frappe.get_all(
			"YRP Item Attribute Value",
			filters={"name": ["in", names]},
			fields=["name", "attribute_value"],
		)
	}


def measurement_images(doc) -> list[dict]:
	links = (
		(("Top", doc.top_measurement), ("Bottom", doc.bottom_measurement))
		if doc.is_set_item
		else (("Measurement", doc.measurement),)
	)
	images = []
	for label, name in links:
		url = name and frappe.db.get_value("SD YRP Product Measurement", name, "measurement_image")
		if url:
			images.append({"label": label, "url": url})
	return images


def colour_entry(colour: str, code: str | None, images: dict) -> dict:
	return {"colour": colour, "colour_code": code or "", "image": images.get(colour) or ""}


def colour_images(names: set[str]) -> dict[str, str]:
	if not names:
		return {}
	return dict(
		frappe.get_all(
			"SD YRP Product Colour Code",
			filters={"name": ["in", list(names)]},
			fields=["name", "image"],
			as_list=True,
		)
	)


def set_colour_options(doc, images: dict) -> tuple[list[dict], list[dict]]:
	top = {
		row.top_colour: colour_entry(row.top_colour, row.top_colour_code, images)
		for row in doc.product_set_colours
		if row.top_colour
	}
	bottom = {
		row.bottom_colour: colour_entry(row.bottom_colour, row.bottom_colour_code, images)
		for row in doc.product_set_colours
		if row.bottom_colour
	}
	return list(top.values()), list(bottom.values())


def colour_options(doc) -> dict:
	"""Return colour choices for trim combinations."""
	set_names = {
		colour
		for row in doc.product_set_colours
		for colour in (row.top_colour, row.bottom_colour)
		if colour
	}
	product_names = {row.product_colour for row in doc.product_colours if row.product_colour}
	images = colour_images(set_names | product_names)
	top, bottom = set_colour_options(doc, images)
	every = {
		row.product_colour: colour_entry(row.product_colour, row.colour_code, images)
		for row in doc.product_colours
		if row.product_colour
	}
	return {"is_set_item": bool(doc.is_set_item), "top": top, "bottom": bottom, "all": list(every.values())}


def strip_row_identity(row) -> dict:
	row = parse_mapping(row, _("Table row"))
	return {key: value for key, value in row.items() if key not in CHILD_FIELDS_TO_DROP}


def child_rows_for_save(doc, table: str, rows) -> list[dict]:
	existing_rows = {row.name: row for row in doc.get(table) or [] if row.name}
	clean_rows = []
	for index, source_row in enumerate(rows or [], start=1):
		row = strip_row_identity(source_row)
		if row.get("name") and row["name"] not in existing_rows:
			frappe.throw(
				_("Row {0} does not belong to table {1}.").format(
					frappe.bold(row["name"]), frappe.bold(table)
				),
				frappe.ValidationError,
			)
		if table in {"product_designs", "product_box_details"}:
			_validate_graphic_reference(doc, table, row, existing_rows.get(row.get("name")))
			row["idx"] = index
		clean_rows.append(row)
	return clean_rows


def _validate_graphic_reference(doc, table: str, row: dict, existing_row=None) -> None:
	if existing_row and all(
		row.get(fieldname) == existing_row.get(fieldname)
		for fieldname in ("file", "graphic_image")
	):
		row["filename"] = existing_row.filename
		return
	file_name = cstr(row.get("file")).strip()
	if not file_name or not frappe.db.exists("File", file_name):
		frappe.throw(_("The selected graphic file was not found."), frappe.ValidationError)
	file_doc = frappe.get_doc("File", file_name)
	if (
		file_doc.attached_to_doctype != PRODUCT
		or file_doc.attached_to_name != doc.name
		or file_doc.attached_to_field != table
	):
		frappe.throw(
			_("The selected graphic file does not belong to this Product table."),
			frappe.ValidationError,
		)
	if not file_doc.file_url or file_doc.file_url != row.get("graphic_image"):
		frappe.throw(_("The selected graphic URL does not match its File."), frappe.ValidationError)
	row["filename"] = file_doc.file_name


def product_for_save(name, expected_modified):
	if not name:
		frappe.has_permission(PRODUCT, "create", throw=True)
		return frappe.new_doc(PRODUCT)
	doc = frappe.get_doc(PRODUCT, name, for_update=True)
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	return doc


def apply_product_values(doc, values: dict, images: dict) -> None:
	for fieldname in PRODUCT_FIELDS:
		if fieldname in values and not (fieldname == "style_no" and doc.name and not doc.is_new()):
			doc.set(fieldname, values[fieldname])
	for table in PRODUCT_TABLES:
		if table in values:
			doc.set(table, child_rows_for_save(doc, table, values[table]))
	for key in IMAGE_PAYLOAD_KEYS:
		if key in images:
			doc.set(key, images[key])


@frappe.whitelist()
def get_capabilities() -> dict:
	"""Return effective permissions for each PD destination."""
	return {
		"sections": {
			key: {
				"label": _(label),
				"doctype": doctype,
				**permission_flags(doctype, PERMISSION_TYPES),
			}
			for key, (doctype, label) in SECTIONS.items()
		}
	}


@frappe.whitelist()
def search_submitted_colour_codes(query: str = "") -> dict:
	"""Search submitted Product Colour Codes through normal read permissions."""
	query = cstr(query).strip()
	or_filters = None
	if query:
		like = f"%{query}%"
		or_filters = [
			["name", "like", like],
			["colour", "like", like],
			["colour_code", "like", like],
		]
	options = frappe.get_list(
		COLOUR_CODE,
		filters={"docstatus": 1},
		or_filters=or_filters,
		fields=["name", "colour", "colour_code", "image"],
		order_by="colour asc",
		limit_page_length=50,
	)
	exact_name_exists = bool(
		query
		and frappe.get_list(
			COLOUR_CODE,
			filters={"name": query},
			pluck="name",
			limit_page_length=1,
		)
	)
	return {"options": options, "exact_name_exists": exact_name_exists}


@frappe.whitelist(methods=["POST"])
def create_colour_code(colour: str, colour_code: str) -> dict:
	"""Create a Product Colour Code, submitting it only when the user may submit."""
	colour = cstr(colour).strip()
	colour_code = cstr(colour_code).strip()
	frappe.has_permission(COLOUR_CODE, "create", throw=True)
	if not HEX_COLOUR.fullmatch(colour_code):
		frappe.throw(_("Colour code must be a hex value like #FF8800."), frappe.ValidationError)
	existing = frappe.db.get_value(COLOUR_CODE, colour, ["name", "docstatus"], as_dict=True)
	if existing:
		state = _("submitted") if existing.docstatus == 1 else _("not submitted")
		frappe.throw(
			_('Colour "{0}" already exists ({1}).').format(existing.name, state),
			frappe.DuplicateEntryError,
		)
	doc = frappe.get_doc({"doctype": COLOUR_CODE, "colour": colour, "colour_code": colour_code}).insert()
	if frappe.has_permission(COLOUR_CODE, "submit", doc=doc):
		doc.submit()
	return {
		"name": doc.name,
		"colour": doc.colour,
		"colour_code": doc.colour_code,
		"image": doc.image,
		"docstatus": doc.docstatus,
	}


@frappe.whitelist()
def get_product_workspace(name: str) -> dict:
	doc = readable_doc(PRODUCT, name)
	onload = doc.get_onload()
	permissions = permission_flags(PRODUCT, PERMISSION_TYPES, doc)
	permissions["can_release"] = bool(frappe.has_permission(PRODUCT, "write", doc=doc))
	return {
		"record": doc.as_dict(),
		"modified": str(doc.modified),
		"permissions": permissions,
		"images": image_payload(onload),
		"size_labels": size_labels(doc.sizes),
		"measurement": {
			"groups": onload.get("measurement_details") or {},
			"images": measurement_images(doc),
		},
		"colours": colour_options(doc),
		"costing": onload.get("costing_list") or [],
		"releases": frappe.get_list(
			RELEASE,
			filters={"product": doc.name},
			fields=["name", "tech_pack_no", "creation"],
			order_by="tech_pack_no desc",
		),
		"print_formats": ["Essdee Product Tech Pack"],
		"link_filters": PRODUCT_LINK_FILTERS,
	}


@frappe.whitelist()
def get_product_release_workspace(name: str) -> dict:
	doc = readable_doc(RELEASE, name)
	onload = doc.get_onload()
	return {
		"record": doc.as_dict(),
		"modified": str(doc.modified),
		"product": doc.product,
		"permissions": {
			**permission_flags(RELEASE, PERMISSION_TYPES, doc),
			"can_write": False,
			"can_create": False,
		},
		"images": image_payload(onload),
		"size_labels": size_labels(doc.sizes),
		"measurement": {
			"groups": onload.get("measurement_details") or {},
			"images": measurement_images(doc),
		},
		"colours": colour_options(doc),
		"print_formats": ["Essdee Tech Pack"],
	}


@frappe.whitelist()
def get_new_product_defaults() -> dict:
	frappe.has_permission(PRODUCT, "create", throw=True)
	doc = frappe.new_doc(PRODUCT)
	return {
		"record": doc.as_dict(),
		"permissions": permission_flags(PRODUCT, PERMISSION_TYPES),
		"size_labels": size_labels(doc.sizes),
		"link_filters": PRODUCT_LINK_FILTERS,
	}


@frappe.whitelist()
def save_product(values, images=None, name: str | None = None, expected_modified: str | None = None) -> dict:
	values = parse_mapping(values, _("Values"))
	images = parse_mapping(images or {}, _("Images"))
	doc = product_for_save(name, expected_modified)
	apply_product_values(doc, values, images)
	doc.save() if name else doc.insert()
	return get_product_workspace(doc.name)


@frappe.whitelist()
def get_size_range_sizes(size_range: str) -> list[dict]:
	doc = frappe.get_doc("SD YRP FG Item Size Range", size_range)
	doc.check_permission("read")
	labels = size_labels(doc.sizes)
	return [
		{"attribute_value": row.attribute_value, "size": labels.get(row.attribute_value, row.attribute_value)}
		for row in doc.sizes
	]


@frappe.whitelist()
def delete_product(name: str, expected_modified: str | None = None) -> dict:
	doc = frappe.get_doc(PRODUCT, name, for_update=True)
	doc.check_permission("delete")
	assert_expected_modified(doc, expected_modified)
	frappe.delete_doc(PRODUCT, name)
	return {"deleted": True}


@frappe.whitelist()
def delete_product_release(name: str) -> dict:
	doc = frappe.get_doc(RELEASE, name)
	doc.check_permission("delete")
	frappe.delete_doc(RELEASE, name)
	return {"deleted": True}
