from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import purchase_order_against as against
from essdee_yrp.fabric_store.documents.purchase_order import _capability_candidates

MODULE = "essdee_yrp.purchase_order_against"
FIELD = against.PRODUCTION_ORDERS_FIELD


def linked(name) -> list[str]:
	return against.get_stored_production_orders(name)


class TestPurchaseOrderPpoLinks(IntegrationTestCase):
	"""Add PPO on a Draft Purchase Order, run against site data inside the test transaction."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.open_orders = frappe.get_all(
			against.PRODUCTION_ORDER_DOCTYPE,
			filters={"docstatus": 1, "status": "Open"},
			fields=["name", "item"],
			order_by="creation asc",
			limit_page_length=3,
		)
		self.purchase_order = frappe.get_value(
			"Purchase Order", {"docstatus": 0, "is_yrp_managed": 1, "status": "Draft"}, "name", order_by="creation asc"
		)
		if len(self.open_orders) < 3 or not self.purchase_order:
			self.skipTest("Needs a Draft YRP Purchase Order and three open Production Orders.")
		frappe.db.delete(against.PRODUCTION_ORDER_ROW_DOCTYPE, {"parenttype": "Purchase Order", "parent": self.purchase_order})
		self.first, self.second, self.third = (row.name for row in self.open_orders)

	def update(self, names, name=None):
		with patch(f"{MODULE}.get_live_request", return_value=None):
			return against.update_purchase_order_production_orders(name or self.purchase_order, names)

	def test_add_in_draft_fills_item_name_and_records_timeline(self):
		rows = self.update([self.first, self.second])
		self.assertEqual([row["production_order"] for row in rows], [self.first, self.second])
		self.assertEqual(rows[0]["item_name"], self.open_orders[0].item)
		self.assertEqual(linked(self.purchase_order), [self.first, self.second])
		comment = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Purchase Order", "reference_name": self.purchase_order, "comment_type": "Comment"},
			pluck="content",
			order_by="creation desc",
			limit_page_length=1,
		)[0]
		self.assertIn(f"Added PPO {self.first}, {self.second}", comment)
		self.assertTrue(frappe.db.exists("Version", {"ref_doctype": "Purchase Order", "docname": self.purchase_order}))

	def test_duplicates_are_dropped_and_rows_keep_order(self):
		self.update([self.first])
		self.update([self.first, self.second, self.second])
		self.assertEqual(linked(self.purchase_order), [self.first, self.second])

	def test_remove_and_replace_in_draft(self):
		self.update([self.first, self.second])
		self.update([self.second, self.third])
		self.assertEqual(linked(self.purchase_order), [self.second, self.third])
		self.update([])
		self.assertEqual(linked(self.purchase_order), [])

	def test_closed_production_order_is_rejected(self):
		closed = frappe.get_value(against.PRODUCTION_ORDER_DOCTYPE, {"docstatus": 1, "status": "Closed"}, "name")
		if not closed:
			self.skipTest("Needs a closed Production Order.")
		with self.assertRaises(frappe.ValidationError):
			self.update([self.first, closed])
		self.assertEqual(linked(self.purchase_order), [])

	def test_submit_permission_is_required(self):
		def permission(_doctype, ptype="read", *args, **kwargs):
			return ptype != "submit"

		with patch(f"{MODULE}.frappe.has_permission", side_effect=permission), self.assertRaises(frappe.PermissionError):
			self.update([self.first])
		doc = frappe.get_doc("Purchase Order", self.purchase_order)
		with patch(f"{MODULE}.frappe.has_permission", side_effect=permission):
			self.assertFalse(against.can_manage_production_orders(doc))

	def submitted(self, is_development):
		name = frappe.get_value("Purchase Order", {"docstatus": 1, "is_yrp_managed": 1}, "name", order_by="creation asc")
		frappe.db.delete(against.PRODUCTION_ORDER_ROW_DOCTYPE, {"parenttype": "Purchase Order", "parent": name})
		frappe.db.set_value("Purchase Order", name, "is_development", is_development, update_modified=False)
		return name

	def test_submitted_without_development_is_refused(self):
		name = self.submitted(0)
		doc = frappe.get_doc("Purchase Order", name)
		self.assertFalse(against.can_manage_production_orders(doc))
		self.assertFalse(_capability_candidates(doc, {}, {})["update_production_orders"]["eligible"])
		with self.assertRaisesRegex(frappe.ValidationError, "Development"):
			self.update([self.first], name=name)

	def test_submitted_development_adds_once_and_never_removes(self):
		name = self.submitted(1)
		doc = frappe.get_doc("Purchase Order", name)
		self.assertTrue(against.can_manage_production_orders(doc))
		self.assertFalse(against.can_remove_production_orders(doc))
		self.update([self.first, self.second], name=name)
		self.assertEqual(linked(name), [self.first, self.second])
		doc = frappe.get_doc("Purchase Order", name)
		self.assertEqual(doc.docstatus, 1)
		self.assertFalse(against.can_manage_production_orders(doc))
		self.assertFalse(_capability_candidates(doc, {}, {})["update_production_orders"]["eligible"])
		for names in ([self.first], [self.first, self.second, self.third]):
			with self.subTest(names=names), self.assertRaisesRegex(frappe.ValidationError, "Development"):
				self.update(names, name=name)
		self.assertEqual(linked(name), [self.first, self.second])

	def test_cancelled_purchase_order_is_refused(self):
		name = frappe.get_value("Purchase Order", {"docstatus": 2, "is_yrp_managed": 1}, "name")
		self.assertFalse(against.can_manage_production_orders(frappe.get_doc("Purchase Order", name)))
		with self.assertRaisesRegex(frappe.ValidationError, "cancelled"):
			self.update([self.first], name=name)

	def test_live_telegram_request_allows_add_but_blocks_removal(self):
		self.update([self.first])
		live = frappe._dict(name="REQ-1", status="Pending")
		doc = frappe.get_doc("Purchase Order", self.purchase_order)
		with patch(f"{MODULE}.get_live_request", return_value=live):
			self.assertTrue(against.can_manage_production_orders(doc))
			self.assertFalse(against.can_remove_production_orders(doc))
			against.update_purchase_order_production_orders(self.purchase_order, [self.first, self.second])
			with self.assertRaisesRegex(frappe.ValidationError, "REQ-1"):
				against.update_purchase_order_production_orders(self.purchase_order, [self.second])
		self.assertEqual(linked(self.purchase_order), [self.first, self.second])
		with patch(f"{MODULE}.get_live_request", return_value=None):
			self.assertTrue(against.can_remove_production_orders(doc))

	def test_manual_table_edit_is_still_blocked(self):
		self.update([self.first])
		doc = frappe.get_doc("Purchase Order", self.purchase_order)
		doc.append(FIELD, {"production_order": self.second})
		with self.assertRaisesRegex(frappe.ValidationError, "Production Orders cannot be changed"):
			against.validate_purchase_order_against_unchanged(doc)

	def test_onload_exposes_the_flag(self):
		doc = frappe.get_doc("Purchase Order", self.purchase_order)
		with patch(f"{MODULE}.get_live_request", return_value=None):
			against.set_production_order_onload(doc)
		self.assertTrue(doc.get_onload().can_manage_production_orders)
		self.assertTrue(doc.get_onload().can_remove_production_orders)

	def test_search_matches_id_or_item(self):
		target = self.open_orders[0]
		by_id = against.search_production_orders(target.name)
		self.assertIn(target.name, [row["name"] for row in by_id])
		self.assertEqual(next(row for row in by_id if row["name"] == target.name)["description"], target.item)
		by_item = against.search_production_orders(target.item)
		self.assertIn(target.name, [row["name"] for row in by_item])
		self.assertTrue(all(target.item in (row["item"] or "") or target.item in row["name"] for row in by_item))
		desk = against.production_order_query("YRP Production Order", target.item, "name", 0, 20, {})
		self.assertIn((target.name, target.item), desk)
		closed = frappe.get_value(against.PRODUCTION_ORDER_DOCTYPE, {"docstatus": 1, "status": "Closed"}, "name")
		if closed:
			self.assertNotIn(closed, [row["name"] for row in against.search_production_orders(closed)])
