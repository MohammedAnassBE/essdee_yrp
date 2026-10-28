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
		self.assertFalse(sections["lay_sheet_planner"]["can_read"])

	def test_lay_sheet_planner_section_follows_planner_permissions(self):
		def allowed(doctype, ptype="read", doc=None, **kwargs):
			return doctype == "SD YRP Cutting Laysheet Planner" and ptype in ("read", "create")

		with patch.object(frappe, "has_permission", side_effect=allowed):
			section = self.workspace().get_capabilities()["sections"]["lay_sheet_planner"]
		self.assertEqual(section["doctype"], "SD YRP Cutting Laysheet Planner")
		self.assertEqual(section["label"], "LaySheet Planner")
		self.assertTrue(section["can_read"])
		self.assertTrue(section["can_create"])
		self.assertFalse(section["can_write"])

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
		self.attachments = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for file_name in self.attachments:
			if frappe.db.exists("File", file_name):
				frappe.delete_doc("File", file_name, ignore_permissions=True)
		super().tearDown()

	def make_attachment(self, *, product=None, table="product_designs", filename=None):
		product = product or self.product
		filename = filename or f"{frappe.generate_hash(length=10)}.png"
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": filename,
				"content": b"image",
				"is_private": 1,
				"attached_to_doctype": web_workspace.PRODUCT,
				"attached_to_name": product.name,
				"attached_to_field": table,
			}
		).insert(ignore_permissions=True)
		self.attachments.append(file_doc.name)
		return file_doc

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

	def test_set_colour_links_save_with_fetched_codes_and_trim_options(self):
		colours = []
		for code in ["#123456", "#654321"]:
			colour = frappe.get_doc({
				"doctype": "SD YRP Product Colour Code",
				"colour": f"Set colour {frappe.generate_hash(length=10)}", "colour_code": code,
			}).insert()
			colour.submit()
			colours.append(colour)
		payload = web_workspace.save_product(
			{"is_set_item": 1, "product_set_colours": [{
				"top_colour": colours[0].name, "bottom_colour": colours[1].name,
			}]}, name=self.product.name, expected_modified=str(self.product.modified),
		)
		row = payload["record"]["product_set_colours"][0]
		self.assertEqual(row["top_colour"], colours[0].name)
		self.assertEqual(row["bottom_colour"], colours[1].name)
		self.assertEqual(row["top_colour_code"], "#123456")
		self.assertEqual(row["bottom_colour_code"], "#654321")
		self.product.reload()
		self.assertEqual(self.product.product_set_colours[0].top_colour_code, "#123456")
		self.assertEqual(self.product.product_set_colours[0].bottom_colour_code, "#654321")
		self.assertEqual(payload["colours"]["top"][0]["colour"], colours[0].name)
		self.assertEqual(payload["colours"]["bottom"][0]["colour"], colours[1].name)
		self.assertEqual(payload["link_filters"]["product_set_colours.top_colour"], {"docstatus": 1})
		self.assertEqual(payload["link_filters"]["product_set_colours.bottom_colour"], {"docstatus": 1})

	def test_save_updates_fields_and_ignores_unlisted_fields(self):
		payload = web_workspace.save_product(
			{"item_name": "Renamed", "tech_pack_no": 99},
			name=self.product.name,
			expected_modified=str(self.product.modified),
		)
		self.assertEqual(payload["record"]["item_name"], "Renamed")
		self.assertNotEqual(payload["record"]["tech_pack_no"], 99)

	def test_save_persists_staged_silhouette_and_graphic_rows(self):
		silhouette = self.make_attachment(table="product_image", filename="staged-silhouette.png")
		graphic = self.make_attachment(filename="staged-graphic.png")
		payload = web_workspace.save_product(
			{
				"product_image": silhouette.file_url,
				"product_designs": [
					{
						"graphic_image": graphic.file_url,
						"upload_name": "Option 5",
						"filename": "untrusted-name.png",
						"file": graphic.name,
					}
				],
			},
			name=self.product.name,
			expected_modified=str(self.product.modified),
		)

		self.assertEqual(
			payload["record"]["product_image"], silhouette.file_url
		)
		self.assertEqual(payload["record"]["product_designs"][0]["upload_name"], "Option 5")
		self.assertEqual(payload["record"]["product_designs"][0]["filename"], graphic.file_name)

	def test_save_rejects_nonexistent_graphic_file(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not found"):
			web_workspace.save_product(
				{
					"product_designs": [{
						"file": "missing-file",
						"graphic_image": "/private/files/missing.png",
					}]
				},
				name=self.product.name,
				expected_modified=str(self.product.modified),
			)

	def test_save_rejects_graphic_file_attached_to_another_product(self):
		foreign_file = self.make_attachment(product=make_product())
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong"):
			web_workspace.save_product(
				{"product_designs": [{"file": foreign_file.name, "graphic_image": foreign_file.file_url}]},
				name=self.product.name,
				expected_modified=str(self.product.modified),
			)

	def test_save_rejects_mismatched_graphic_file_url_and_table(self):
		graphic = self.make_attachment(table="product_box_details")
		with self.assertRaisesRegex(frappe.ValidationError, "Product table"):
			web_workspace.save_product(
				{"product_designs": [{"file": graphic.name, "graphic_image": graphic.file_url}]},
				name=self.product.name,
				expected_modified=str(self.product.modified),
			)

		graphic = self.make_attachment()
		with self.assertRaisesRegex(frappe.ValidationError, "URL does not match"):
			web_workspace.save_product(
				{"product_designs": [{"file": graphic.name, "graphic_image": "/files/other.png"}]},
				name=self.product.name,
				expected_modified=str(self.product.modified),
			)

	def test_graphic_tables_follow_submitted_order_after_removal_and_upload(self):
		initial_rows = {}
		for table in ("product_designs", "product_box_details"):
			initial_rows[table] = []
			for number in range(1, 4):
				file_doc = self.make_attachment(table=table, filename=f"{table}-{number}.png")
				initial_rows[table].append({
					"upload_name": f"Option {number}",
					"graphic_image": file_doc.file_url,
					"file": file_doc.name,
				})
		web_workspace.save_product(
			initial_rows,
			name=self.product.name,
			expected_modified=str(self.product.modified),
		)
		self.product.reload()

		next_rows = {}
		for table in ("product_designs", "product_box_details"):
			survivor = self.product.get(table)[2].as_dict()
			uploaded = self.make_attachment(table=table, filename=f"{table}-new.png")
			next_rows[table] = [survivor, {
				"upload_name": "New upload",
				"graphic_image": uploaded.file_url,
				"file": uploaded.name,
			}]
		web_workspace.save_product(
			next_rows,
			name=self.product.name,
			expected_modified=str(self.product.modified),
		)
		self.product.reload()

		for table in ("product_designs", "product_box_details"):
			self.assertEqual(
				[(row.idx, row.upload_name) for row in self.product.get(table)],
				[(1, "Option 3"), (2, "New upload")],
			)

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

		self.assertIn(colour, {row["name"] for row in result["options"]})
		matched = next(row for row in result["options"] if row["name"] == colour)
		self.assertEqual(matched["colour_code"], colour_code)
		self.assertFalse(result["exact_name_exists"])

	def test_colour_search_detects_draft_exact_name_case_insensitively(self):
		colour = f"PD Web Draft {frappe.generate_hash(length=10)}"
		frappe.get_doc(
			{
				"doctype": web_workspace.COLOUR_CODE,
				"colour": colour,
				"colour_code": "#123456",
			}
		).insert()

		result = web_workspace.search_submitted_colour_codes(colour.swapcase())

		self.assertTrue(result["exact_name_exists"])
		self.assertNotIn(colour, {row["name"] for row in result["options"]})

	def test_colour_search_detects_exact_name_beyond_option_limit(self):
		colour = f"PD Web Limited {frappe.generate_hash(length=10)}"
		limited_options = [{"name": f"Earlier {index} {colour}"} for index in range(50)]
		with patch.object(
			frappe, "get_list", side_effect=[limited_options, [colour]]
		) as get_list:
			result = web_workspace.search_submitted_colour_codes(colour)

		self.assertEqual(result["options"], limited_options)
		self.assertNotIn(colour, {row["name"] for row in result["options"]})
		self.assertTrue(result["exact_name_exists"])
		self.assertEqual(get_list.call_args_list[1].kwargs["filters"], {"name": colour})
		self.assertEqual(get_list.call_args_list[1].kwargs["limit_page_length"], 1)

	def colour_user(self, *, can_create, can_write, can_submit, can_read=True):
		token = frappe.generate_hash(length=8)
		role = f"Test PD Colour {token}"
		email = f"pd-colour-{frappe.generate_hash(length=8)}@example.com"
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)
		permission_doctype = (
			"Custom DocPerm"
			if frappe.db.exists("Custom DocPerm", {"parent": web_workspace.COLOUR_CODE})
			else "DocPerm"
		)
		permission = frappe.get_doc(
			{
				"doctype": permission_doctype,
				"parent": web_workspace.COLOUR_CODE,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"read": int(can_read),
				"create": int(can_create),
				"write": int(can_write),
				"submit": int(can_submit),
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "PD Colour",
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(self.cleanup_colour_user, email, role, permission_doctype, permission.name)
		frappe.clear_cache(doctype=web_workspace.COLOUR_CODE)
		frappe.clear_cache(user=email)
		frappe.set_user(email)

	def cleanup_colour_user(self, email, role, permission_doctype, permission):
		frappe.set_user("Administrator")
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		if frappe.db.exists(permission_doctype, permission):
			frappe.db.delete(permission_doctype, {"name": permission})
		if frappe.db.exists("Role", role):
			frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
		frappe.clear_cache(doctype=web_workspace.COLOUR_CODE)
		frappe.clear_cache(user=email)

	def test_create_colour_code_submits_when_user_can_submit(self):
		self.colour_user(can_create=True, can_write=True, can_submit=True)
		colour = f"pd web orange {frappe.generate_hash(length=8)}"

		created = web_workspace.create_colour_code(f"  {colour} ", "#FF8800")

		self.assertEqual(created["name"], colour)
		self.assertEqual(created["colour_code"], "#FF8800")
		self.assertEqual(created["docstatus"], 1)
		result = web_workspace.search_submitted_colour_codes(colour)
		self.assertIn(colour, {row["name"] for row in result["options"]})

	def test_create_colour_code_stays_draft_without_submit_permission(self):
		self.colour_user(can_create=True, can_write=True, can_submit=False)
		colour = f"pd web draft {frappe.generate_hash(length=8)}"

		created = web_workspace.create_colour_code(colour, "#123456")

		self.assertEqual(created["docstatus"], 0)
		self.assertEqual(frappe.db.get_value("SD YRP Product Colour Code", colour, "docstatus"), 0)

	def test_create_colour_code_checks_permission_before_existing_lookup(self):
		colour = f"pd web denied {frappe.generate_hash(length=8)}"
		web_workspace.create_colour_code(colour, "#123456")
		self.colour_user(
			can_create=False,
			can_write=False,
			can_submit=False,
			can_read=False,
		)
		with self.assertRaises(frappe.PermissionError):
			web_workspace.create_colour_code(colour, "#654321")

	def test_create_colour_code_rejects_invalid_hex(self):
		with self.assertRaises(frappe.ValidationError):
			web_workspace.create_colour_code(f"pd web bad {frappe.generate_hash(length=8)}", "orange")

	def test_create_colour_code_rejects_existing_colour(self):
		colour = f"pd web existing {frappe.generate_hash(length=8)}"
		web_workspace.create_colour_code(colour, "#123456")
		with self.assertRaisesRegex(frappe.DuplicateEntryError, "already exists"):
			web_workspace.create_colour_code(colour.upper(), "#654321")

	def test_create_colour_code_is_post_only_and_not_guest(self):
		function = web_workspace.create_colour_code
		self.assertIn(function, frappe.whitelisted)
		self.assertNotIn(function, frappe.guest_methods)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[function], ["POST"])

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
