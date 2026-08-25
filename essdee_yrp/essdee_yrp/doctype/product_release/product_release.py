# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class ProductRelease(Document):
	def onload(self):
		if self.product_placement:
			self.set_onload(
				"placement_images", get_table_onload_data(self.product_placement)
			)
		if self.trims:
			self.set_onload("trims_images", get_table_onload_data(self.trims))
		if self.product_trim_combination:
			self.set_onload(
				"trims_combination",
				get_table_onload_data(self.product_trim_combination, with_list=True),
			)
		if self.product_accessories:
			self.set_onload(
				"accessory_images", get_table_onload_data(self.product_accessories)
			)
		if self.product_measurement_descriptions:
			measurement_details = {}
			for row in self.product_measurement_descriptions:
				measurement_details.setdefault(row.group, []).append(row.description)
			self.set_onload("measurement_details", measurement_details)


def get_table_onload_data(table, with_list: bool = False) -> list[dict]:
	image_names = [row.product_image for row in table if row.product_image]
	image_urls = dict(
		frappe.get_all(
			"Product Image",
			filters={"name": ["in", image_names]},
			fields=["name", "image"],
			as_list=True,
		)
	) if image_names else {}
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


def get_tabel_struct_data(data, with_list: bool = False) -> list[dict]:
	"""Preserve the established helper name used by the Product UI."""

	result = []
	for row in data or []:
		value = {
			"product_image": row.get("image_name"),
			"url": row.get("image_url"),
			"title_header": row.get("image_title"),
		}
		if with_list:
			value["selected_colours"] = ",".join(
				row.get("selected_colours") or []
			)
		result.append(value)
	return result
