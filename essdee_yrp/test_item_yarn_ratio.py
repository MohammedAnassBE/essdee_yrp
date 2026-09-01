"""Item yarn-ratio validation and SD YRP synchronization tests."""

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.sd_yrp_sync import upsert_item


def _ensure_group():
	name = "_Test Item Yarn Ratio Group"
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": name,
			"is_group": 0,
			"parent_item_group": "All Item Groups",
		}).insert(ignore_permissions=True)
	return name


def _ensure_uom():
	if not frappe.db.exists("UOM", "Kg"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Kg"}).insert(
			ignore_permissions=True
		)
	return "Kg"


def _ensure_yarn(name):
	if not frappe.db.exists("Item", name):
		frappe.get_doc({
			"doctype": "Item",
			"name1": name,
			"item_group": _ensure_group(),
			"default_unit_of_measure": _ensure_uom(),
			"is_stock_item": 1,
		}).insert(ignore_permissions=True)
	return name


def _add_yarn_attribute(yarn, attribute):
	if not frappe.db.exists("Item Attribute", attribute):
		frappe.get_doc({
			"doctype": "Item Attribute",
			"attribute_name": attribute,
		}).insert(ignore_permissions=True)
	doc = frappe.get_doc("Item", yarn)
	if attribute not in {row.attribute for row in doc.get("attributes") or []}:
		doc.append("attributes", {"attribute": attribute})
		doc.save(ignore_permissions=True)


class TestItemYarnRatio(IntegrationTestCase):
	def setUp(self):
		self.yarn_a = _ensure_yarn("_Test Synced Yarn A")
		self.yarn_b = _ensure_yarn("_Test Synced Yarn B")
		self.cloth = "_Test Synced Cloth Recipe"

	def _payload(self, rows):
		return {
			"doctype": "Item",
			"name": self.cloth,
			"name1": self.cloth,
			"item_group": _ensure_group(),
			"default_unit_of_measure": _ensure_uom(),
			"is_stock_item": 1,
			"is_cloth_item": 1,
			"yarn_ratio_details": rows,
		}

	def test_sync_inserts_and_replaces_item_yarn_ratio_rows(self):
		upsert_item(self._payload([
			{
				"doctype": "Item Yarn Ratio",
				"name": "_test-sync-yarn-row-a",
				"yarn_item": self.yarn_a,
				"ratio": 60,
			},
			{
				"doctype": "Item Yarn Ratio",
				"name": "_test-sync-yarn-row-b",
				"yarn_item": self.yarn_b,
				"ratio": 40,
			},
		]))
		item = frappe.get_doc("Item", self.cloth)
		self.assertEqual(
			[(row.yarn_item, row.ratio) for row in item.yarn_ratio_details],
			[(self.yarn_a, 60), (self.yarn_b, 40)],
		)

		upsert_item(self._payload([
			{
				"doctype": "Item Yarn Ratio",
				"name": "_test-sync-yarn-row-a2",
				"yarn_item": self.yarn_a,
				"ratio": 100,
			},
		]))
		item.reload()
		self.assertEqual(
			[(row.yarn_item, row.ratio) for row in item.yarn_ratio_details],
			[(self.yarn_a, 100)],
		)

	def test_colour_is_the_supported_yarn_variant_attribute(self):
		colour_yarn = _ensure_yarn("_Test Colour Variant Yarn")
		_add_yarn_attribute(colour_yarn, "Colour")
		upsert_item(self._payload([{
			"doctype": "Item Yarn Ratio",
			"yarn_item": colour_yarn,
			"ratio": 100,
		}]))
		self.assertEqual(
			frappe.get_doc("Item", self.cloth).yarn_ratio_details[0].yarn_item,
			colour_yarn,
		)

		unsupported_yarn = _ensure_yarn("_Test Unsupported Variant Yarn")
		_add_yarn_attribute(unsupported_yarn, "Dia")
		with self.assertRaisesRegex(frappe.ValidationError, "may only use the Colour"):
			upsert_item(self._payload([{
				"doctype": "Item Yarn Ratio",
				"yarn_item": unsupported_yarn,
				"ratio": 100,
			}]))

	def test_sync_rejects_non_100_ratio(self):
		with self.assertRaisesRegex(frappe.ValidationError, "exactly 100"):
			upsert_item(self._payload([
				{
					"doctype": "Item Yarn Ratio",
					"yarn_item": self.yarn_a,
					"ratio": 90,
				},
			]))
