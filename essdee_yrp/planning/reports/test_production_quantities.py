from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning.reports import colour_wise_diff, size_wise_stock, work_in_progress
from essdee_yrp.planning.reports import production_quantities as quantities


class TestProductionQuantities(TestCase):
	def test_confirmed_stage_uses_in_stage_only(self):
		detail = {"stiching_in_stage": "Panels", "stiching_out_stage": "Pieces"}
		self.assertEqual(quantities.process_comparison({"in_stage": "Panels", "out_stage": "Pieces"}, detail), "cut")
		self.assertEqual(quantities.process_comparison({"in_stage": "Pieces", "out_stage": "Panels"}, detail), "piece")
		self.assertEqual(quantities.process_comparison({"in_stage": "Other"}, detail), "piece")

	def test_missing_stages_compare_against_cut_like_legacy(self):
		self.assertEqual(quantities.process_comparison({}, {}), "cut")
		self.assertEqual(quantities.process_comparison({"in_stage": None}, {"stiching_in_stage": None}), "cut")

	def test_category_membership_preserves_item_row_permissions_without_field_access(self):
		for field in ("category", "product_category"):
			def read(doctype, **kwargs):
				if doctype == "Item":
					self.assertEqual(kwargs["filters"], {"name": ["in", ["Visible", "Hidden"]]})
					return ["Visible"]
				self.assertEqual(kwargs["filters"]["item"], ["in", ["Visible"]])
				return []
			with self.subTest(field=field), patch.object(quantities, "authorize_filter_values", side_effect=lambda doctype, values: values or []), patch.object(frappe, "get_all", return_value=["Visible", "Hidden"]) as membership, patch.object(frappe, "get_list", side_effect=read):
				quantities.production_lots({field: "MMA Vest"}, field)
				membership.assert_called_once_with("Item", filters={"product_category": "MMA Vest"}, pluck="name", limit_page_length=0)

	def test_all_multi_values_are_authorized_in_order(self):
		with patch.object(frappe, "get_list", return_value=["B", "A"]):
			self.assertEqual(quantities.authorize_filter_values("YRP Process", '["A","B","A"]'), ["A", "B"])
		with patch.object(frappe, "get_list", return_value=["A"]):
			with self.assertRaises(frappe.PermissionError):
				quantities.authorize_filter_values("YRP Process", ["A", "Hidden"])
		for value in ('{"name":"A"}', [1], "1"):
			with self.assertRaises(frappe.ValidationError):
				quantities.authorize_filter_values("YRP Process", value)

	def test_required_filter_status_and_paired_dates(self):
		for filters in ({}, {"item": ["I"], "lot_status": "Invalid"}, {"item": ["I"], "from_date": "2026-10-01"}, {"item": ["I"], "from_date": "2026-10-15", "to_date": "2026-10-01"}):
			with patch.object(quantities, "authorize_filter_values", side_effect=lambda doctype, values: values or []):
				with self.assertRaises(frappe.ValidationError):
					quantities.production_lots(filters)

	def test_lot_creation_includes_entire_end_date(self):
		with patch.object(quantities, "authorize_filter_values", side_effect=lambda doctype, values: values or []), patch.object(frappe, "get_list", return_value=[]) as read:
			quantities.production_lots({"lot": ["L"], "from_date": "2026-10-01", "to_date": "2026-10-15"})
			conditions = read.call_args.kwargs["filters"]
			self.assertIn(["SD YRP Lot", "creation", ">=", "2026-10-01"], conditions)
			self.assertIn(["SD YRP Lot", "creation", "<", "2026-10-16"], conditions)

	def test_children_scoped_to_permitted_parents(self):
		with patch.object(frappe, "get_all", return_value=[]) as read:
			quantities.child_rows("SD YRP Lot Order Detail", ["L"], ["quantity"], "SD YRP Lot")
			self.assertEqual(read.call_args.kwargs["filters"], {"parent": ["in", ["L"]], "parenttype": "SD YRP Lot"})
			read.reset_mock()
			self.assertEqual(quantities.child_rows("Child", [], [], "Parent"), [])
			read.assert_not_called()

	def test_size_order_resolves_attribute_values(self):
		details = {"D": {"primary_item_attribute": "Size"}}
		with patch.object(quantities, "child_rows", side_effect=[[{"parent": "D", "attribute": "Size", "mapping": "Map"}], [{"parent": "Map", "idx": 2, "attribute_value": "IAV-S"}, {"parent": "Map", "idx": 1, "attribute_value": "IAV-M"}]]), patch.object(quantities, "actual_values", return_value={"IAV-M": "M", "IAV-S": "S"}):
			self.assertEqual(quantities.production_size_orders(details), {"D": ["M", "S"]})

	def test_reports_reject_every_hidden_json_filter_before_child_reads(self):
		for module, fields in ((colour_wise_diff, ("process_list",)), (size_wise_stock, ("lot", "item", "process_list")), (work_in_progress, ("lot", "item", "process_list"))):
			for field in fields:
				filters = {field: '["Hidden"]'}
				if module is colour_wise_diff:
					filters["lot"] = "Readable"
				def read(doctype, **kwargs):
					return ["Readable"] if doctype == "SD YRP Lot" and module is colour_wise_diff else []
				with self.subTest(module=module.__name__, field=field), patch.object(module, "require_access"), patch.object(frappe, "get_list", side_effect=read), patch.object(frappe, "get_all") as children:
					with self.assertRaises(frappe.PermissionError):
						module.run(filters)
					children.assert_not_called()

	def test_set_part_multiplier_and_finishing_parent_scope(self):
		details = {"D": {"is_set_item": 1, "set_item_attribute": "Part"}}
		def children(doctype, parents, fields, parenttype):
			if doctype == "YRP IPD Item Attribute":
				return [{"parent": "D", "attribute": "Part", "mapping": "Parts"}]
			if doctype == "YRP Item Item Attribute Mapping Value":
				return [{"parent": "Parts", "attribute_value": value} for value in ("Top", "Bottom")]
			self.assertEqual(set(parents), {"VisiblePlan"})
			return []
		with patch.object(frappe, "get_list", return_value=[{"name": "VisiblePlan", "lot": "L", "pieces_per_box": 5}]) as read, patch.object(quantities, "child_rows", side_effect=children):
			result = quantities.finishing_context([{"name": "L"}], details)
		self.assertEqual(read.call_args.args[0], "SD YRP Finishing Plan")
		self.assertEqual(read.call_args.kwargs["filters"], {"lot": ["in", ["L"]]})
		self.assertEqual(result["parts"], {"D": 2})

	def test_production_context_requires_readable_ipd_before_children(self):
		with patch.object(frappe, "get_list", return_value=[]), patch.object(frappe, "get_all") as children:
			with self.assertRaises(frappe.PermissionError):
				quantities.production_context([{"name": "L", "production_detail": "Hidden"}], [])
			children.assert_not_called()
