from unittest import TestCase
from unittest.mock import MagicMock, mock_open, patch

import frappe
import pymupdf as fitz
from frappe import _dict
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product import (
	PRODUCT_ATTACHMENT_FIELDS,
	_assert_file_attached_to,
	_validated_pdf,
	get_grouped_files,
	get_table_struct_data,
	process_pdf_to_images,
	process_single_page_pdf,
	release_tech_pack,
)
from essdee_yrp.product_development import web_workspace


class TestProductPdfStaging(TestCase):
	def test_single_page_pdf_can_be_staged_without_saving_product(self):
		product = MagicMock()
		source_file = _dict(name="source-pdf", is_private=1)
		page = MagicMock()
		page.get_pixmap.return_value.tobytes.return_value = b"image"
		pdf = MagicMock()
		pdf.__len__.return_value = 1
		pdf.__getitem__.return_value = page
		image_file = _dict(
			name="image-file",
			file_name="product.png",
			file_url="/private/files/product.png",
		)
		image_document = MagicMock()
		image_document.insert.return_value = image_file
		module = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product"
		with (
			patch(f"{module}._get_writable_doc", return_value=product),
			patch(f"{module}._validated_pdf", return_value=(source_file, pdf)),
			patch(f"{module}.frappe.get_doc", return_value=image_document),
			patch(f"{module}.frappe.delete_doc") as delete_document,
		):
			result = process_single_page_pdf(
				"/private/files/source.pdf",
				"SD YRP Product",
				"STYLE-001",
				"product_image",
				defer_save=1,
			)

		self.assertEqual(result["file_url"], image_file.file_url)
		product.db_set.assert_not_called()
		delete_document.assert_called_once_with("File", source_file.name, ignore_permissions=True)

	def test_graphics_pdf_can_be_staged_without_saving_product(self):
		product = MagicMock()
		source_file = _dict(name="source-pdf", is_private=1)
		page = MagicMock()
		page.get_pixmap.return_value.tobytes.return_value = b"image"
		image_file = _dict(name="image-file", file_url="/private/files/page.png")
		image_document = MagicMock()
		image_document.insert.return_value = image_file
		module = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product"
		with (
			patch(f"{module}._get_writable_doc", return_value=product),
			patch(f"{module}._validated_pdf", return_value=(source_file, [page])),
			patch(f"{module}.get_or_create_product_folder", return_value="Home/product/style-001"),
			patch(f"{module}._", side_effect=lambda message: message),
			patch(f"{module}.frappe.get_doc", return_value=image_document),
		):
			rows = process_pdf_to_images(
				"/private/files/source.pdf",
				"STYLE-001",
				"product_designs",
				defer_save=1,
			)

		self.assertEqual(rows[0]["graphic_image"], image_file.file_url)
		self.assertEqual(rows[0]["upload_name"], "Page 1")
		product.extend.assert_not_called()
		product.save.assert_not_called()


class TestProductUploadStagingContract(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		groups = frappe.get_all("SD YRP Product Group", pluck="name", limit=1)
		self.product = frappe.get_doc(
			{
				"doctype": "SD YRP Product",
				"style_no": f"PD-STAGE-{frappe.generate_hash(length=10)}",
				"item_name": "Staging contract",
				"product_group": groups[0] if groups else None,
				"description": "Test",
				"fabric_details": "Cotton",
			}
		).insert()
		self.original_modified = str(self.product.modified)

	def tearDown(self):
		frappe.set_user("Administrator")
		for file_name in frappe.get_all(
			"File", filters={"attached_to_name": self.product.name}, pluck="name"
		):
			frappe.delete_doc("File", file_name, ignore_permissions=True)
		super().tearDown()

	def make_file(self, fieldname, filename, content=b"image"):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": filename,
				"content": content,
				"is_private": 1,
				"attached_to_doctype": "SD YRP Product",
				"attached_to_name": self.product.name,
				"attached_to_field": fieldname,
			}
		).insert(ignore_permissions=True)

	def make_pdf(self, fieldname, filename):
		document = fitz.open()
		document.new_page()
		content = document.tobytes()
		document.close()
		return self.make_file(fieldname, filename, content)

	def assert_product_unchanged(self):
		self.product.reload()
		self.assertEqual(str(self.product.modified), self.original_modified)
		self.assertFalse(self.product.product_image)
		self.assertFalse(self.product.product_designs)

	def assert_private_attachment(self, file_name, fieldname):
		file_doc = frappe.get_doc("File", file_name)
		self.assertEqual(file_doc.attached_to_doctype, "SD YRP Product")
		self.assertEqual(file_doc.attached_to_name, self.product.name)
		self.assertEqual(file_doc.attached_to_field, fieldname)
		self.assertEqual(file_doc.is_private, 1)
		return file_doc

	def test_real_uploads_and_deferred_pdfs_save_with_original_timestamp(self):
		ordinary = self.make_file("product_designs", "ordinary.png")
		silhouette_pdf = self.make_pdf("product_image", "silhouette.pdf")
		graphics_pdf = self.make_pdf("product_designs", "graphics.pdf")

		silhouette = process_single_page_pdf(
			silhouette_pdf.file_url,
			"SD YRP Product",
			self.product.name,
			"product_image",
			defer_save=1,
		)
		pdf_rows = process_pdf_to_images(
			graphics_pdf.file_url,
			self.product.name,
			"product_designs",
			defer_save=1,
		)

		self.assert_product_unchanged()
		self.assert_private_attachment(ordinary.name, "product_designs")
		self.assert_private_attachment(silhouette["name"], "product_image")
		for row in pdf_rows:
			self.assert_private_attachment(row["file"], "product_designs")
		self.assertFalse(frappe.db.exists("File", silhouette_pdf.name))
		self.assertTrue(frappe.db.exists("File", graphics_pdf.name))

		payload = web_workspace.save_product(
			{
				"product_image": silhouette["file_url"],
				"product_designs": [
					{
						"upload_name": "Ordinary",
						"graphic_image": ordinary.file_url,
						"file": ordinary.name,
					},
					*pdf_rows,
				],
			},
			name=self.product.name,
			expected_modified=self.original_modified,
		)

		self.assertEqual(payload["record"]["product_image"], silhouette["file_url"])
		self.assertEqual(
			[row["upload_name"] for row in payload["record"]["product_designs"]],
			["Ordinary", "Page 1"],
		)

	def test_discarded_upload_draft_does_not_change_product(self):
		graphic = self.make_file("product_designs", "discarded.png")

		self.assert_product_unchanged()
		self.assert_private_attachment(graphic.name, "product_designs")

	def test_staged_upload_does_not_bypass_stale_save_check(self):
		graphic = self.make_file("product_designs", "stale.png")
		self.product.db_set("item_name", "Changed elsewhere", update_modified=True)

		with self.assertRaises(frappe.TimestampMismatchError):
			web_workspace.save_product(
				{
					"product_designs": [{
						"upload_name": "Stale",
						"graphic_image": graphic.file_url,
						"file": graphic.name,
					}]
				},
				name=self.product.name,
				expected_modified=self.original_modified,
			)

	def test_deferred_pdf_endpoints_deny_users_without_write_access(self):
		silhouette_pdf = self.make_pdf("product_image", "denied-silhouette.pdf")
		graphics_pdf = self.make_pdf("product_designs", "denied-graphics.pdf")
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				process_single_page_pdf(
					silhouette_pdf.file_url,
					"SD YRP Product",
					self.product.name,
					"product_image",
					defer_save=1,
				)
			with self.assertRaises(frappe.PermissionError):
				process_pdf_to_images(
					graphics_pdf.file_url,
					self.product.name,
					"product_designs",
					defer_save=1,
				)
		finally:
			frappe.set_user("Administrator")


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
				"SD YRP Product": {
					"product_image",
					"top_image",
					"bottom_image",
					"front_image",
					"back_image",
				},
				"SD YRP Product Colour Code": {"image"},
				"SD YRP Product Image": {"image"},
				"SD YRP Product Measurement": {"measurement_image"},
			},
		)

	def test_attachment_owner_check_rejects_cross_document_file(self):
		file_doc = _dict(
			attached_to_doctype="SD YRP Product",
			attached_to_name="STYLE-001",
			attached_to_field="product_image",
		)
		_assert_file_attached_to(file_doc, "SD YRP Product", "STYLE-001", "product_image")
		with self.assertRaises(frappe.PermissionError):
			_assert_file_attached_to(file_doc, "SD YRP Product", "STYLE-002", "product_image")

	def test_pdf_validation_preserves_original_non_ascii_bytes(self):
		content = b"%PDF-1.4\n% Latin-1 Caf\xe9 and UTF-8 Caf\xc3\xa9\n%%EOF\n"
		file_doc = _dict(
			file_name="test.pdf",
			file_url="/private/files/test.pdf",
			attached_to_doctype="SD YRP Product",
			attached_to_name="PD-PDF-TEST",
			attached_to_field="product_image",
			get_full_path=lambda: "/private/files/test.pdf",
		)
		validated_pdf = MagicMock()
		validated_pdf.__len__.return_value = 1
		module = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product"
		with (
			patch(f"{module}._get_file_by_url", return_value=file_doc),
			patch(f"{module}.guess_type", return_value=("application/pdf", None)),
			patch("builtins.open", mock_open(read_data=content)) as source,
			patch(f"{module}.fitz.open", return_value=validated_pdf) as open_pdf,
		):
			_validated_file, validated_pdf = _validated_pdf(
				file_doc.file_url,
				file_doc.attached_to_doctype,
				file_doc.attached_to_name,
				file_doc.attached_to_field,
			)
		source.assert_called_once_with("/private/files/test.pdf", "rb")
		open_pdf.assert_called_once_with(stream=content, filetype="pdf")
		self.assertEqual(len(validated_pdf), 1)

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
		self.assertEqual([row.version_number for row in grouped["CAD"]], [3, 1])

	def test_existing_product_builds_product_development_onload(self):
		names = frappe.get_all("SD YRP Product", pluck="name", limit=1)
		if not names:
			self.skipTest("Product onload parity runs after source data migration")
		name = names[0]
		doc = frappe.get_doc("SD YRP Product", name)
		doc.run_method("onload")
		self.assertIn("costing_list", doc.get("__onload") or {})

	def test_release_tech_pack_creates_versioned_snapshot(self):
		groups = frappe.get_all("SD YRP Product Group", pluck="name", limit=1)
		sizes = frappe.get_all(
			"YRP Item Attribute Value",
			filters={"attribute_name": "Size"},
			fields=["name", "attribute_value"],
			limit=1,
		)
		if not groups or not sizes:
			self.skipTest("needs a Product Group and scoped Size value")
		token = frappe.generate_hash(length=10)
		measurement = frappe.get_doc(
			{
				"doctype": "SD YRP Product Measurement",
				"measurement_name": f"PD Release Measurement {token}",
				"product_measurement_descriptions": [{"description": "Sleeve length"}],
			}
		).insert()
		measurement.submit()
		colour = frappe.get_doc(
			{
				"doctype": "SD YRP Product Colour Code",
				"colour": f"PD Release Colour {token}",
				"colour_code": "#123456",
			}
		).insert()
		colour.submit()
		image_names = []
		for label in ("Placement", "Trim", "Combination", "Accessory"):
			image = frappe.get_doc(
				{
					"doctype": "SD YRP Product Image",
					"image_title": f"PD-{token}-{label}",
					"title_header": f"{label} Library Header",
				}
			).insert()
			image_names.append(image.name)

		product = frappe.get_doc(
			{
				"doctype": "SD YRP Product",
				"style_no": f"PD-RELEASE-{token}",
				"item_name": "Release parity product",
				"product_group": groups[0],
				"description": "Release parity test",
				"fabric_details": "Cotton",
				"front_image": "/files/front-parity.png",
				"back_image": "/files/back-parity.png",
				"measurement": measurement.name,
				"tech_pack_no": 4,
				"sizes": [{"attribute_value": sizes[0].name}],
				"product_colours": [{"product_colour": colour.name}],
				"product_placement": [
					{
						"product_image": image_names[0],
						"title_header": "Placement Header",
					}
				],
				"trims": [
					{"product_image": image_names[1], "title_header": "Trim Header"}
				],
				"product_trim_combination": [
					{
						"product_image": image_names[2],
						"title_header": "Combination Header",
						"selected_colours": colour.name,
						"part": "Top",
					}
				],
				"product_accessories": [
					{"product_image": image_names[3], "title_header": "Accessory Header"}
				],
			}
		).insert()
		release_name = None
		try:
			source_files = {}
			for table, content in (
				("product_designs", b"graphic"),
				("product_box_details", b"box"),
			):
				file_doc = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": f"{token}-{table}.png",
						"folder": "Home",
						"content": content,
						"is_private": 1,
						"attached_to_doctype": "SD YRP Product",
						"attached_to_name": product.name,
						"attached_to_field": table,
					}
				).insert(ignore_permissions=True)
				source_files[table] = file_doc.name
				product.append(
					table,
					{
						"graphic_image": file_doc.file_url,
						"filename": file_doc.file_name,
						"upload_name": table,
						"file": file_doc.name,
					},
				)
			product.save()

			release_name = release_tech_pack(product.name)
			release = frappe.get_doc("SD YRP Product Release", release_name)
			self.assertIsNone(frappe.get_meta(release.doctype).get_field("product_info_extras"))
			self.assertEqual(release.product, product.name)
			self.assertEqual(release.tech_pack_no, 5)
			self.assertEqual(release.front_image, product.front_image)
			self.assertEqual(release.back_image, product.back_image)
			self.assertEqual(release.measurement, measurement.name)
			self.assertEqual(release.sizes[0].attribute_value, product.sizes[0].attribute_value)
			self.assertEqual(release.product_colours[0].product_colour, colour.name)
			self.assertEqual(
				[(row.product_image, row.title_header) for row in release.product_placement],
				[(image_names[0], "Placement Header")],
			)
			self.assertEqual(
				[(row.product_image, row.title_header) for row in release.trims],
				[(image_names[1], "Trim Header")],
			)
			combination = release.product_trim_combination[0]
			self.assertEqual(combination.product_image, image_names[2])
			self.assertEqual(combination.title_header, "Combination Header")
			self.assertEqual(combination.selected_colours, colour.name)
			self.assertEqual(combination.part, "Top")
			self.assertEqual(
				[(row.product_image, row.title_header) for row in release.product_accessories],
				[(image_names[3], "Accessory Header")],
			)
			self.assertEqual(
				[(row.group, row.description) for row in release.product_measurement_descriptions],
				[("Part", "Sleeve length")],
			)
			for table in ("product_designs", "product_box_details"):
				row = release.get(table)[0]
				self.assertNotEqual(row.file, source_files[table])
				file_doc = frappe.get_doc("File", row.file)
				self.assertEqual(file_doc.attached_to_doctype, "SD YRP Product Release")
				self.assertEqual(file_doc.attached_to_name, release.name)
				self.assertEqual(row.graphic_image, file_doc.file_url)

			payload = web_workspace.get_product_release_workspace(release.name)
			self.assertEqual(payload["size_labels"][sizes[0].name], sizes[0].attribute_value)
			self.assertEqual(payload["measurement"]["groups"], {"Part": ["Sleeve length"]})
			self.assertEqual(payload["colours"]["all"][0]["colour"], colour.name)
			self.assertEqual(
				[row["image_name"] for row in payload["images"]["placement"]],
				[image_names[0]],
			)
			self.assertEqual(
				payload["images"]["combination"][0]["selected_colours"], [colour.name]
			)
			self.assertEqual(payload["images"]["combination"][0]["selected_part"], "Top")
			self.assertTrue(payload["record"]["product_designs"][0]["graphic_image"])
			self.assertTrue(payload["record"]["product_box_details"][0]["graphic_image"])
			product.reload()
			self.assertEqual(product.tech_pack_no, 5)
		finally:
			attached_names = [product.name, release_name]
			for file_name in frappe.get_all(
				"File",
				filters={"attached_to_name": ["in", [name for name in attached_names if name]]},
				pluck="name",
			):
				frappe.delete_doc("File", file_name, ignore_permissions=True)

	def test_pd_user_can_release_tech_pack_without_release_create_permission(self):
		users = frappe.get_all(
			"Has Role",
			filters={"role": "PD User", "parenttype": "User"},
			pluck="parent",
		)
		users = [
			user
			for user in users
			if frappe.db.get_value("User", user, "enabled") and "System Manager" not in frappe.get_roles(user)
		]
		if not users:
			self.skipTest("needs an enabled PD User without the System Manager role")

		frappe.set_user("Administrator")
		groups = frappe.get_all("SD YRP Product Group", pluck="name", limit=1)
		product = frappe.get_doc(
			{
				"doctype": "SD YRP Product",
				"style_no": f"PD-RELEASE-TEST-{frappe.generate_hash(length=10)}",
				"item_name": "PD Release Test",
				"product_group": groups[0] if groups else None,
				"description": "Test",
				"fabric_details": "Cotton",
			}
		).insert()
		frappe.set_user(users[0])
		try:
			release_name = release_tech_pack(product.name)
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("SD YRP Product Release", release_name))
