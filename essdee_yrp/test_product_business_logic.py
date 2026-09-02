import frappe
from frappe import _dict
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product import (
	PRODUCT_ATTACHMENT_FIELDS,
	_assert_file_attached_to,
	get_grouped_files,
	get_table_struct_data,
	release_tech_pack,
)


class TestProductBusinessLogic(IntegrationTestCase):
	def test_product_mutation_endpoints_are_authenticated(self):
		for method in (
			"upload_product_file",
			"upload_graphics_file",
			"get_product_colour_codes",
			"delete_and_update_file",
			"remove_graphic_image",
			"release_tech_pack",
			"process_pdf_to_images",
			"process_single_page_pdf",
		):
			function = frappe.get_attr(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product." + method
			)
			self.assertIn(function, frappe.whitelisted, method)
			self.assertNotIn(function, frappe.guest_methods, method)

	def test_attachment_mutations_are_limited_to_product_development(self):
		self.assertEqual(
			PRODUCT_ATTACHMENT_FIELDS,
			{
				'SD YRP Product': {
					"product_image",
					"top_image",
					"bottom_image",
					"front_image",
					"back_image",
				},
				'SD YRP Product Colour Code': {"image"},
				'SD YRP Product Image': {"image"},
				'SD YRP Product Measurement': {"measurement_image"},
			},
		)

	def test_attachment_owner_check_rejects_cross_document_file(self):
		file_doc = _dict(
			attached_to_doctype='SD YRP Product',
			attached_to_name="STYLE-001",
			attached_to_field="product_image",
		)
		_assert_file_attached_to(
			file_doc, 'SD YRP Product', "STYLE-001", "product_image"
		)
		with self.assertRaises(frappe.PermissionError):
			_assert_file_attached_to(
				file_doc, 'SD YRP Product', "STYLE-002", "product_image"
			)

	def test_trim_colour_payload_discards_values_not_on_product(self):
		rows = get_table_struct_data(
			[
				{
					"image_name": "IMAGE-1",
					"image_url": "/files/image.png",
					"image_title": "Neck Trim",
					"selected_part": "Top",
					"selected_colours": ["Red", "Tampered", "Red"],
				}
			],
			with_list=True,
			colour_list=["Red", "Blue"],
		)
		self.assertEqual(rows[0]["selected_colours"], "Red")
		self.assertEqual(rows[0]["part"], "Top")

	def test_file_versions_group_by_type_and_sort_descending(self):
		rows = [
			_dict(product_upload_type="CAD", version_number=1),
			_dict(product_upload_type="CAD", version_number=3),
			_dict(product_upload_type="Spec", version_number=2),
		]
		grouped = get_grouped_files(rows)
		self.assertEqual(
			[row.version_number for row in grouped["CAD"]], [3, 1]
		)

	def test_existing_product_builds_product_development_onload(self):
		name = frappe.get_all('SD YRP Product', pluck="name", limit=1)[0]
		doc = frappe.get_doc('SD YRP Product', name)
		doc.run_method("onload")
		self.assertIn("costing_list", doc.get("__onload") or {})

	def test_release_tech_pack_creates_versioned_snapshot(self):
		product_name = frappe.get_all(
			'SD YRP Product', filters={"is_set_item": 0}, pluck="name", limit=1
		)[0]
		product = frappe.get_doc('SD YRP Product', product_name)
		product.set("product_designs", [])
		product.set("product_box_details", [])
		product.save()
		old_version = product.tech_pack_no or 0

		release_name = release_tech_pack(product.name)
		release = frappe.get_doc('SD YRP Product Release', release_name)
		self.assertEqual(release.product, product.name)
		self.assertEqual(release.tech_pack_no, old_version + 1)
		product.reload()
		self.assertEqual(product.tech_pack_no, old_version + 1)
