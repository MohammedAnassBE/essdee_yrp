from importlib import import_module
from importlib.util import find_spec
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp import hooks
from essdee_yrp.www.web import WEB_DOCTYPES, _apply_accurate_web_perms


class FakeProductionOrder:
	def __init__(self, **values):
		self.doctype = "YRP Production Order"
		self.name = values.pop("name", "PPO-0001")
		self.docstatus = values.pop("docstatus", 0)
		self.modified = values.pop("modified", "2026-10-09 10:30:00.000000")
		self._values = values
		self.checked_permissions = []
		self.meta = SimpleNamespace(fields=[], is_submittable=1)

	def get(self, key, default=None):
		if key == "name":
			return self.name
		if key == "docstatus":
			return self.docstatus
		if key == "modified":
			return self.modified
		return self._values.get(key, default)

	def check_permission(self, permission):
		self.checked_permissions.append(permission)

	def has_permission(self, permission):
		return frappe.has_permission(self.doctype, ptype=permission, doc=self)

	def run_method(self, method):
		if method != "onload":
			raise AssertionError(f"Unexpected method: {method}")


class FakeChildRow:
	"""Match a Frappe child Document: serializable, but not iterable."""

	def __init__(self, **values):
		self._values = values

	def as_dict(self):
		return dict(self._values)


class TestSalesWebWorkspace(TestCase):
	def setUp(self):
		# Permission tests allow printing unless the test explicitly disables a setting.
		settings = patch.object(frappe.db, "get_single_value", return_value=1)
		settings.start()
		self.addCleanup(settings.stop)

	def test_workspace_print_availability_respects_print_settings(self):
		workspace = self._workspace()
		for docstatus, setting_enabled, expected in ((2, 0, False), (2, 1, True), (0, 0, False), (0, 1, True), (1, 0, True)):
			with self.subTest(docstatus=docstatus, setting_enabled=setting_enabled):
				doc = FakeProductionOrder(docstatus=docstatus)
				with (
					patch.object(frappe, "get_doc", return_value=doc),
					patch.object(frappe, "has_permission", return_value=True),
					patch.object(frappe.db, "get_single_value", return_value=setting_enabled),
				):
					payload = workspace.get_production_order_workspace(doc.name)
				self.assertEqual(bool(payload["print_formats"]), expected)
				self.assertEqual(payload["permissions"]["can_print"], expected)
				self.assertEqual(payload["capabilities"]["print"]["allowed"], expected)

	def test_workspace_display_status_and_print_permissions_for_all_document_states(self):
		workspace = self._workspace()
		cases = ((0, None, "Draft"), (0, "PPO Request", "PPO Request"), (1, "Open", "Open"), (1, None, "Submitted"), (2, None, "Cancelled"), (2, "Open", "Cancelled"))
		for docstatus, stored_status, label in cases:
			for can_print in (True, False):
				with self.subTest(docstatus=docstatus, status=stored_status, can_print=can_print):
					doc = FakeProductionOrder(docstatus=docstatus, status=stored_status)
					with (
						patch.object(frappe, "get_doc", return_value=doc),
						patch.object(frappe, "has_permission", side_effect=lambda _doctype, ptype="read", **_kwargs: ptype != "print" or can_print),
					):
						payload = workspace.get_production_order_workspace(doc.name)
					self.assertEqual(payload["record"]["status_label"], label)
					self.assertEqual(payload["record"]["status"], stored_status)
					self.assertEqual(doc.get("status"), stored_status)
					self.assertEqual(payload["print_formats"], [{"label": "Production Order", "format": "Essdee Production Order"}] if can_print else [])

	def test_editor_and_save_reject_invalid_items_before_matrix_or_insert(self):
		from essdee_yrp.test_sales_production_order_commands import FakeEditableProductionOrder

		workspace = self._workspace()
		cases = (None, frappe._dict(has_variants=0), frappe._dict(has_variants=1, variant_of="Parent"), frappe._dict(has_variants=1, disabled=1))
		for item_values in cases:
			with self.subTest(item_values=item_values):
				doc = FakeEditableProductionOrder()
				with (
					patch.object(frappe, "new_doc", return_value=doc),
					patch.object(frappe, "has_permission", return_value=True),
					patch.object(frappe.db, "get_value", return_value=item_values),
					patch.object(workspace.workflow, "get_order_editor_context") as matrix,
				):
					with self.assertRaisesRegex(frappe.ValidationError, "Select a template Item"):
						workspace.get_production_order_editor(source={"item": "ZZ TEST Invalid"})
					with self.assertRaisesRegex(frappe.ValidationError, "Select a template Item"):
						workspace.save_production_order({"item": "ZZ TEST Invalid", "item_details": [{"item": "ZZ TEST Invalid", "entries": [{"qty": 1}]}]})
				matrix.assert_not_called()
				self.assertEqual(doc.inserted, 0)
				self.assertEqual(doc.saved, 0)

	def test_save_rejects_variant_in_matrix_even_with_valid_header_item(self):
		from essdee_yrp.test_sales_production_order_commands import FakeEditableProductionOrder

		workspace = self._workspace()
		doc = FakeEditableProductionOrder()
		with (
			patch.object(frappe, "new_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe.db, "get_value", side_effect=lambda _doctype, name, *_args, **_kwargs: frappe._dict(has_variants=name == "ZZ TEST Template", variant_of=None, disabled=0)),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "Select a template Item"):
				workspace.save_production_order({"item": "ZZ TEST Template", "item_details": [{"item": "ZZ TEST Variant", "entries": [{"qty": 1}]}]})
		self.assertEqual(doc.inserted, 0)

	def test_cancel_refreshes_display_status_without_changing_stored_status(self):
		from essdee_yrp.test_sales_production_order_commands import FakeEditableProductionOrder

		workspace = self._workspace()
		doc = FakeEditableProductionOrder(docstatus=1, status="Open")
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
		):
			payload = workspace.execute_production_order_command(doc.name, "cancel")
		self.assertEqual(payload["record"]["status_label"], "Cancelled")
		self.assertEqual(doc.get("status"), "Open")
		self.assertEqual({key for key, value in payload["capabilities"].items() if value["allowed"]}, {"amend", "print"})

	def _workspace(self):
		module = "essdee_yrp.sales.web_workspace"
		self.assertIsNotNone(find_spec(module), "The Sales web workspace must exist")
		return import_module(module)

	def _capabilities(self, allowed):
		workspace = self._workspace()
		with patch.object(
			frappe,
			"has_permission",
			side_effect=lambda doctype, ptype="read", **_kwargs: (doctype, ptype) in allowed,
		):
			return workspace.get_capabilities()

	def test_capabilities_expose_exactly_production_orders_and_reports(self):
		permissions = {
			("YRP Production Order", permission)
			for permission in ("read", "create", "write", "delete", "submit", "cancel", "print", "report")
		}
		payload = self._capabilities(permissions)
		self.assertEqual(set(payload), {"sections", "reports"})
		self.assertEqual(
			{key: value["label"] for key, value in payload["sections"].items()},
			{"production_orders": "Production Orders", "reports": "Reports"},
		)
		self.assertEqual(
			payload["reports"],
			{
				"ppo_report": {
					"label": "PPO Report",
					"can_read": True,
					"can_export": True,
				}
			},
		)

	def test_report_permission_is_independent_from_document_write_permissions(self):
		payload = self._capabilities({("YRP Production Order", "read"), ("YRP Production Order", "report")})
		self.assertEqual(set(payload["sections"]), {"production_orders", "reports"})
		self.assertFalse(payload["sections"]["production_orders"]["can_write"])
		self.assertTrue(payload["reports"]["ppo_report"]["can_read"])

		payload = self._capabilities({("YRP Production Order", "read")})
		self.assertEqual(set(payload["sections"]), {"production_orders"})
		self.assertEqual(payload["reports"], {})

	def test_finishing_dispatch_report_uses_its_own_read_permissions(self):
		payload = self._capabilities(
			{
				("YRP Production Order", "read"),
				("SD YRP Finishing Plan", "read"),
				("YRP Goods Received Note", "read"),
			}
		)
		self.assertEqual(set(payload["sections"]), {"production_orders", "reports"})
		self.assertEqual(
			payload["reports"],
			{
				"finishing_dispatch": {
					"label": "Finishing Plan Dispatch",
					"can_read": True,
					"can_export": False,
				}
			},
		)

		for missing in (("SD YRP Finishing Plan", "read"), ("YRP Goods Received Note", "read")):
			with self.subTest(missing=missing):
				allowed = {
					("YRP Production Order", "read"),
					("SD YRP Finishing Plan", "read"),
					("YRP Goods Received Note", "read"),
				} - {missing}
				payload = self._capabilities(allowed)
				self.assertNotIn("reports", payload["sections"])
				self.assertEqual(payload["reports"], {})

	def test_unreadable_production_orders_hide_both_sections(self):
		payload = self._capabilities({("YRP Production Order", "report")})
		self.assertEqual(payload, {"sections": {}, "reports": {}})

	def test_workspace_projects_compact_data_matrices_and_histories(self):
		workspace = self._workspace()
		doc = FakeProductionOrder(
			docstatus=1,
			status="Open",
			item="Premium Polo",
			production_detail="IPD-0001",
			production_term="Default Term",
			posting_date="2026-10-09",
			delivery_date="2026-10-20",
			dont_deliver_after="2026-10-25",
			lead_time_given=11,
			comments="Priority order",
			price_approval_status="Approved",
			production_order_details=[
				frappe._dict(item="Premium Polo", item_variant="POLO-NAVY-S", size="S", quantity=40, ratio=1, mrp=799, retail_price=699, wholesale_price=520, production_order_mrp=760),
				frappe._dict(item="Premium Polo", item_variant="POLO-NAVY-M", size="M", quantity=80, ratio=2, mrp=799, retail_price=699, wholesale_price=520, production_order_mrp=760),
			],
			production_ordered_details=[
				frappe._dict(item="Premium Polo", item_variant="POLO-NAVY-S", size="S", lot="LOT-1", quantity=10),
			],
			date_change_history=[FakeChildRow(date_field="Delivery Date", old_date="2026-10-18", new_date="2026-10-20", reason="Buyer request")],
			quantity_transfer_history=[FakeChildRow(
				approved_on="2026-10-09 14:35:00.000000",
				movement="Added",
				counterpart_production_order="PPO-OLD",
				size="S",
				quantity=12,
				quantity_before=28,
				quantity_after=40,
				transfer_reference="PPO-TRANSFER-0001",
				requested_by="sales@example.com",
				requested_on="2026-10-09 14:00:00.000000",
				approved_by="manager@example.com",
				reason="Balance the size run",
			)],
			comment_log="Created by Sales",
			__onload={
				"can_manage_production_order": True,
				"linked_lots": ["LOT-1"],
				"price_requests": [{"name": "PRICE-1", "status": "Approved"}],
			},
		)
		allowed = {
			("YRP Production Order", permission)
			for permission in ("read", "write", "cancel", "print")
		}
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", side_effect=lambda doctype, ptype="read", **_kwargs: (doctype, ptype) in allowed),
		):
			payload = workspace.get_production_order_workspace(doc.name)

		self.assertEqual(doc.checked_permissions, ["read"])
		self.assertEqual(payload["record"]["name"], "PPO-0001")
		self.assertEqual(payload["record"]["total_quantity"], 120)
		self.assertEqual(payload["matrix"][0]["prices"], {"mrp": 799, "retail_price": 699, "wholesale_price": 520, "production_order_mrp": 760})
		self.assertEqual(payload["ordered"][0]["lot"], "LOT-1")
		self.assertEqual(payload["ordered"][0]["size"], "S")
		self.assertEqual(payload["linked_lots"], ["LOT-1"])
		self.assertEqual(set(payload["histories"]), {"dates", "transfers", "prices", "comments"})
		self.assertEqual(payload["histories"]["dates"][0]["reason"], "Buyer request")
		self.assertEqual(payload["histories"]["transfers"], [{
			"approved_on": "2026-10-09 14:35:00.000000",
			"movement": "Added",
			"counterpart_production_order": "PPO-OLD",
			"size": "S",
			"quantity": 12,
			"quantity_before": 28,
			"quantity_after": 40,
			"transfer_reference": "PPO-TRANSFER-0001",
			"requested_by": "sales@example.com",
			"requested_on": "2026-10-09 14:00:00.000000",
			"approved_by": "manager@example.com",
			"reason": "Balance the size run",
		}])
		self.assertFalse(payload["capabilities"]["update_quantity_ratio"]["allowed"])
		self.assertTrue(payload["capabilities"]["update_quantity_ratio"]["reason"])
		self.assertTrue(payload["capabilities"]["update_price"]["allowed"])

	def test_workspace_resolves_size_for_migrated_rows_without_attribute_json(self):
		workspace = self._workspace()
		doc = FakeProductionOrder(
			docstatus=1,
			status="Open",
			production_order_details=[frappe._dict(item="Premium Polo", item_variant="POLO-M", attributes_json=None, quantity=40)],
			production_ordered_details=[],
			__onload={"can_manage_production_order": False, "linked_lots": []},
		)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(workspace, "get_variant_attr_details", return_value={"Size": "M"}),
		):
			payload = workspace.get_production_order_workspace(doc.name)

		self.assertEqual(payload["matrix"][0]["size"], "M")

	def test_workspace_resolves_size_for_ordered_lot_rows(self):
		workspace = self._workspace()
		doc = FakeProductionOrder(
			docstatus=1,
			status="Open",
			production_order_details=[],
			production_ordered_details=[
				frappe._dict(item="Premium Polo", item_variant="POLO-M", lot="LOT-1", quantity=12),
			],
			__onload={"can_manage_production_order": False, "linked_lots": ["LOT-1"]},
		)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(workspace, "get_variant_attr_details", return_value={"Size": "M"}),
		):
			payload = workspace.get_production_order_workspace(doc.name)

		self.assertEqual(payload["ordered"], [{
			"name": None,
			"item": "Premium Polo",
			"item_variant": "POLO-M",
			"size": "M",
			"lot": "LOT-1",
			"quantity": 12,
		}])

	def test_lot_ocr_details_require_a_readable_lot_linked_to_the_production_order(self):
		workspace = self._workspace()
		self.assertTrue(hasattr(workspace, "get_lot_ocr_details"), "Sales must expose a permission-safe Lot OCR endpoint")
		production_order = FakeProductionOrder(name="PPO-0001", item="Premium Polo")
		lot = frappe._dict(name="LOT-1", production_order="PPO-0001", item="Premium Polo")
		lot.checked_permissions = []
		lot.check_permission = lot.checked_permissions.append
		ocr = {
			"sizes": ["S"],
			"processes": {"Cutting": {"wo_list": ["WO-1"], "cp_list": ["CP-1"], "data": {"S": {"sent": 10, "received": 9}}, "total_sent": 10, "total_received": 9}},
			"dispatch_detail": {"S": 8},
			"total_dispatch": 8,
			"finishing_plan_list": ["FP-1"],
		}

		def get_doc(doctype, name):
			return production_order if doctype == "YRP Production Order" else lot

		with (
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(workspace, "build_lot_ocr_details", return_value=ocr) as build_ocr,
		):
			payload = workspace.get_lot_ocr_details("PPO-0001", "LOT-1")

		self.assertEqual(production_order.checked_permissions, ["read"])
		self.assertEqual(lot.checked_permissions, ["read"])
		build_ocr.assert_called_once_with("LOT-1")
		self.assertEqual(payload["context"], {"lot": "LOT-1", "production_order": "PPO-0001", "item": "Premium Polo"})
		self.assertEqual(payload["processes"], ocr["processes"])

		lot.production_order = "PPO-OTHER"
		with patch.object(frappe, "get_doc", side_effect=get_doc):
			with self.assertRaises(frappe.PermissionError):
				workspace.get_lot_ocr_details("PPO-0001", "LOT-1")

	def test_lot_ocr_details_reject_an_unreadable_production_order_or_lot(self):
		workspace = self._workspace()
		production_order = FakeProductionOrder(name="PPO-0001", item="Premium Polo")
		lot = frappe._dict(name="LOT-1", production_order="PPO-0001", item="Premium Polo")
		lot.check_permission = Mock()

		def get_doc(doctype, _name):
			return production_order if doctype == "YRP Production Order" else lot

		with (
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(workspace, "build_lot_ocr_details") as build_ocr,
		):
			production_order.check_permission = Mock(side_effect=frappe.PermissionError)
			with self.assertRaises(frappe.PermissionError):
				workspace.get_lot_ocr_details("PPO-0001", "LOT-1")
			build_ocr.assert_not_called()

			production_order.check_permission = Mock()
			lot.check_permission = Mock(side_effect=frappe.PermissionError)
			with self.assertRaises(frappe.PermissionError):
				workspace.get_lot_ocr_details("PPO-0001", "LOT-1")
			build_ocr.assert_not_called()

	def test_read_only_user_gets_data_but_no_mutating_actions(self):
		workspace = self._workspace()
		doc = FakeProductionOrder(
			docstatus=1,
			status="Open",
			production_order_details=[],
			production_ordered_details=[],
			__onload={"can_manage_production_order": False, "linked_lots": []},
		)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", side_effect=lambda _doctype, ptype="read", **_kwargs: ptype in {"read", "print"}),
		):
			payload = workspace.get_production_order_workspace(doc.name)
		self.assertTrue(payload["capabilities"]["print"]["allowed"])
		self.assertFalse(any(
			capability["allowed"]
			for key, capability in payload["capabilities"].items()
			if key != "print"
		))

	def test_pending_request_exposes_only_matching_approval(self):
		workspace = self._workspace()
		cases = (
			("quantity_ratio", "approve_quantity_ratio"),
			("status", "approve_status"),
		)
		for request_type, expected in cases:
			with self.subTest(request_type=request_type):
				doc = FakeProductionOrder(
					docstatus=1,
					status="Pending Request",
					production_order_details=[],
					production_ordered_details=[],
					__onload={
						"can_manage_production_order": True,
						"can_approve_production_order_request": True,
						"pending_production_order_request": {"request_type": request_type},
						"linked_lots": [],
					},
				)
				with (
					patch.object(frappe, "get_doc", return_value=doc),
					patch.object(frappe, "has_permission", return_value=True),
				):
					payload = workspace.get_production_order_workspace(doc.name)
				self.assertTrue(payload["capabilities"][expected]["allowed"])
				other = "approve_status" if expected == "approve_quantity_ratio" else "approve_quantity_ratio"
				self.assertFalse(payload["capabilities"][other]["allowed"])

	def test_production_order_is_registered_in_both_web_catalogs(self):
		for catalog in (WEB_DOCTYPES, hooks.yrp_web_doctype_catalog):
			self.assertIn("YRP Production Order", catalog)

	def test_web_boot_corrects_production_order_permissions(self):
		user = {f"can_{ptype}": ["YRP Production Order"] for ptype in ("read", "create", "write", "delete", "submit", "cancel")}
		with patch.object(frappe, "has_permission", return_value=False):
			_apply_accurate_web_perms(user)
		for allowed in user.values():
			self.assertNotIn("YRP Production Order", allowed)

	def test_sales_endpoints_are_authenticated(self):
		workspace = self._workspace()
		for endpoint in (workspace.get_capabilities, workspace.get_production_order_workspace, workspace.get_lot_ocr_details):
			with self.subTest(endpoint=endpoint.__name__):
				self.assertIn(endpoint, frappe.whitelisted)
				self.assertNotIn(endpoint, frappe.guest_methods)
				original_user = frappe.session.user
				try:
					frappe.set_user("Guest")
					with self.assertRaises(frappe.PermissionError):
						frappe.is_whitelisted(endpoint)
					frappe.set_user("Administrator")
					frappe.is_whitelisted(endpoint)
				finally:
					frappe.set_user(original_user)


class TestSalesProductionOrderLiveQueries(TestCase):
	def test_every_existing_production_order_item_is_found_first(self):
		from essdee_yrp.api.link_search import link_search

		items = set(frappe.get_all("YRP Production Order", pluck="item", limit_page_length=0)) - {None, ""}
		self.assertTrue(items)
		filters = {"has_variants": 1, "variant_of": ["is", "not set"], "disabled": 0}
		for item in sorted(items):
			with self.subTest(item=item):
				results = link_search("Item", item, filters)
				self.assertTrue(results)
				self.assertEqual(results[0]["name"].casefold(), item.casefold())
				self.assertEqual(link_search("Item", item.swapcase(), filters)[0]["name"].casefold(), item.casefold())

	def test_status_queries_partition_real_documents_without_changing_status(self):
		from essdee_yrp.sales.web_workspace import get_production_order_status

		rows = frappe.get_all("YRP Production Order", fields=["name", "docstatus", "status"], limit_page_length=0)
		self.assertTrue(rows)
		statuses = ("Draft", "PPO Request", "Open", "Pending Request", "Item Changed", "Not Processed", "Closed", "Cancelled")
		seen = set()
		for status in statuses:
			if status == "Cancelled":
				filters = [["docstatus", "=", 2]]
			else:
				filters = [["docstatus", "=", 0 if status in {"Draft", "PPO Request"} else 1]]
				filters.append(["status", "in", ["Draft", ""]] if status == "Draft" else ["status", "=", status])
			actual = set(frappe.get_list("YRP Production Order", filters=filters, pluck="name", limit_page_length=0))
			expected = {row.name for row in rows if get_production_order_status(row) == status}
			with self.subTest(status=status):
				self.assertEqual(actual, expected)
				self.assertFalse(seen & actual)
			seen.update(actual)
		self.assertEqual(seen, {row.name for row in rows})
