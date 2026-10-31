from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

import frappe

from essdee_yrp import purchase_order_against as against
from essdee_yrp.fabric_store.documents.purchase_order import (
	get_purchase_order_editor,
	save_purchase_order_document,
)
from essdee_yrp.sales.web_workspace import _production_order_actions

MODULE = "essdee_yrp.purchase_order_against"
SERVICE = "essdee_yrp.fabric_store.documents.purchase_order"
ITEM_DETAILS = [{"items": [{"name": "ITEM"}]}]


def production_order(docstatus=1, status="Open", readable=True):
	doc = frappe._dict(doctype="YRP Production Order", name="PPO-1", docstatus=docstatus, status=status)
	doc.check_permission = Mock(side_effect=None if readable else frappe.PermissionError)
	return doc


class TestPurchaseOrderAgainst(TestCase):
	def resolve(self, ppo, exists=True):
		with (
			patch(f"{MODULE}.frappe.db.exists", return_value=exists),
			patch(f"{MODULE}.frappe.get_doc", return_value=ppo),
		):
			return against.get_purchase_order_against("YRP Production Order", "PPO-1")

	def test_custom_fields_are_read_only_source_links(self):
		meta = frappe.get_meta("Purchase Order")
		source = meta.get_field("against")
		reference = meta.get_field("against_id")
		self.assertEqual((source.fieldtype, source.options, source.label), ("Link", "DocType", "Against"))
		self.assertEqual((reference.fieldtype, reference.options, reference.label), ("Dynamic Link", "against", "Against ID"))
		for field in (source, reference):
			self.assertTrue(field.read_only)
			self.assertTrue(field.no_copy)

	def test_open_production_order_resolves_to_field_values(self):
		ppo = production_order()
		self.assertEqual(self.resolve(ppo), {"against": "YRP Production Order", "against_id": "PPO-1"})
		ppo.check_permission.assert_called_once_with("read")

	def test_closed_draft_and_cancelled_production_orders_are_rejected(self):
		for docstatus, status in ((1, "Closed"), (0, "Draft"), (0, "PPO Request"), (2, "Open")):
			with self.subTest(docstatus=docstatus, status=status), self.assertRaises(frappe.ValidationError):
				self.resolve(production_order(docstatus, status))

	def test_unreadable_missing_and_unsupported_sources_are_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			self.resolve(production_order(readable=False))
		with self.assertRaises(frappe.DoesNotExistError):
			self.resolve(production_order(), exists=False)
		with self.assertRaises(frappe.ValidationError):
			against.get_purchase_order_against("Item", "ITEM-1")
		with self.assertRaises(frappe.ValidationError):
			against.get_purchase_order_against("YRP Production Order", "")
		self.assertEqual(against.get_purchase_order_against(None, None), {})

	def test_create_capability_needs_open_production_order_and_create_permission(self):
		cases = {
			(1, "Open", True): True,
			(1, "Not Processed", True): True,
			(1, "Pending Request", True): True,
			(1, "Closed", True): False,
			(0, "Draft", True): False,
			(2, "Open", True): False,
			(1, "Open", False): False,
		}
		for (docstatus, status, can_create), expected in cases.items():
			with (
				self.subTest(docstatus=docstatus, status=status, can_create=can_create),
				patch(f"{MODULE}.frappe.has_permission", return_value=can_create) as has_permission,
			):
				self.assertIs(against.can_create_purchase_order_against(production_order(docstatus, status)), expected)
				if docstatus == 1 and status != "Closed":
					has_permission.assert_called_once_with("Purchase Order", ptype="create")

	def test_production_order_actions_expose_create_purchase_order(self):
		permissions = {key: True for key in ("can_print", "can_write", "can_delete", "can_cancel", "can_create")}
		for status, can_create, expected in (("Open", True, True), ("Closed", True, False), ("Open", False, False)):
			doc = production_order(status=status)
			with (
				self.subTest(status=status, can_create=can_create),
				patch(f"{MODULE}.frappe.has_permission", return_value=can_create),
			):
				actions = _production_order_actions(doc, permissions, {})
			self.assertIs(actions["create_purchase_order"]["allowed"], expected)
			self.assertEqual(actions["create_purchase_order"]["label"], "Create PO")

	def test_before_insert_validates_new_documents(self):
		with patch(f"{MODULE}.get_purchase_order_against") as resolve:
			against.validate_new_purchase_order_against(frappe._dict(against="YRP Production Order", against_id="PPO-1"))
		resolve.assert_called_once_with("YRP Production Order", "PPO-1")

	def test_amendment_skips_only_an_unchanged_inherited_reference(self):
		original = frappe._dict(against="YRP Production Order", against_id="PPO-1")
		cases = (
			(("YRP Production Order", "PPO-1"), False),
			(("YRP Production Order", "PPO-2"), True),
			(("Item", "PPO-1"), True),
			((None, None), True),
		)
		for (source, reference), validated in cases:
			amendment = frappe._dict(against=source, against_id=reference, amended_from="PO-1")
			with (
				self.subTest(reference=reference),
				patch(f"{MODULE}.frappe.db.get_value", return_value=original),
				patch(f"{MODULE}.get_purchase_order_against") as resolve,
			):
				against.validate_new_purchase_order_against(amendment)
			if validated:
				resolve.assert_called_once_with(source, reference)
			else:
				resolve.assert_not_called()
		# A reference added to an amendment of an unlinked PO is validated like a new one.
		with (
			patch(f"{MODULE}.frappe.db.get_value", return_value=frappe._dict(against=None, against_id=None)),
			patch(f"{MODULE}.get_purchase_order_against") as resolve,
		):
			against.validate_new_purchase_order_against(frappe._dict(against="YRP Production Order", against_id="PPO-9", amended_from="PO-1"))
		resolve.assert_called_once_with("YRP Production Order", "PPO-9")

	def test_saved_purchase_order_cannot_change_its_reference(self):
		stored = frappe._dict(against="YRP Production Order", against_id="PPO-1")

		def saved(**values):
			doc = frappe._dict(name="PO-1", **values)
			doc.flags = frappe._dict()
			doc.is_new = lambda: False
			return doc

		with patch(f"{MODULE}.frappe.db.get_value", return_value=stored):
			against.validate_purchase_order_against_unchanged(saved(against="YRP Production Order", against_id="PPO-1"))
			for values in ({"against": "YRP Production Order", "against_id": "PPO-2"}, {"against": "Item", "against_id": "PPO-1"}, {}):
				with self.subTest(values=values), self.assertRaises(frappe.ValidationError):
					against.validate_purchase_order_against_unchanged(saved(**values))
		with patch(f"{MODULE}.frappe.db.get_value", return_value=frappe._dict(against=None, against_id="")):
			against.validate_purchase_order_against_unchanged(saved())
			with self.assertRaises(frappe.ValidationError):
				against.validate_purchase_order_against_unchanged(saved(against="YRP Production Order", against_id="PPO-1"))

	def test_hooks_cover_insert_save_submit_and_update_after_submit(self):
		hooks = frappe.get_hooks("doc_events")["Purchase Order"]
		self.assertIn(f"{MODULE}.validate_new_purchase_order_against", hooks["before_insert"])
		for event in ("validate", "before_update_after_submit"):
			self.assertIn(f"{MODULE}.validate_purchase_order_against_unchanged", hooks[event])

	def test_linked_purchase_orders_require_read_permission_per_document(self):
		rows = [frappe._dict(name="PO-1"), frappe._dict(name="PO-2")]

		def permission(_doctype, ptype="read", doc=None, **_kwargs):
			return doc != "PO-2"

		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=permission),
			patch(f"{MODULE}.frappe.get_list", return_value=rows),
		):
			self.assertEqual(against.get_purchase_orders_against("YRP Production Order", "PPO-1"), [rows[0]])

		select_only = lambda _doctype, ptype="read", **_kwargs: ptype == "select"  # noqa: E731
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=select_only),
			patch(f"{MODULE}.frappe.get_list") as get_list,
		):
			self.assertEqual(against.get_purchase_orders_against("YRP Production Order", "PPO-1"), [])
		get_list.assert_not_called()


class TestPurchaseOrderCreatePath(TestCase):
	def new_document(self):
		doc = frappe._dict(doctype="Purchase Order", name=None, docstatus=0)
		doc.set = lambda key, value: doc.__setitem__(key, value)
		doc.insert = MagicMock(side_effect=lambda: setattr(doc, "name", "PO-NEW"))
		return doc

	def save(self, doc, values, name=None):
		with (
			patch(f"{SERVICE}.frappe.has_permission", return_value=True),
			patch(f"{SERVICE}.frappe.new_doc", return_value=doc),
			patch(f"{SERVICE}._get_purchase_order", return_value=doc),
			patch(f"{SERVICE}.assert_expected_modified"),
			patch(f"{SERVICE}.ungroup_items_from_ui", return_value=[{"item_code": "ITEM", "qty": 1}]),
			patch(f"{SERVICE}.get_purchase_order_workspace", side_effect=lambda docname: {"record": {"name": docname}}),
		):
			return save_purchase_order_document({"item_details": ITEM_DETAILS, **values}, name=name)

	def test_new_purchase_order_carries_validated_against_fields(self):
		doc = self.new_document()
		with patch(f"{MODULE}.frappe.db.exists", return_value=True), patch(f"{MODULE}.frappe.get_doc", return_value=production_order()):
			result = self.save(doc, {"supplier": "SUP", "against": "YRP Production Order", "against_id": "PPO-1"})
		self.assertEqual((doc.against, doc.against_id), ("YRP Production Order", "PPO-1"))
		doc.insert.assert_called_once()
		self.assertEqual(result["record"]["name"], "PO-NEW")

	def test_closed_production_order_is_rejected_before_insert(self):
		doc = self.new_document()
		with (
			patch(f"{MODULE}.frappe.db.exists", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=production_order(status="Closed")),
			self.assertRaises(frappe.ValidationError),
		):
			self.save(doc, {"against": "YRP Production Order", "against_id": "PPO-1"})
		doc.insert.assert_not_called()

	def test_existing_purchase_order_ignores_submitted_against_values(self):
		doc = self.new_document()
		doc.name = "PO-1"
		doc.save = MagicMock()
		self.save(doc, {"against": "YRP Production Order", "against_id": "PPO-9"}, name="PO-1")
		self.assertNotIn("against_id", doc)
		doc.save.assert_called_once()

	def test_new_editor_is_prefilled_from_source(self):
		doc = frappe._dict(doctype="Purchase Order", docstatus=0)
		with (
			patch(f"{SERVICE}.frappe.has_permission", return_value=True),
			patch(f"{SERVICE}.frappe.new_doc", return_value=doc),
			patch(f"{SERVICE}.group_items_for_ui", return_value=[]),
			patch(f"{SERVICE}.get_stock_dimensions_for_ui", return_value=[]),
			patch(f"{SERVICE}.get_effective_fields", return_value=[]) as effective_fields,
			patch(f"{SERVICE}.frappe.db.get_single_value", return_value=0),
			patch(f"{MODULE}.frappe.db.exists", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=production_order()),
		):
			editor = get_purchase_order_editor(source={"against": "YRP Production Order", "against_id": "PPO-1"})
		self.assertEqual(editor["values"]["against"], "YRP Production Order")
		self.assertEqual(editor["values"]["against_id"], "PPO-1")
		self.assertIn("against_id", effective_fields.call_args.args[1])


class TestPurchaseOrderAgainstSiteData(TestCase):
	def test_real_open_and_closed_production_orders(self):
		open_order = frappe.db.get_value("YRP Production Order", {"docstatus": 1, "status": "Open"})
		closed_order = frappe.db.get_value("YRP Production Order", {"docstatus": 1, "status": "Closed"})
		if not open_order or not closed_order:
			self.skipTest("Site has no open and closed Production Orders.")
		self.assertEqual(
			against.get_purchase_order_against("YRP Production Order", open_order)["against_id"],
			open_order,
		)
		with self.assertRaises(frappe.ValidationError):
			against.get_purchase_order_against("YRP Production Order", closed_order)
		self.assertTrue(against.can_create_purchase_order_against(SimpleNamespace(docstatus=1, get=lambda _key: "Open")))


class TestApprovalItemLimitWithoutProductionOrder(TestCase):
	def purchase_order(self, *rows, docstatus=0, against_id=None):
		items = [frappe._dict(idx=index, **row) for index, row in enumerate(rows, start=1)]
		return frappe._dict(docstatus=docstatus, against="YRP Production Order" if against_id else None, against_id=against_id, items=items)

	def check(self, doc, limit=None, conversions=None):
		conversions = conversions or {}

		def conversion(_doctype, filters, _field):
			return conversions.get((filters["from_uom"], filters["to_uom"]))

		with (
			patch(f"{MODULE}.frappe.db.get_single_value", return_value=limit),
			patch(f"{MODULE}.get_approval_item_codes", return_value={"YARN-1", "YARN-2"}) as get_all,
			patch(f"{MODULE}.frappe.db.get_value", side_effect=conversion),
		):
			against.validate_approval_item_limit_without_production_order(doc)
		return get_all

	def test_yarn_up_to_the_limit_is_allowed_and_only_yarn_counts(self):
		get_all = self.check(self.purchase_order(
			{"item_code": "YARN-1", "stock_qty": 300, "stock_uom": "Kg"},
			{"item_code": "YARN-2", "qty": 2, "conversion_factor": 100, "stock_uom": "Kg"},
			{"item_code": "BUTTON", "stock_qty": 5000, "stock_uom": "Kg"},
		))
		self.assertEqual(set(get_all.call_args.args[0]), {"YARN-1", "YARN-2", "BUTTON"})

	def test_approval_rules_with_and_without_against(self):
		from essdee_yrp.purchase_order_approval import apply_draft_approval_status

		row = {"item_code": "YARN-1", "stock_qty": 900, "stock_uom": "Kg"}
		for against_id, over_limit in (("PPO-1", False), (None, True)):
			doc = self.purchase_order(row, against_id=against_id)
			doc.update(is_yrp_managed=1, status="Draft", name="PO-1", flags=frappe._dict())
			with (
				self.subTest(against_id=against_id),
				patch("essdee_yrp.purchase_order_approval.get_approval_item_codes", return_value={"YARN-1"}),
				patch("essdee_yrp.purchase_order_approval._validate_not_locked_for_edit"),
			):
				apply_draft_approval_status(doc)
				self.assertEqual(doc.status, "Pending Approval")
				if over_limit:
					with self.assertRaises(frappe.ValidationError):
						self.check(doc)
				else:
					self.check(doc)

	def test_yarn_over_the_limit_without_production_order_is_rejected(self):
		doc = self.purchase_order({"item_code": "YARN-1", "stock_qty": 620, "stock_uom": "Kg"})
		with self.assertRaises(frappe.ValidationError) as raised:
			self.check(doc)
		self.assertIn(
			"620 kg of approval items exceeds the 500 kg limit for a Purchase Order not raised against a Production Order",
			str(raised.exception),
		)

	def test_production_order_purchase_orders_and_submitted_documents_are_exempt(self):
		row = {"item_code": "YARN-1", "stock_qty": 5000, "stock_uom": "Kg"}
		self.check(self.purchase_order(row, against_id="PPO-1"))
		self.check(self.purchase_order(row, docstatus=1))
		self.check(self.purchase_order(row, docstatus=2))

	def test_settings_override_the_default_limit(self):
		row = {"item_code": "YARN-1", "stock_qty": 150, "stock_uom": "Kg"}
		self.check(self.purchase_order(row), limit=500)
		with self.assertRaises(frappe.ValidationError):
			self.check(self.purchase_order(row), limit=100)
		for unset in (None, 0, ""):
			with patch(f"{MODULE}.frappe.db.get_single_value", return_value=unset):
				self.assertEqual(against.get_approval_item_limit_kg(), 500)

	def test_weight_uoms_convert_to_kg_and_other_uoms_fail_loudly(self):
		grams = {"item_code": "YARN-1", "stock_qty": 600000, "stock_uom": "Gram"}
		with self.assertRaises(frappe.ValidationError):
			self.check(self.purchase_order(grams), conversions={("Kg", "Gram"): 1000})
		self.check(self.purchase_order({**grams, "stock_qty": 400000}), conversions={("Kg", "Gram"): 1000})
		self.check(self.purchase_order({"item_code": "YARN-1", "stock_qty": 0.4, "stock_uom": "Tonne"}), conversions={("Tonne", "Kg"): 1000})
		with self.assertRaises(frappe.ValidationError) as raised:
			self.check(self.purchase_order({"item_code": "YARN-1", "stock_qty": 3, "stock_uom": "Cone"}))
		self.assertIn("cannot be converted to Kg", str(raised.exception))

	def test_limit_hook_and_setting_are_registered(self):
		self.assertIn(
			f"{MODULE}.validate_approval_item_limit_without_production_order",
			frappe.get_hooks("doc_events")["Purchase Order"]["validate"],
		)
		field = frappe.get_meta("SD YRP MRP Settings").get_field("max_approval_item_kg_without_production_order")
		self.assertEqual((field.fieldtype, field.default), ("Float", "500"))
		self.assertEqual(against.DEFAULT_APPROVAL_ITEM_LIMIT_KG, 500)

	def test_real_yarn_item_document_is_checked_without_saving(self):
		yarn_item = frappe.db.get_value("Item", {"item_group": "Purchase - Yarn", "stock_uom": "Kg", "disabled": 0})
		if not yarn_item:
			self.skipTest("Site has no Kg yarn Item.")
		doc = frappe.new_doc("Purchase Order")
		doc.append("items", {"item_code": yarn_item, "qty": 600, "uom": "Kg", "stock_uom": "Kg", "conversion_factor": 1})
		with self.assertRaises(frappe.ValidationError):
			against.validate_approval_item_limit_without_production_order(doc)
		doc.items[0].qty = 500
		against.validate_approval_item_limit_without_production_order(doc)
		doc.items[0].qty = 600
		doc.against, doc.against_id = "YRP Production Order", "PPO-1"
		against.validate_approval_item_limit_without_production_order(doc)
