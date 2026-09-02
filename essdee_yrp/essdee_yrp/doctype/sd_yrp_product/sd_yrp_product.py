# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import re
from mimetypes import guess_type

import frappe
import pymupdf as fitz
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, get_url


PRODUCT_ATTACHMENT_FIELDS = {
	'SD YRP Product': {"product_image", "top_image", "bottom_image", "front_image", "back_image"},
	'SD YRP Product Colour Code': {"image"},
	'SD YRP Product Image': {"image"},
	'SD YRP Product Measurement': {"measurement_image"},
}
PRODUCT_GRAPHIC_TABLES = {"product_designs", "product_box_details"}
CHILD_IDENTITY_FIELDS = {
	"creation",
	"docstatus",
	"doctype",
	"idx",
	"modified",
	"modified_by",
	"name",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
}


class SDYRPProduct(Document):
	def onload(self):
		self._load_costing_list()
		for source_field, onload_key, with_list in (
			("product_placement", "placement_images", False),
			("trims", "trims_images", False),
			("product_trim_combination", "trims_combination", True),
			("product_accessories", "accessory_images", False),
		):
			if self.get(source_field):
				self.set_onload(
					onload_key,
					get_table_onload_data(self.get(source_field), with_list=with_list),
				)

		if self.product_measurement_descriptions:
			measurement_details = {}
			for row in self.product_measurement_descriptions:
				measurement_details.setdefault(row.group, []).append(row.description)
			self.set_onload("measurement_details", measurement_details)

	def before_validate(self):
		colours = self._validate_measurements_and_get_colours()
		self._sync_ui_image_tables(colours)
		self._sync_measurement_descriptions()

	def _load_costing_list(self):
		self.set_onload(
			"costing_list",
			frappe.get_list(
				'SD YRP Lotwise Item Profit',
				fields=[
					"name",
					"product",
					"total_qty",
					"avg_rate_per_piece",
					"profit_percent_markdown",
				],
				filters={"product": self.name},
			),
		)

	def _validate_measurements_and_get_colours(self) -> list[str]:
		colours = []
		if self.is_set_item:
			_validate_submitted_measurement(self.top_measurement, _("Top Measurement"))
			_validate_submitted_measurement(
				self.bottom_measurement, _("Bottom Measurement")
			)
			for row in self.product_set_colours:
				for colour in (row.top_colour, row.bottom_colour):
					if colour and colour not in colours:
						colours.append(colour)
		else:
			_validate_submitted_measurement(self.measurement, _("Measurement"))
			for row in self.product_colours:
				if row.product_colour and row.product_colour not in colours:
					colours.append(row.product_colour)
		return colours

	def _sync_ui_image_tables(self, colours: list[str]):
		for payload_field, table_field, with_list in (
			("placement_images", "product_placement", False),
			("product_trims_images", "trims", False),
			("trim_comb", "product_trim_combination", True),
			("accessory_images", "product_accessories", False),
		):
			payload = self.get(payload_field)
			if payload is not None:
				self.set(
					table_field,
					get_table_struct_data(
						_parse_payload(payload), with_list=with_list, colour_list=colours
					),
				)

	def _sync_measurement_descriptions(self):
		self.is_cord = 0
		rows = []
		if self.is_set_item:
			self.is_cord = int(
				all(row.top_colour == row.bottom_colour for row in self.product_set_colours)
			)
			rows.extend(_measurement_rows(self.top_measurement, "Top"))
			rows.extend(_measurement_rows(self.bottom_measurement, "Bottom"))
		else:
			rows.extend(_measurement_rows(self.measurement, "Part"))
		self.set("product_measurement_descriptions", rows)


def _validate_submitted_measurement(name: str | None, label: str):
	if name and frappe.db.get_value('SD YRP Product Measurement', name, "docstatus") != 1:
		frappe.throw(_("{0} is not submitted").format(label))


def _measurement_rows(name: str | None, group: str) -> list[dict]:
	if not name:
		return []
	doc = frappe.get_doc('SD YRP Product Measurement', name)
	return [
		{"description": row.description, "group": group}
		for row in doc.product_measurement_descriptions
	]


def _parse_payload(value):
	return frappe.parse_json(value) if isinstance(value, str) else value


def get_table_onload_data(table, with_list: bool = False) -> list[dict]:
	image_names = [row.product_image for row in table if row.product_image]
	image_urls = (
		dict(
			frappe.get_all(
				'SD YRP Product Image',
				filters={"name": ["in", image_names]},
				fields=["name", "image"],
				as_list=True,
			)
		)
		if image_names
		else {}
	)
	result = []
	for row in table:
		image = image_urls.get(row.product_image)
		value = {
			"image_url": get_url(image) if image else "",
			"image_title": row.title_header,
			"image_name": row.product_image,
		}
		if with_list:
			if row.get("part"):
				value["selected_part"] = row.part
			value["selected_colours"] = [
				colour for colour in (row.selected_colours or "").split(",") if colour
			]
		result.append(value)
	return result


def get_table_struct_data(
	data, with_list: bool = False, colour_list: list[str] | None = None
) -> list[dict]:
	allowed_colours = set(colour_list or [])
	result = []
	for row in data or []:
		value = {
			"product_image": row.get("image_name"),
			"url": row.get("image_url"),
			"title_header": row.get("image_title"),
		}
		if with_list:
			if row.get("selected_part"):
				value["part"] = row.get("selected_part")
			selected = []
			for colour in row.get("selected_colours") or []:
				if colour in allowed_colours and colour not in selected:
					selected.append(colour)
			value["selected_colours"] = ",".join(selected)
		result.append(value)
	return result


# Keep the historical misspelling as a compatibility alias for older callers.
get_tabel_struct_data = get_table_struct_data


def _get_writable_doc(doctype: str, docname: str):
	if doctype not in PRODUCT_ATTACHMENT_FIELDS:
		frappe.throw(_("Unsupported Product Development document."))
	doc = frappe.get_doc(doctype, docname)
	doc.check_permission("write")
	return doc


def _validate_attachment_field(doctype: str, fieldname: str):
	if fieldname not in PRODUCT_ATTACHMENT_FIELDS.get(doctype, set()):
		frappe.throw(_("Unsupported attachment field {0}.").format(frappe.bold(fieldname)))


def _get_file_by_url(file_url: str):
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		frappe.throw(_("Attachment {0} was not found.").format(frappe.bold(file_url)))
	return frappe.get_doc("File", name)


def _assert_file_attached_to(file_doc, doctype: str, docname: str, fieldname=None):
	if file_doc.attached_to_doctype != doctype or file_doc.attached_to_name != docname:
		frappe.throw(_("The selected file does not belong to this document."), frappe.PermissionError)
	if fieldname and file_doc.attached_to_field != fieldname:
		frappe.throw(_("The selected file does not belong to this field."), frappe.PermissionError)


def _safe_fragment(value: str) -> str:
	value = re.sub(r"[^A-Za-z0-9._-]+", "_", cstr(value)).strip("._")
	return value or "product"


def _uploaded_file_parts() -> tuple[bytes, str]:
	content = getattr(frappe.local, "uploaded_file", None)
	filename = os.path.basename(
		cstr(getattr(frappe.local, "uploaded_filename", None) or frappe.form_dict.file_name)
	)
	if content is None or not filename:
		frappe.throw(_("Please upload a file."))
	return content, filename


def _requested_upload_type(product_name: str, filename: str) -> str:
	upload_type = cstr(frappe.form_dict.get("upload_type")).strip()
	if not upload_type:
		prefix = f"{product_name}_"
		tail = filename[len(prefix) :] if filename.startswith(prefix) else filename
		upload_type = tail.split("_", 1)[0]
	if not upload_type:
		frappe.throw(_("Upload Type is required."))
	return upload_type


def _new_product_file(
	product, filename: str, content: bytes, fieldname: str, is_private: int
):
	return frappe.get_doc(
		{
			"doctype": "File",
			"attached_to_doctype": 'SD YRP Product',
			"attached_to_name": product.name,
			"attached_to_field": fieldname,
			"folder": get_or_create_product_folder(product.name),
			"file_name": filename,
			"is_private": cint(is_private),
			"content": content,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def upload_product_file():
	product = _get_writable_doc('SD YRP Product', frappe.form_dict.docname)
	content, original_filename = _uploaded_file_parts()
	upload_type = _requested_upload_type(product.name, original_filename)
	if not frappe.db.exists('SD YRP Product Upload Type', upload_type):
		frappe.throw(_("Unknown Product Upload Type {0}.").format(frappe.bold(upload_type)))

	version = (
		max(
			(
				cint(row.version_number)
				for row in product.product_file_versions
				if row.product_upload_type == upload_type
			),
			default=0,
		)
		+ 1
	)
	extension = os.path.splitext(original_filename)[1]
	filename = (
		f"{_safe_fragment(product.name)}_{_safe_fragment(upload_type)}_{version}{extension}"
	)
	file_doc = _new_product_file(
		product, filename, content, "file", frappe.form_dict.is_private
	)
	product.append(
		"product_file_versions",
		{
			"product_upload_type": upload_type,
			"file": file_doc.name,
			"filename": filename,
			"file_url": file_doc.file_url,
			"version_number": version,
			"timestamp": file_doc.creation,
		},
	)
	product.save()
	return file_doc


@frappe.whitelist()
def upload_graphics_file():
	product = _get_writable_doc('SD YRP Product', frappe.form_dict.docname)
	content, original_filename = _uploaded_file_parts()
	upload_type = _requested_upload_type(product.name, original_filename)
	table_name = "product_box_details" if frappe.form_dict.get("box_data") else "product_designs"
	extension = os.path.splitext(original_filename)[1]
	filename = f"{_safe_fragment(product.name)}_{_safe_fragment(upload_type)}{extension}"
	file_doc = _new_product_file(
		product, filename, content, table_name, frappe.form_dict.is_private
	)
	product.append(
		table_name,
		{
			"graphic_image": file_doc.file_url,
			"upload_name": upload_type,
			"file": file_doc.name,
			"filename": filename,
		},
	)
	product.save()
	return file_doc


def get_or_create_product_folder(product_name: str) -> str:
	product_folder = _safe_fragment("product").lower()
	doc_folder = _safe_fragment(product_name).lower()
	parent_name = frappe.db.exists(
		"File", {"file_name": product_folder, "is_folder": 1, "folder": "Home"}
	)
	if not parent_name:
		parent_name = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": product_folder,
				"is_folder": 1,
				"folder": "Home",
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True).name

	folder_name = frappe.db.exists(
		"File", {"file_name": doc_folder, "is_folder": 1, "folder": parent_name}
	)
	if not folder_name:
		folder_name = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": doc_folder,
				"is_folder": 1,
				"folder": parent_name,
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True).name
	return folder_name


def get_latest_product_images(product_name: str) -> list:
	product = frappe.get_doc('SD YRP Product', product_name)
	product.check_permission("read")
	latest_files = [group[0] for group in get_grouped_files(product.product_file_versions).values()]
	return [
		row
		for row in latest_files
		if (guess_type(row.filename)[0] or "").startswith("image/")
	]


def get_grouped_files(files) -> dict:
	grouped = {}
	for row in files:
		grouped.setdefault(row.product_upload_type, []).append(row)
	for rows in grouped.values():
		rows.sort(key=lambda row: cint(row.version_number), reverse=True)
	return grouped


@frappe.whitelist()
def get_product_colour_codes(doctype: str, docname: str) -> dict:
	if doctype != 'SD YRP Product':
		frappe.throw(_("Colour codes are available only for Product."))
	doc = frappe.get_doc('SD YRP Product', docname)
	doc.check_permission("read")
	if doc.is_set_item:
		return {
			colour: code
			for row in doc.product_set_colours
			for colour, code in (
				(row.top_colour, row.top_colour_code),
				(row.bottom_colour, row.bottom_colour_code),
			)
			if colour
		}
	return {
		row.product_colour: row.colour_code
		for row in doc.product_colours
		if row.product_colour
	}


@frappe.whitelist()
def delete_and_update_file(
	file_url: str,
	fieldname: str,
	doctype: str,
	docname: str,
	updated_url: str | None = None,
	file_name: str | None = None,
):
	doc = _get_writable_doc(doctype, docname)
	_validate_attachment_field(doctype, fieldname)
	new_file = None
	if updated_url:
		new_file = frappe.get_doc("File", file_name) if file_name else _get_file_by_url(updated_url)
		_assert_file_attached_to(new_file, doctype, docname, fieldname)
		if new_file.file_url != updated_url:
			frappe.throw(_("The uploaded file URL does not match the selected file."))

	if file_url and file_url != updated_url:
		old_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": doctype,
				"attached_to_name": docname,
				"attached_to_field": fieldname,
				"file_url": file_url,
			},
			pluck="name",
		)
		for old_file in old_files:
			frappe.delete_doc("File", old_file, ignore_permissions=True)

	doc.db_set(fieldname, updated_url or None, update_modified=True)
	return updated_url or None


@frappe.whitelist()
def remove_graphic_image(detail, docname: str):
	product = _get_writable_doc('SD YRP Product', docname)
	data = _parse_payload(detail) or {}
	row_name = data.get("name")
	row = next(
		(
			item
			for table_name in PRODUCT_GRAPHIC_TABLES
			for item in product.get(table_name)
			if item.name == row_name
		),
		None,
	)
	if not row:
		frappe.throw(_("The graphic row does not belong to this Product."))
	file_name = row.file
	product.remove(row)
	product.save()
	if file_name and frappe.db.exists("File", file_name):
		file_doc = frappe.get_doc("File", file_name)
		_assert_file_attached_to(file_doc, 'SD YRP Product', product.name)
		frappe.delete_doc("File", file_name, ignore_permissions=True)
	return True


def _child_rows(doc, table_name: str) -> list[dict]:
	return [
		{key: value for key, value in row.as_dict().items() if key not in CHILD_IDENTITY_FIELDS}
		for row in doc.get(table_name)
	]


def _copy_release_attachment(file_name: str | None, release_name: str):
	if not file_name:
		return None
	file_doc = frappe.get_doc("File", file_name)
	_assert_file_attached_to(file_doc, 'SD YRP Product', frappe.db.get_value('SD YRP Product Release', release_name, "product"))
	return file_doc.create_attachment_copy(
		'SD YRP Product Release', release_name, "file", ignore_permissions=True
	)


@frappe.whitelist()
def release_tech_pack(doc_name: str):
	product = _get_writable_doc('SD YRP Product', doc_name)
	frappe.has_permission('SD YRP Product Release', "create", throw=True)
	if product.is_set_item:
		for row in product.product_trim_combination:
			if not row.selected_colours:
				frappe.throw(
					_("Please select colours in trim colour combination for {0}").format(
						frappe.bold(row.title_header)
					)
				)
			if not row.part:
				frappe.throw(
					_("Please select part in trim colour combination for {0}").format(
						frappe.bold(row.title_header)
					)
				)

	release = frappe.new_doc('SD YRP Product Release')
	for fieldname in (
		"is_cord",
		"item_name",
		"style_no",
		"brand",
		"product_group",
		"fabric_details",
		"description",
		"season",
		"gsm",
		"size_range",
		"is_set_item",
		"category",
		"sub_brand",
		"dia",
		"product_image",
		"top_image",
		"bottom_image",
		"measurement",
		"top_measurement",
		"bottom_measurement",
	):
		release.set(fieldname, product.get(fieldname))
	release.product = product.name
	release.tech_pack_no = cint(product.tech_pack_no) + 1

	for table_name in (
		"sizes",
		"product_fabric_composition_details",
		"product_placement",
		"trims",
		"product_colours",
		"product_set_colours",
		"product_trim_combination",
		"product_designs",
		"product_measurement_descriptions",
		"product_accessories",
		"product_box_details",
	):
		release.set(table_name, _child_rows(product, table_name))
	release.insert()

	for table_name in PRODUCT_GRAPHIC_TABLES:
		for row in release.get(table_name):
			copy = _copy_release_attachment(row.file, release.name)
			if copy:
				row.db_set("file", copy.name)
				row.db_set("graphic_image", copy.file_url)
	product.db_set("tech_pack_no", release.tech_pack_no, update_modified=True)
	return release.name


def _validated_pdf(file_url: str, doctype: str, docname: str, fieldname: str):
	file_doc = _get_file_by_url(file_url)
	_assert_file_attached_to(file_doc, doctype, docname, fieldname)
	if (guess_type(file_doc.file_name or file_doc.file_url)[0] or "") != "application/pdf":
		frappe.throw(_("Please upload a PDF file."))
	try:
		pdf = fitz.open(stream=file_doc.get_content(), filetype="pdf")
	except Exception as exc:
		frappe.throw(_("Unable to read the PDF: {0}").format(cstr(exc)))
	if len(pdf) > 100:
		frappe.throw(_("PDFs with more than 100 pages are not supported."))
	return file_doc, pdf


@frappe.whitelist()
def process_pdf_to_images(file_url: str, docname: str, table_name: str):
	product = _get_writable_doc('SD YRP Product', docname)
	if table_name not in PRODUCT_GRAPHIC_TABLES:
		frappe.throw(_("Unsupported Product graphics table."))
	file_doc, pdf = _validated_pdf(file_url, 'SD YRP Product', docname, table_name)
	folder = get_or_create_product_folder(docname)
	matrix = fitz.Matrix(2, 2)
	for page_number, page in enumerate(pdf):
		image = page.get_pixmap(matrix=matrix).tobytes("png")
		filename = f"{_safe_fragment(docname)}_page_{page_number + 1}.png"
		new_file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": filename,
				"folder": folder,
				"content": image,
				"is_private": file_doc.is_private,
				"attached_to_doctype": 'SD YRP Product',
				"attached_to_name": docname,
				"attached_to_field": table_name,
			}
		).insert(ignore_permissions=True)
		product.append(
			table_name,
			{
				"upload_name": _("Page {0}").format(page_number + 1),
				"graphic_image": new_file.file_url,
				"filename": filename,
				"file": new_file.name,
			},
		)
	product.save()
	return True


@frappe.whitelist()
def process_single_page_pdf(
	file_url: str, doctype: str, docname: str, fieldname: str
):
	doc = _get_writable_doc(doctype, docname)
	_validate_attachment_field(doctype, fieldname)
	file_doc, pdf = _validated_pdf(file_url, doctype, docname, fieldname)
	if len(pdf) != 1:
		frappe.throw(_("The PDF must contain exactly 1 page."))

	image = pdf[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
	filename = f"{_safe_fragment(doctype)}_{_safe_fragment(docname)}_{_safe_fragment(fieldname)}.png"
	new_file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": image,
			"is_private": file_doc.is_private,
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"attached_to_field": fieldname,
		}
	).insert(ignore_permissions=True)
	doc.db_set(fieldname, new_file.file_url, update_modified=True)
	frappe.delete_doc("File", file_doc.name, ignore_permissions=True)
	return True


Product = SDYRPProduct
