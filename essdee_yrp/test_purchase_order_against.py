from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

import frappe

from essdee_yrp import purchase_order_against as against
from essdee_yrp.fabric_store.documents.purchase_order import (
	PURCHASE_ORDER_FIELDS,
	get_purchase_order_editor,
	save_purchase_order_document,
)
from essdee_yrp.sales.web_workspace import _production_order_actions

MODULE = "essdee_yrp.purchase_order_against"
SERVICE = "essdee_yrp.fabric_store.documents.purchase_order"
ITEM_DETAILS = [{"items": [{"name": "ITEM"}]}]
ROW_DOCTYPE = "SD YRP Purchase Order Production Order"


def production_order(name="PPO-1", docstatus=1, status="Open", readable=True, item="ITEM-A"):
	doc = frappe._dict(doctype="YRP Production Order", name=name, docstatus=docstatus, status=status, item=item)
	doc.check_permission = Mock(side_effect=None if readable else frappe.PermissionError)
	return doc


def production_orders(*docs):
	"""Patch existence and loading for the given Production Orders."""
	by_name = {doc.name: doc for doc in docs}
	get_doc = frappe.get_doc

	def load(*args, **kwargs):
		return by_name[args[1]] if args and args[0] == "YRP Production Order" else get_doc(*args, **kwargs)

	return (
		patch(f"{MODULE}.frappe.db.exists", side_effect=lambda _doctype, name: name in by_name),
		patch(f"{MODULE}.frappe.get_doc", side_effect=load),
	)


def table(*names):
	return [frappe._dict(production_order=name, item_name=f"ITEM-{name}") for name in names]


def purchase_order(*names, **values):
	doc = frappe._dict(production_orders=table(*names), **values)
	doc.set = lambda key, value: doc.__setitem__(key, value)
	doc.flags = frappe._dict()
	doc.is_new = lambda: not values.get("name")
	return doc


class TestPurchaseOrderProductionOrders(TestCase):
	def rows(self, names, *docs):
		exists, get_doc = production_orders(*docs)
		with exists, get_doc:
			return against.get_production_order_rows(names)

	def test_custom_table_replaces_against_fields(self):
		meta = frappe.get_meta("Purchase Order")
		self.assertIsNone(meta.get_field("against"))
		self.assertIsNone(meta.get_field("against_id"))
		field = meta.get_field("production_orders")
		self.assertEqual((field.fieldtype, field.options, field.label), ("Table", ROW_DOCTYPE, "Production Orders"))
		self.assertTrue(field.read_only)
		self.assertTrue(field.no_copy)
		row_meta = frappe.get_meta(ROW_DOCTYPE)
		self.assertTrue(row_meta.istable)
		self.assertEqual([df.fieldname for df in row_meta.fields], ["production_order", "item_name"])
		self.assertEqual(row_meta.get_field("production_order").options, "YRP Production Order")
		self.assertEqual(row_meta.get_field("item_name").label, "Item Name")
		self.assertTrue(all(df.read_only for df in row_meta.fields))

	def test_single_production_order_gives_one_row(self):
		ppo = production_order()
		self.assertEqual(self.rows(["PPO-1"], ppo), [{"production_order": "PPO-1", "item_name": "ITEM-A"}])
		ppo.check_permission.assert_called_once_with("read")

	def test_several_production_orders_give_one_row_each_in_order(self):
		docs = (production_order("PPO-2", item="ITEM-B"), production_order("PPO-1"))
		self.assertEqual(
			self.rows(table("PPO-2", "PPO-1"), *docs),
			[{"production_order": "PPO-2", "item_name": "ITEM-B"}, {"production_order": "PPO-1", "item_name": "ITEM-A"}],
		)

	def test_closed_draft_and_cancelled_production_orders_are_rejected(self):
		for docstatus, status in ((1, "Closed"), (0, "Draft"), (0, "PPO Request"), (2, "Open")):
			with self.subTest(docstatus=docstatus, status=status), self.assertRaises(frappe.ValidationError):
				self.rows(["PPO-1", "PPO-2"], production_order(), production_order("PPO-2", docstatus=docstatus, status=status))

	def test_unreadable_missing_blank_and_duplicate_selections_are_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			self.rows(["PPO-1"], production_order(readable=False))
		with self.assertRaises(frappe.DoesNotExistError):
			self.rows(["PPO-9"], production_order())
		with self.assertRaises(frappe.ValidationError):
			self.rows([""], production_order())
		with self.assertRaises(frappe.ValidationError) as raised:
			self.rows(["PPO-1", "PPO-1"], production_order())
		self.assertIn("more than once", str(raised.exception))
		self.assertEqual(self.rows([]), [])

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
				doc = production_order(docstatus=docstatus, status=status)
				self.assertIs(against.can_create_purchase_order_against(doc), expected)
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

	def test_make_purchase_order_builds_one_unsaved_po_with_a_row_per_production_order(self):
		exists, get_doc = production_orders(production_order(), production_order("PPO-2", item="ITEM-B"))
		with exists, get_doc, patch(f"{MODULE}.frappe.has_permission", return_value=True):
			result = against.make_purchase_order('["PPO-1", "PPO-2"]')
		self.assertEqual(result["doctype"], "Purchase Order")
		self.assertTrue(result["__islocal"])
		self.assertEqual(result["is_yrp_managed"], 1)
		self.assertEqual(result["naming_series"], "YRP-PO-.YYYY.-")
		self.assertEqual(
			[(row["production_order"], row["item_name"]) for row in result["production_orders"]],
			[("PPO-1", "ITEM-A"), ("PPO-2", "ITEM-B")],
		)
		self.assertNotIn("against", result)

	def test_make_purchase_order_needs_a_selection_and_create_permission(self):
		with patch(f"{MODULE}.frappe.has_permission", return_value=True), self.assertRaises(frappe.ValidationError):
			against.make_purchase_order([])
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=frappe.PermissionError),
			patch(f"{MODULE}.get_production_order_rows") as rows,
			self.assertRaises(frappe.PermissionError),
		):
			against.make_purchase_order(["PPO-1"])
		rows.assert_not_called()

	def test_make_purchase_order_rejects_an_incompatible_selection(self):
		exists, get_doc = production_orders(production_order(), production_order("PPO-2", status="Closed"))
		with exists, get_doc, patch(f"{MODULE}.frappe.has_permission", return_value=True):
			with self.assertRaises(frappe.ValidationError) as raised:
				against.make_purchase_order(["PPO-1", "PPO-2"])
		self.assertIn("PPO-2", str(raised.exception))

	def test_before_insert_validates_and_normalizes_the_table(self):
		doc = purchase_order("PPO-1", "PPO-2")
		resolved = [{"production_order": "PPO-1", "item_name": "A"}, {"production_order": "PPO-2", "item_name": "B"}]
		with patch(f"{MODULE}.get_production_order_rows", return_value=resolved) as resolve:
			against.validate_new_purchase_order_against(doc)
		resolve.assert_called_once_with(["PPO-1", "PPO-2"])
		self.assertEqual(doc.production_orders, resolved)

	def test_amendment_skips_only_an_unchanged_inherited_table(self):
		cases = ((("PPO-1", "PPO-2"), False), (("PPO-1",), True), (("PPO-3",), True), ((), True))
		for names, validated in cases:
			with (
				self.subTest(names=names),
				patch(f"{MODULE}.frappe.get_all", return_value=["PPO-1", "PPO-2"]),
				patch(f"{MODULE}.get_production_order_rows", return_value=[]) as resolve,
			):
				against.validate_new_purchase_order_against(purchase_order(*names, amended_from="PO-1"))
			self.assertIs(resolve.called, validated)

	def test_saved_purchase_order_cannot_change_its_production_orders(self):
		with patch(f"{MODULE}.frappe.get_all", return_value=["PPO-1"]):
			against.validate_purchase_order_against_unchanged(purchase_order("PPO-1", name="PO-1"))
			for names in (("PPO-2",), ("PPO-1", "PPO-2"), ()):
				with self.subTest(names=names), self.assertRaises(frappe.ValidationError):
					against.validate_purchase_order_against_unchanged(purchase_order(*names, name="PO-1"))
		with patch(f"{MODULE}.frappe.get_all", return_value=[]):
			against.validate_purchase_order_against_unchanged(purchase_order(name="PO-1"))
			with self.assertRaises(frappe.ValidationError):
				against.validate_purchase_order_against_unchanged(purchase_order("PPO-1", name="PO-1"))
		with patch(f"{MODULE}.frappe.get_all") as get_all:
			against.validate_purchase_order_against_unchanged(purchase_order("PPO-1"))
		get_all.assert_not_called()

	def test_hooks_cover_insert_save_submit_and_update_after_submit(self):
		hooks = frappe.get_hooks("doc_events")["Purchase Order"]
		self.assertIn(f"{MODULE}.validate_new_purchase_order_against", hooks["before_insert"])
		for event in ("validate", "before_update_after_submit"):
			self.assertIn(f"{MODULE}.validate_purchase_order_against_unchanged", hooks[event])

	def test_linked_purchase_orders_come_from_the_table_and_need_read_permission(self):
		rows = [frappe._dict(name="PO-1"), frappe._dict(name="PO-2")]

		def permission(_doctype, ptype="read", doc=None, **_kwargs):
			return doc != "PO-2"

		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=permission),
			patch(f"{MODULE}.frappe.get_all", return_value=["PO-1", "PO-2"]) as get_all,
			patch(f"{MODULE}.frappe.get_list", return_value=rows) as get_list,
		):
			self.assertEqual(against.get_purchase_orders_against("PPO-1"), [rows[0]])
		self.assertEqual(get_all.call_args.args[0], ROW_DOCTYPE)
		self.assertEqual(get_all.call_args.kwargs["filters"]["production_order"], "PPO-1")
		self.assertEqual(get_list.call_args.kwargs["filters"], {"name": ["in", ["PO-1", "PO-2"]]})

		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_all", return_value=[]),
			patch(f"{MODULE}.frappe.get_list") as get_list,
		):
			self.assertEqual(against.get_purchase_orders_against("PPO-1"), [])
		get_list.assert_not_called()

		select_only = lambda _doctype, ptype="read", **_kwargs: ptype == "select"  # noqa: E731
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=select_only),
			patch(f"{MODULE}.frappe.get_all") as get_all,
		):
			self.assertEqual(against.get_purchase_orders_against("PPO-1"), [])
		get_all.assert_not_called()


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

	def test_new_purchase_order_carries_the_validated_table(self):
		doc = self.new_document()
		exists, get_doc = production_orders(production_order(), production_order("PPO-2", item="ITEM-B"))
		with exists, get_doc:
			result = self.save(doc, {"supplier": "SUP", "production_orders": table("PPO-1", "PPO-2")})
		self.assertEqual(
			doc.production_orders,
			[{"production_order": "PPO-1", "item_name": "ITEM-A"}, {"production_order": "PPO-2", "item_name": "ITEM-B"}],
		)
		self.assertNotIn("against_id", doc)
		doc.insert.assert_called_once()
		self.assertEqual(result["record"]["name"], "PO-NEW")

	def test_closed_production_order_is_rejected_before_insert(self):
		doc = self.new_document()
		exists, get_doc = production_orders(production_order(status="Closed"))
		with exists, get_doc, self.assertRaises(frappe.ValidationError):
			self.save(doc, {"production_orders": ["PPO-1"]})
		doc.insert.assert_not_called()

	def test_existing_purchase_order_ignores_submitted_production_orders(self):
		doc = self.new_document()
		doc.name = "PO-1"
		doc.save = MagicMock()
		self.save(doc, {"production_orders": table("PPO-9")}, name="PO-1")
		self.assertNotIn("production_orders", doc)
		doc.save.assert_called_once()

	def test_new_editor_is_prefilled_from_one_or_many_production_orders(self):
		docs = (production_order(), production_order("PPO-2", item="ITEM-B"))
		for names in (["PPO-1"], ["PPO-1", "PPO-2"]):
			doc = frappe._dict(doctype="Purchase Order", docstatus=0)
			doc.set = lambda key, value, doc=doc: doc.__setitem__(key, value)
			exists, get_doc = production_orders(*docs)
			with (
				self.subTest(names=names),
				patch(f"{SERVICE}.frappe.has_permission", return_value=True),
				patch(f"{SERVICE}.frappe.new_doc", return_value=doc),
				patch(f"{SERVICE}.group_items_for_ui", return_value=[]),
				patch(f"{SERVICE}.get_stock_dimensions_for_ui", return_value=[]),
				patch(f"{SERVICE}.get_effective_fields", return_value=[]) as effective_fields,
				patch(f"{SERVICE}.frappe.db.get_single_value", return_value=0),
				exists,
				get_doc,
			):
				editor = get_purchase_order_editor(source={"production_orders": names})
			self.assertEqual([row["production_order"] for row in editor["values"]["production_orders"]], names)
			self.assertEqual(editor["values"]["production_orders"][0]["item_name"], "ITEM-A")
			self.assertNotIn("against_id", editor["values"])
			self.assertNotIn("against_id", effective_fields.call_args.args[1])

	def test_workspace_fields_no_longer_include_against(self):
		self.assertNotIn("against", PURCHASE_ORDER_FIELDS)
		self.assertNotIn("against_id", PURCHASE_ORDER_FIELDS)


class TestPurchaseOrderProductionOrdersSiteData(TestCase):
	def test_real_open_and_closed_production_orders(self):
		open_orders = frappe.get_all("YRP Production Order", {"docstatus": 1, "status": "Open"}, pluck="name", limit=2)
		closed_order = frappe.db.get_value("YRP Production Order", {"docstatus": 1, "status": "Closed"})
		if len(open_orders) < 2 or not closed_order:
			self.skipTest("Site has no two open and one closed Production Orders.")
		rows = against.get_production_order_rows(open_orders)
		self.assertEqual([row["production_order"] for row in rows], open_orders)
		self.assertEqual(rows[0]["item_name"], frappe.db.get_value("YRP Production Order", open_orders[0], "item"))
		with self.assertRaises(frappe.ValidationError):
			against.get_production_order_rows([*open_orders, closed_order])
		self.assertTrue(against.can_create_purchase_order_against(SimpleNamespace(docstatus=1, get=lambda _key: "Open")))

	def test_real_unsaved_purchase_order_table_runs_the_insert_validation(self):
		open_orders = frappe.get_all("YRP Production Order", {"docstatus": 1, "status": "Open"}, pluck="name", limit=2)
		if len(open_orders) < 2:
			self.skipTest("Site has no two open Production Orders.")
		doc = frappe.get_doc(against.make_purchase_order(open_orders))
		against.validate_new_purchase_order_against(doc)
		self.assertEqual([row.production_order for row in doc.production_orders], open_orders)
		self.assertEqual(doc.production_orders[0].doctype, ROW_DOCTYPE)


class TestApprovalItemLimitWithoutProductionOrder(TestCase):
	def purchase_order(self, *rows, docstatus=0, production_order=None):
		items = [frappe._dict(idx=index, **row) for index, row in enumerate(rows, start=1)]
		return frappe._dict(docstatus=docstatus, production_orders=table(production_order) if production_order else [], items=items)

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

	def test_approval_rules_with_and_without_production_order(self):
		from essdee_yrp.purchase_order_approval import apply_draft_approval_status

		row = {"item_code": "YARN-1", "stock_qty": 900, "stock_uom": "Kg"}
		for production_order_name, over_limit in (("PPO-1", False), (None, True)):
			doc = self.purchase_order(row, production_order=production_order_name)
			doc.update(is_yrp_managed=1, status="Draft", name="PO-1", flags=frappe._dict())
			with (
				self.subTest(production_order=production_order_name),
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
		self.check(self.purchase_order(row, production_order="PPO-1"))
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
		doc.append("production_orders", {"production_order": "PPO-1", "item_name": "ITEM"})
		against.validate_approval_item_limit_without_production_order(doc)
