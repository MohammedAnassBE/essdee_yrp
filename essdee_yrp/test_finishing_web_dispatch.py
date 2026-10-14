import copy
from importlib import import_module
from importlib.util import find_spec
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

MODULE = "essdee_yrp.finishing.web_dispatch"
SERVICE = "essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch.sd_yrp_finishing_plan_dispatch"

FRESH = [
	{
		"lot": "LOT-1",
		"item": "TSHIRT",
		"doc_name": "FP-1",
		"uom": "Box",
		"values": {
			"S": {"qty": 4, "row_detail": "grn-row-1", "dispatch_qty": 0},
			"M": {"qty": 2, "row_detail": "grn-row-2", "dispatch_qty": 0},
		},
		"total": {"total_qty": 6, "total_dispatch": 0},
		"primary_attribute": "Size",
		"packing_config": {},
		"dynamic_ratio_packing": False,
		"packing_batches": [],
		"batch_dispatches": [],
	},
	{
		"lot": "LOT-2",
		"item": "POLO",
		"doc_name": "FP-2",
		"uom": "Nos",
		"values": {"S": {"qty": 10, "row_detail": "grn-row-3", "dispatch_qty": 0}},
		"total": {"total_qty": 10, "total_dispatch": 0},
		"primary_attribute": "Size",
		"packing_config": {},
		"dynamic_ratio_packing": True,
		"packing_batches": [{"batch_row": "B1", "available_boxes": 3}],
		"batch_dispatches": [],
	},
]


class FakeDispatch(frappe._dict):
	doctype = "SD YRP Finishing Plan Dispatch"

	def check_permission(self, ptype="read"):
		if ptype in self.get("denied", ()):
			raise frappe.PermissionError(ptype)

	def is_new(self):
		return False


def dispatch(**values):
	defaults = {
		"name": "FPD-2627-00001",
		"docstatus": 0,
		"modified": "2026-10-09 10:00:00",
		"stock_entry": None,
	}
	defaults.update(values)
	doc = FakeDispatch(defaults)
	doc.save = MagicMock()
	doc.submit = MagicMock()
	doc.cancel = MagicMock()
	doc.insert = MagicMock()
	return doc


class TestFinishingWebDispatch(TestCase):
	def _dispatch(self):
		self.assertIsNotNone(find_spec(MODULE), "Finishing Plan Dispatch web endpoints must exist")
		return import_module(MODULE)

	def _fresh(self):
		return patch(f"{SERVICE}.fetch_fp_items", side_effect=lambda: copy.deepcopy(FRESH))

	def test_endpoints_are_whitelisted_for_authenticated_users(self):
		module = self._dispatch()
		for name in (
			"get_dispatch_workspace",
			"fetch_dispatch_items",
			"save_dispatch",
			"execute_dispatch_command",
		):
			with self.subTest(endpoint=name):
				self.assertIn(getattr(module, name), frappe.whitelisted)
				self.assertNotIn(getattr(module, name), frappe.guest_methods)

	def test_rows_are_rebuilt_from_server_balances(self):
		module = self._dispatch()
		posted = copy.deepcopy(FRESH)
		posted[0]["values"]["S"]["qty"] = 999
		posted[0]["values"]["S"]["row_detail"] = "forged"
		posted[0]["values"]["S"]["dispatch_qty"] = 3
		posted[0]["colour_grid"] = {"Red": {"S": 3}}
		posted[1]["batch_dispatches"] = [{"batch_row": "B1", "box_quantity": 2}]
		with self._fresh():
			rows = module.authoritative_items(posted)
		self.assertEqual(rows[0]["values"]["S"], {"qty": 4, "row_detail": "grn-row-1", "dispatch_qty": 3})
		self.assertEqual(rows[0]["values"]["M"]["dispatch_qty"], 0)
		self.assertEqual(rows[0]["colour_grid"], {"Red": {"S": 3}})
		self.assertEqual(rows[1]["batch_dispatches"], [{"batch_row": "B1", "box_quantity": 2}])

	def test_rows_without_requests_are_dropped(self):
		module = self._dispatch()
		with self._fresh():
			self.assertEqual(module.authoritative_items(copy.deepcopy(FRESH)), [])

	def test_invalid_rows_are_rejected(self):
		module = self._dispatch()
		cases = []
		unknown_plan = copy.deepcopy(FRESH[:1])
		unknown_plan[0]["doc_name"] = "FP-GONE"
		unknown_plan[0]["values"]["S"]["dispatch_qty"] = 1
		cases.append(unknown_plan)
		negative = copy.deepcopy(FRESH[:1])
		negative[0]["values"]["S"]["dispatch_qty"] = -1
		cases.append(negative)
		unknown_size = copy.deepcopy(FRESH[:1])
		unknown_size[0]["values"]["XXL"] = {"dispatch_qty": 1}
		cases.append(unknown_size)
		unknown_batch = copy.deepcopy(FRESH[1:])
		unknown_batch[0]["batch_dispatches"] = [{"batch_row": "B9", "box_quantity": 1}]
		cases.append(unknown_batch)
		for posted in cases:
			with (
				self.subTest(posted=posted[0]["doc_name"]),
				self._fresh(),
				self.assertRaises(frappe.ValidationError),
			):
				module.authoritative_items(posted)

	def test_save_existing_draft_checks_freshness_and_submits_on_request(self):
		module = self._dispatch()
		doc = dispatch()
		posted = copy.deepcopy(FRESH[:1])
		posted[0]["values"]["S"]["dispatch_qty"] = 1
		with (
			self._fresh(),
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(module, "get_dispatch_workspace", return_value={"record": {"name": doc.name}}),
		):
			with self.assertRaises(frappe.TimestampMismatchError):
				module.save_dispatch(posted, doc.name, 0, "2020-01-01 00:00:00")
			module.save_dispatch(posted, doc.name, 1, doc.modified)
		self.assertEqual(frappe.parse_json(doc.finishing_items)[0]["values"]["S"]["dispatch_qty"], 1)
		doc.save.assert_called_once()
		doc.submit.assert_called_once()

	def test_submitted_dispatch_cannot_be_saved(self):
		module = self._dispatch()
		with (
			patch.object(frappe, "get_doc", return_value=dispatch(docstatus=1)),
			self.assertRaises(frappe.ValidationError),
		):
			module.save_dispatch([], "FPD-2627-00001", 0, "2026-10-09 10:00:00")

	def test_dispatch_stock_requires_submitted_dispatch_without_stock_entry(self):
		module = self._dispatch()
		values = {
			"from_supplier": "S-FROM",
			"from_warehouse": "WH-FROM",
			"to_supplier": "S-TO",
			"to_warehouse": "WH-TO",
			"goods_value": 100,
			"vehicle_no": "TN01",
		}
		for doc in (dispatch(docstatus=0), dispatch(docstatus=1, stock_entry="STE-1")):
			with (
				self.subTest(docstatus=doc.docstatus),
				patch.object(frappe, "get_doc", return_value=doc),
				patch.object(frappe, "has_permission", return_value=True),
				patch.object(frappe.db, "get_value", return_value=1),
				self.assertRaises(frappe.ValidationError),
			):
				module.execute_dispatch_command(doc.name, "dispatch_stock", values, doc.modified)
		doc = dispatch(docstatus=1)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch(f"{SERVICE}.create_stock_dispatch", return_value="STE-9") as create,
			patch.object(module, "get_dispatch_workspace", return_value={"record": {"name": doc.name}}),
		):
			result = module.execute_dispatch_command(doc.name, "dispatch_stock", values, doc.modified)
		create.assert_called_once_with(doc_name=doc.name, **values)
		self.assertEqual(result["result"], {"doctype": "YRP Stock Entry", "name": "STE-9"})

	def test_dispatch_stock_requires_frappe_15_fields(self):
		module = self._dispatch()
		with (
			patch.object(frappe, "get_doc", return_value=dispatch(docstatus=1)),
			patch.object(frappe, "has_permission", return_value=True),
			self.assertRaises(frappe.ValidationError),
		):
			module.execute_dispatch_command(
				"FPD-2627-00001",
				"dispatch_stock",
				{"from_supplier": "S-FROM", "from_warehouse": "WH-FROM"},
				"2026-10-09 10:00:00",
			)

	def test_cancel_requires_a_submitted_dispatch_and_cancel_permission(self):
		module = self._dispatch()
		with (
			patch.object(frappe, "get_doc", return_value=dispatch(docstatus=1)),
			patch.object(
				frappe,
				"has_permission",
				side_effect=lambda doctype, ptype="read", *args, **kwargs: ptype != "cancel",
			),
			self.assertRaises(frappe.ValidationError),
		):
			module.execute_dispatch_command("FPD-2627-00001", "cancel", {}, "2026-10-09 10:00:00")
		doc = dispatch(docstatus=1)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(module, "get_dispatch_workspace", return_value={"record": {"name": doc.name}}),
		):
			module.execute_dispatch_command(doc.name, "cancel", {}, doc.modified)
		doc.cancel.assert_called_once()
