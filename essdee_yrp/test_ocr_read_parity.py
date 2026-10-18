from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot import sd_yrp_lot as lot


class TestOcrReadParity(TestCase):
	def setUp(self):
		self.denied = set()
		self.docs = {}
		self.wo_names = ["WO-1", "WO-hidden"]
		self.cp_names = {"WO-1": ["CP-1", "CP-hidden"], "WO-hidden": ["CP-2"]}
		self.grn_names = ["GRN-1", "GRN-hidden", "GRN-missing", "GRN-external"]
		self.fp_names = ["FP-1", "FP-hidden"]
		self.add_doc("SD YRP Lot", "LOT", check_permission=Mock(), production_order="PPO", item="Item", production_detail="IPD")
		self.add_doc("YRP Production Order", "PPO", check_permission=Mock())
		for name, process in [("WO-1", "Pack"), ("WO-hidden", "Hidden pack"), ("WO-external", "Hidden pack")]:
			self.add_doc("YRP Work Order", name, process_name=process, includes_packing=1,
				work_order_calculated_items=[frappe._dict(item_variant="S", delivered_quantity=2.5, received_qty=1)])
		for names in self.cp_names.values():
			for name in names:self.add_doc("SD YRP Cutting Plan", name)
		for name, source, version in [("GRN-1", "WO-1", 2), ("GRN-hidden", "WO-hidden", 0), ("GRN-missing", "missing", 2), ("GRN-external", "WO-external", 2)]:
			self.add_doc("YRP Goods Received Note", name, against_id=source, packing_calculation_version=version,
				items=[frappe._dict(item_variant="S", quantity=0.5)])
		for name, variant in [("FP-1", "S"), ("FP-hidden", "private-size")]:
			self.add_doc("SD YRP Finishing Plan", name, work_order="WO-1", pieces_per_box=3,
				finishing_plan_grn_details=[frappe._dict(item_variant=variant, dispatched=0.25)])
		self.stack = ExitStack();self.addCleanup(self.stack.close)
		for target, name, value in [
			(frappe, "get_doc", self.get_doc), (frappe, "get_lazy_doc", self.get_doc),
			(frappe, "get_all", self.get_all),
			(frappe, "get_value", self.get_value), (frappe, "has_permission", self.can_read),
			(frappe, "get_meta", lambda *a: frappe._dict(has_field=lambda f: True)),
			(lot, "get_variant_attr_details", lambda variant: {"Size": variant}),
			(frappe.db, "exists", lambda *a, **kw: True),
		]:self.stack.enter_context(patch.object(target, name, side_effect=value))
		self.stack.enter_context(patch.object(frappe, "session", frappe._dict(user="reader")))

	def add_doc(self, doctype, name, **fields):
		self.docs[doctype, name] = SimpleNamespace(doctype=doctype, name=name, **fields)
		self.docs[doctype, name].get = lambda key, default=None: getattr(self.docs[doctype, name], key, default)

	def get_doc(self, doctype, name):
		if (doctype, name) not in self.docs:raise frappe.DoesNotExistError(name)
		return self.docs[doctype, name]

	def get_all(self, doctype, **kwargs):
		if doctype == "YRP Work Order":return self.wo_names
		if doctype == "SD YRP Cutting Plan":return self.cp_names[kwargs["filters"]["work_order"]]
		if doctype == "YRP Goods Received Note":
			self.last_grn_filters = kwargs["filters"]
			return self.grn_names
		if doctype == "SD YRP Finishing Plan":return self.fp_names
		raise AssertionError(doctype)

	def get_value(self, doctype, *args):
		return ("IPD", "Item") if doctype == "SD YRP Lot" else ("Sew", "Size", 6)

	def can_read(self, doctype, ptype="read", doc=None, **kwargs):
		return doctype not in self.denied and (doctype, doc.name if doc else None) not in self.denied

	def test_hidden_records_and_packing_sources_never_contribute(self):
		self.denied = {("YRP Work Order", "WO-hidden"), ("YRP Work Order", "WO-external"), ("SD YRP Cutting Plan", "CP-hidden"), ("SD YRP Finishing Plan", "FP-hidden")}
		result = lot.get_ocr_details("LOT")
		self.assertEqual(list(result["processes"]), ["Pack"])
		self.assertEqual(result["processes"]["Pack"]["cp_list"], ["CP-1"])
		self.assertEqual(result["processes"]["Pack"]["total_received"], 0)
		self.assertEqual(self.last_grn_filters["process_name"], "Hidden pack")
		self.assertEqual(result["sizes"], ["S"])
		self.assertEqual(result["finishing_plan_list"], ["FP-1"])
		self.assertEqual(result["total_dispatch"], 0.25)

	def test_denied_doctypes_hide_all_rows(self):
		self.denied = {"YRP Work Order", "SD YRP Cutting Plan", "SD YRP Finishing Plan"}
		self.assertEqual(lot.get_ocr_details("LOT"), {"sizes": [], "processes": {}, "dispatch_detail": {}, "total_dispatch": 0, "finishing_plan_list": []})

	def test_administrator_retains_legacy_receipts_and_arithmetic(self):
		frappe.session.user = "Administrator"
		result = lot.get_ocr_details("LOT")
		self.assertEqual(result["processes"]["Hidden pack"]["total_received"], 4.5)
		self.assertEqual(result["finishing_plan_list"], self.fp_names)
		self.assertEqual(result["total_dispatch"], 0.5)

	def test_fully_readable_reader_matches_admin_and_legacy_dispatch(self):
		self.grn_names = ["GRN-1", "GRN-hidden", "GRN-external"]
		with patch.object(frappe.db, "exists", return_value=False):
			reader = lot.get_ocr_details("LOT")
			frappe.session.user = "Administrator"
			self.assertEqual(lot.get_ocr_details("LOT"), reader)
		self.assertEqual(reader["total_dispatch"], 1.5)

	def test_lot_denial_precedes_child_reads(self):
		self.docs["SD YRP Lot", "LOT"].check_permission.side_effect = frappe.PermissionError
		with self.assertRaises(frappe.PermissionError):lot.get_ocr_details("LOT")

	def test_all_three_entry_points_use_record_checks(self):
		from essdee_yrp.purchase.lot_workspace import get_ocr
		from essdee_yrp.sales.web_workspace import get_lot_ocr_details

		self.denied = {"YRP Work Order", "SD YRP Cutting Plan", "SD YRP Finishing Plan"}
		self.assertEqual(lot.get_ocr_details("LOT")["processes"], {})
		self.assertIsNone(get_ocr(self.docs["SD YRP Lot", "LOT"]))
		self.assertEqual(get_lot_ocr_details("PPO", "LOT")["processes"], {})

	def test_blank_receipt_source_cannot_resolve_an_unfiltered_work_order(self):
		self.wo_names = ["WO-1"]
		self.fp_names = []
		self.grn_names = ["GRN-1"]
		self.docs["YRP Goods Received Note", "GRN-1"].against_id = None
		# Frappe's None filter can read the first record; never call it for a blank Link.
		self.docs["YRP Work Order", None] = self.docs["YRP Work Order", "WO-1"]
		result = lot.get_ocr_details("LOT")
		self.assertEqual(result["processes"]["Pack"]["total_received"], 0)

	def test_hidden_packing_process_does_not_resolve_receipt_attributes(self):
		self.denied = {("YRP Work Order", "WO-hidden")}
		self.grn_names = ["GRN-external"]
		self.docs["YRP Goods Received Note", "GRN-external"].items[0].item_variant = "broken"
		with patch.object(lot, "get_variant_attr_details", side_effect=lambda v: {"Size": v} if v != "broken" else (_ for _ in ()).throw(KeyError(v))):
			self.assertEqual(lot.get_ocr_details("LOT")["processes"]["Pack"]["total_received"], 0)
