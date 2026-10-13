from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import hooks
from essdee_yrp.product_development import web_workspace
from essdee_yrp.www.web import WEB_DOCTYPES

PD_DOCTYPES = ("SD YRP Product", "SD YRP Product Release", "SD YRP Lotwise Item Profit")


def make_product(style_no=None, **values):
	groups = frappe.get_all("SD YRP Product Group", pluck="name", limit=1)
	style_no = style_no or f"PD-WEB-TEST-{frappe.generate_hash(length=10)}"
	return frappe.get_doc(
		{
			"doctype": "SD YRP Product",
			"style_no": style_no,
			"item_name": "PD Web Test",
			"product_group": groups[0] if groups else None,
			"description": "Test",
			"fabric_details": "Cotton",
			**values,
		}
	).insert()


class TestPdCapabilities(TestCase):
	def workspace(self):
		from essdee_yrp.product_development import web_workspace

		return web_workspace

	def test_pd_doctypes_are_in_both_web_catalogs(self):
		for catalog in (WEB_DOCTYPES, hooks.yrp_web_doctype_catalog):
			for doctype in PD_DOCTYPES:
				self.assertIn(doctype, catalog)

	def test_capabilities_reflect_permissions_per_section(self):
		def allowed(doctype, ptype="read", doc=None, **kwargs):
			return doctype == "SD YRP Product" or (
				doctype == "SD YRP Product Release" and ptype == "read"
			)

		with patch.object(frappe, "has_permission", side_effect=allowed):
			sections = self.workspace().get_capabilities()["sections"]
		self.assertTrue(sections["products"]["can_write"])
		self.assertTrue(sections["product_releases"]["can_read"])
		self.assertFalse(sections["product_releases"]["can_write"])
		self.assertFalse(sections["lotwise_item_profits"]["can_read"])

	def test_capability_labels_are_translated_at_call_time(self):
		language = "en"
		translations = {"en": "Products", "fr": "Produits"}

		def translate(label):
			return translations[language] if label == "Products" else label

		workspace = self.workspace()
		with (
			patch.object(frappe, "has_permission", return_value=False),
			patch.object(workspace, "_", side_effect=translate),
		):
			english_label = workspace.get_capabilities()["sections"]["products"]["label"]
			language = "fr"
			french_label = workspace.get_capabilities()["sections"]["products"]["label"]

		self.assertEqual(english_label, "Products")
		self.assertEqual(french_label, "Produits")

	def test_capabilities_is_whitelisted_and_not_guest(self):
		function = self.workspace().get_capabilities
		self.assertIn(function, frappe.whitelisted)
		self.assertNotIn(function, frappe.guest_methods)


class TestPdProductWorkspace(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.product = make_product()

	def test_workspace_contains_record_images_and_permissions(self):
		payload = web_workspace.get_product_workspace(self.product.name)
		self.assertEqual(payload["record"]["name"], self.product.name)
		self.assertEqual(payload["modified"], str(self.product.modified))
		self.assertIn("can_write", payload["permissions"])
		self.assertEqual(set(payload["images"]), {"placement", "trims", "combination", "accessories"})
		self.assertIn("size_labels", payload)
		self.assertEqual(payload["print_formats"], ["Essdee Product Tech Pack"])
		self.assertEqual(payload["link_filters"]["measurement"], {"docstatus": 1})

	def test_new_product_defaults_include_size_labels(self):
		payload = web_workspace.get_new_product_defaults()
		self.assertEqual(payload["size_labels"], {})

	def test_save_updates_fields_and_ignores_unlisted_fields(self):
		payload = web_workspace.save_product(
			{"item_name": "Renamed", "tech_pack_no": 99},
			name=self.product.name,
			expected_modified=str(self.product.modified),
		)
		self.assertEqual(payload["record"]["item_name"], "Renamed")
		self.assertNotEqual(payload["record"]["tech_pack_no"], 99)

	def test_save_rejects_stale_modified(self):
		with self.assertRaises(frappe.TimestampMismatchError):
			web_workspace.save_product(
				{"item_name": "X"},
				name=self.product.name,
				expected_modified="2000-01-01 00:00:00",
			)

	def test_existing_mutations_require_modified_timestamp(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Reload the record"):
			web_workspace.save_product({"item_name": "X"}, name=self.product.name)
		with self.assertRaisesRegex(frappe.ValidationError, "Reload the record"):
			web_workspace.delete_product(self.product.name, expected_modified="")

	def test_existing_product_is_loaded_for_update_before_save(self):
		with patch.object(frappe, "get_doc", wraps=frappe.get_doc) as get_document:
			doc = web_workspace.product_for_save(self.product.name, str(self.product.modified))

		self.assertEqual(doc.name, self.product.name)
		get_document.assert_called_once_with(
			web_workspace.PRODUCT, self.product.name, for_update=True
		)

	def test_delete_locks_product_before_stale_check(self):
		locked_doc = MagicMock(name=self.product.name, modified="2026-10-12 12:00:00")
		with (
			patch.object(frappe, "get_doc", return_value=locked_doc) as get_document,
			patch.object(frappe, "delete_doc") as delete_document,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			web_workspace.delete_product(
				self.product.name, expected_modified="2026-10-12 11:00:00"
			)

		get_document.assert_called_once_with(
			web_workspace.PRODUCT, self.product.name, for_update=True
		)
		locked_doc.check_permission.assert_called_once_with("delete")
		delete_document.assert_not_called()

	def test_save_rejects_child_row_owned_by_another_product(self):
		other_product = make_product(
			product_fabric_composition_details=[{"fabric_name": "Cotton", "percentage": 100}]
		)
		foreign_row = other_product.product_fabric_composition_details[0]

		with self.assertRaisesRegex(
			frappe.ValidationError, "product_fabric_composition_details"
		):
			web_workspace.save_product(
				{
					"product_fabric_composition_details": [
						{"name": foreign_row.name, "fabric_name": "Wool", "percentage": 100}
					]
				},
				name=self.product.name,
				expected_modified=str(self.product.modified),
			)

		owner = frappe.db.get_value(
			"SD YRP Product Fabric Composition Detail",
			foreign_row.name,
			["parent", "parentfield"],
			as_dict=True,
		)
		self.assertEqual(owner.parent, other_product.name)
		self.assertEqual(owner.parentfield, "product_fabric_composition_details")

	def test_save_drops_trim_colours_not_on_product(self):
		colours = frappe.get_all(
			"SD YRP Product Colour Code", filters={"docstatus": 1}, pluck="name", limit=1
		)
		images = frappe.get_all("SD YRP Product Image", pluck="name", limit=1)
		if not colours or not images:
			self.skipTest("needs a submitted colour code and a product image on the test site")
		self.product.set("product_colours", [{"product_colour": colours[0]}])
		self.product.save()
		image_payload = {
			"trim_comb": [
				{
					"image_name": images[0],
					"image_title": "T",
					"image_url": "",
					"selected_colours": [colours[0], "NOT-A-COLOUR"],
				}
			]
		}
		payload = web_workspace.save_product(
			{},
			images=image_payload,
			name=self.product.name,
			expected_modified=str(self.product.modified),
		)
		self.assertEqual(payload["images"]["combination"][0]["selected_colours"], [colours[0]])

	def test_colour_search_matches_colour_code(self):
		colour = f"PD Web Colour {frappe.generate_hash(length=10)}"
		colour_code = "#c0ffee"
		self.assertNotIn("c0ffee", colour.lower())
		frappe.get_doc(
			{
				"doctype": "SD YRP Product Colour Code",
				"colour": colour,
				"colour_code": colour_code,
			}
		).insert().submit()

		result = web_workspace.search_submitted_colour_codes("c0ffee")

		self.assertIn(colour, {row["name"] for row in result})
		matched = next(row for row in result if row["name"] == colour)
		self.assertEqual(matched["colour_code"], colour_code)

	def test_create_product_image_rejects_duplicate_titles(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image import (
			create_product_image,
		)

		image_title = f"pd-web-test-button-{frappe.generate_hash(length=10)}"
		first = create_product_image(image_title, "Button")
		with self.assertRaisesRegex(
			frappe.DuplicateEntryError,
			f'Product Image "{image_title}" already exists. Pick it from the library instead.',
		):
			create_product_image(image_title, "Button")
		self.assertEqual(first["name"], image_title)
		self.assertEqual(frappe.db.count("SD YRP Product Image", {"image_title": image_title}), 1)
		self.assertFalse(frappe.db.exists("SD YRP Product Image", f"{image_title}-2"))

	def test_create_product_image_rejects_insert_race(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image import (
			PRODUCT_IMAGE,
			create_product_image,
		)

		image_title = f"pd-web-test-race-{frappe.generate_hash(length=10)}"
		insert = MagicMock(side_effect=frappe.DuplicateEntryError)
		with (
			patch.object(frappe.db, "exists", return_value=None),
			patch.object(frappe, "get_doc", return_value=MagicMock(insert=insert)) as get_document,
			self.assertRaisesRegex(frappe.DuplicateEntryError, "Pick it from the library instead"),
		):
			create_product_image(image_title, "Button")
		get_document.assert_called_once_with(
			{"doctype": PRODUCT_IMAGE, "image_title": image_title, "title_header": "Button"}
		)
		insert.assert_called_once_with()

	def test_size_range_sizes(self):
		size_ranges = frappe.get_all("SD YRP FG Item Size Range", pluck="name", limit=1)
		if not size_ranges:
			self.skipTest("needs an FG Item Size Range")
		rows = web_workspace.get_size_range_sizes(size_ranges[0])
		self.assertTrue(all({"attribute_value", "size"} <= row.keys() for row in rows))
		for row in rows:
			label = frappe.db.get_value(
				"YRP Item Attribute Value", row["attribute_value"], "attribute_value"
			)
			self.assertEqual(row["size"], label or row["attribute_value"])
		if rows:
			self.product.size_range = size_ranges[0]
			self.product.set("sizes", [{"attribute_value": rows[0]["attribute_value"]}])
			self.product.save()
			payload = web_workspace.get_product_workspace(self.product.name)
			self.assertEqual(
				payload["size_labels"][rows[0]["attribute_value"]], rows[0]["size"]
			)

	def test_read_only_user_cannot_save(self):
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				web_workspace.save_product(
					{"item_name": "X"},
					name=self.product.name,
					expected_modified=str(self.product.modified),
				)


class TestPdReleaseWorkspace(IntegrationTestCase):
	def test_release_workspace_is_read_only(self):
		name = frappe.get_all("SD YRP Product Release", pluck="name", limit=1)
		if not name:
			self.skipTest("no Product Release on the test site")
		payload = web_workspace.get_product_release_workspace(name[0])
		self.assertFalse(payload["permissions"]["can_write"])
		self.assertFalse(payload["permissions"]["can_create"])
		self.assertEqual(payload["print_formats"], ["Essdee Tech Pack"])
		self.assertIn("combination", payload["images"])
		self.assertIn("size_labels", payload)
		self.assertEqual(payload["product"], payload["record"].get("product"))
		for excluded_key in ("costing", "releases", "link_filters"):
			self.assertNotIn(excluded_key, payload)

	def test_release_workspace_requires_read(self):
		name = frappe.get_all("SD YRP Product Release", pluck="name", limit=1)
		if not name:
			self.skipTest("no Product Release on the test site")
		with patch("frappe.model.document.Document.has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				web_workspace.get_product_release_workspace(name[0])

	def test_delete_release_checks_permission(self):
		doc = MagicMock()
		with (
			patch.object(frappe, "get_doc", return_value=doc) as get_document,
			patch.object(frappe, "delete_doc") as delete_document,
		):
			result = web_workspace.delete_product_release("RELEASE-1")

		self.assertEqual(result, {"deleted": True})
		get_document.assert_called_once_with(web_workspace.RELEASE, "RELEASE-1")
		doc.check_permission.assert_called_once_with("delete")
		delete_document.assert_called_once_with(web_workspace.RELEASE, "RELEASE-1")
