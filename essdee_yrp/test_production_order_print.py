import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict

from essdee_yrp import production_order_workflow as workflow


class TestProductionOrderPrint(TestCase):
	def get_details(self, form=None, fg_pieces_per_box=None, **kwargs):
		doc = _dict(production_order_details=[], item="FG-ITEM")
		doc.check_permission = MagicMock()
		quantities = {
			"S": {"qty": 10, "ratio": 1, "mrp": 100},
			"M": {"qty": 20, "ratio": 2, "mrp": 120},
		}
		with (
			patch.object(frappe, "get_doc", return_value=doc) as get_doc,
			patch.object(frappe, "form_dict", _dict(form or {})),
			patch.object(workflow, "get_order_qty", return_value=quantities),
			patch.object(workflow, "get_fg_pieces_per_box", return_value={"pieces_per_box": fg_pieces_per_box}),
		):
			result = workflow.get_production_order_details("PPO-TEST", **kwargs)
		get_doc.assert_called_once_with("YRP Production Order", "PPO-TEST")
		doc.check_permission.assert_called_once_with("read")
		return result

	def test_details_without_pieces_per_box_keep_box_quantities(self):
		result = self.get_details()
		self.assertEqual(result["S"], {"qty": 10, "ratio": 1, "mrp": 100})
		self.assertNotIn("piece_qty", result["M"])

	def test_details_fall_back_to_fg_item_pieces_per_box(self):
		result = self.get_details(fg_pieces_per_box=4)
		self.assertEqual(result["S"]["piece_qty"], 40)
		self.assertEqual(self.get_details({"pieces_per_box": "5"}, fg_pieces_per_box=4)["S"]["piece_qty"], 50)

	def test_form_pieces_per_box_adds_piece_quantities(self):
		result = self.get_details({"pieces_per_box": "5"})
		self.assertEqual(result["S"], {"qty": 10, "piece_qty": 50, "ratio": 1, "mrp": 100})
		self.assertEqual(result["M"]["piece_qty"], 100)

	def test_explicit_pieces_per_box_overrides_form(self):
		result = self.get_details({"pieces_per_box": "5"}, pieces_per_box=7)
		self.assertEqual(result["S"]["piece_qty"], 70)

	def test_invalid_pieces_per_box_throws(self):
		for value in (0, -1, 2.5, "abc"):
			with (
				self.subTest(value=value),
				patch.object(frappe, "throw", side_effect=frappe.ValidationError) as throw,
				self.assertRaises(frappe.ValidationError),
			):
				self.get_details(pieces_per_box=value)
			throw.assert_called_once_with("Pieces per Box must be a whole number greater than zero")

	def test_settings_find_fg_master_by_name(self):
		doc = _dict(item="FG-ITEM", check_permission=MagicMock())
		with (
			patch.object(frappe, "get_doc", return_value=doc) as get_doc,
			patch.object(frappe, "db", MagicMock()) as db,
		):
			db.exists.return_value = "FG-ITEM"
			db.get_value.return_value = "10"
			result = workflow.get_production_order_print_settings("PPO-TEST")
		self.assertEqual(result, {"fg_item_exists": True, "pieces_per_box": 10})
		get_doc.assert_called_once_with("YRP Production Order", "PPO-TEST")
		doc.check_permission.assert_called_once_with("read")
		db.exists.assert_called_once_with("SD YRP FG Item Master", "FG-ITEM")
		db.get_value.assert_called_once_with("SD YRP FG Item Master", "FG-ITEM", "pcs_per_box")

	def test_settings_find_fg_master_by_item(self):
		doc = _dict(item="FG-ITEM", check_permission=MagicMock())
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "db", MagicMock()) as db,
		):
			db.exists.return_value = None
			db.get_value.side_effect = ["FG-MASTER", 0]
			result = workflow.get_production_order_print_settings("PPO-TEST")
		self.assertEqual(result, {"fg_item_exists": True, "pieces_per_box": 0})
		db.get_value.assert_any_call("SD YRP FG Item Master", {"item": "FG-ITEM"}, "name")
		db.get_value.assert_any_call("SD YRP FG Item Master", "FG-MASTER", "pcs_per_box")
		doc.check_permission.assert_called_once_with("read")

	def test_settings_report_missing_fg_master(self):
		doc = _dict(item="MISSING", check_permission=MagicMock())
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "db", MagicMock()) as db,
		):
			db.exists.return_value = None
			db.get_value.return_value = None
			result = workflow.get_production_order_print_settings("PPO-TEST")
		self.assertEqual(result, {"fg_item_exists": False, "pieces_per_box": None})
		doc.check_permission.assert_called_once_with("read")
		db.get_value.assert_called_once_with("SD YRP FG Item Master", {"item": "MISSING"}, "name")

	def test_read_permission_is_required(self):
		doc = _dict(check_permission=MagicMock(side_effect=frappe.PermissionError))
		with patch.object(frappe, "get_doc", return_value=doc):
			for method in (workflow.get_production_order_details, workflow.get_production_order_print_settings):
				with self.subTest(method=method.__name__), self.assertRaises(frappe.PermissionError):
					method("PPO-TEST")

	def test_print_format_has_box_and_piece_rows_and_totals(self):
		path = Path(__file__).parent / "essdee_yrp/print_format/essdee_production_order/essdee_production_order.json"
		html = json.loads(json.loads(path.read_text())["format_data"])[-1]["options"]
		for text in (
			"<td>Qty (Box)</td>", "<td>Qty (Piece)</td>", "po_details[size]['piece_qty']",
			"{{ ns.total_qty }}", "{{ piece_ns.total_qty }}", "YRP Production Term Detail",
		):
			self.assertIn(text, html)
		self.assertLess(html.index("Qty (Box)"), html.index("Qty (Piece)"))
		self.assertLess(html.index("Qty (Piece)"), html.index("<td>Ratio</td>"))

	def test_desk_print_prepares_pieces_and_encodes_url(self):
		source = (Path(__file__).parent / "public/js/production_order_workflow.js").read_text()
		for text in (
			'frm.add_custom_button(__("Print")', "prepare_production_order_print(frm);",
			"get_production_order_print_settings", "Pieces per Box", '"&pieces_per_box="',
			'encodeURIComponent("YRP Production Order")', 'encodeURIComponent("Essdee Production Order")',
			"encodeURIComponent(frm.doc.name)", "freeze: true",
		):
			self.assertIn(text, source)
		self.assertNotIn("doctype=Production Order", source)

	def test_print_format_renders_box_and_piece_rows_from_request(self):
		text = self.render_format({"pieces_per_box": "7"})
		self.assertIn("Qty (Box) 525.0 350.0 875.0", text)
		self.assertIn("Qty (Piece) 3675.0 2450.0 6125.0", text)
		self.assertIn("Ratio 3.0 2.0", text)

	def test_generic_print_uses_fg_item_pieces_per_box(self):
		text = self.render_format({}, fg_pieces_per_box=4)
		self.assertIn("Qty (Box) 525.0 350.0 875.0", text)
		self.assertIn("Qty (Piece) 2100.0 1400.0 3500.0", text)

	def test_generic_print_without_any_pieces_per_box_shows_note(self):
		text = self.render_format({})
		self.assertIn("Qty (Box) 525.0 350.0 875.0", text)
		self.assertIn("Ratio 3.0 2.0", text)
		self.assertIn("Qty (Piece) Pieces per Box not set in FG Item Master", text)

	def test_print_format_renders_for_submitted_production_order(self):
		name = frappe.db.get_value("YRP Production Order", {"docstatus": 1}, "name", order_by="modified desc")
		if not name:
			self.skipTest("No submitted YRP Production Order on this site")
		form = _dict(doctype="YRP Production Order", name=name, format="Essdee Production Order", pieces_per_box="6")
		with patch.object(frappe, "form_dict", form):
			html = frappe.get_print(form.doctype, name, form.format)
		text = " ".join(frappe.utils.strip_html(html).split())
		self.assertIn(name, text)
		self.assertIn("Qty (Box)", text)
		self.assertIn("Qty (Piece)", text)

	def test_production_order_default_print_format_is_essdee(self):
		self.assertEqual(frappe.get_meta("YRP Production Order").default_print_format, "Essdee Production Order")

	def render_format(self, form, fg_pieces_per_box=None):
		path = Path(__file__).parent / "essdee_yrp/print_format/essdee_production_order/essdee_production_order.json"
		html = json.loads(json.loads(path.read_text())["format_data"])[-1]["options"]
		doc = _dict(production_order_details=[], check_permission=MagicMock())
		quantities = {"2-3": {"qty": 525.0, "ratio": 3.0, "mrp": 0.0}, "4-5": {"qty": 350.0, "ratio": 2.0, "mrp": 0.0}}
		get_doc = frappe.get_doc
		with (
			patch.object(frappe, "get_doc", side_effect=lambda *args: doc if args[0] == "YRP Production Order" else get_doc(*args)),
			patch.object(frappe, "form_dict", _dict(form)),
			patch.object(workflow, "get_order_qty", return_value=quantities),
			patch.object(workflow, "get_fg_pieces_per_box", return_value={"pieces_per_box": fg_pieces_per_box}),
		):
			rendered = frappe.render_template(html, {
				"doc": _dict(name="PPO-TEST", item="STYLE", production_term=None),
				"get_production_order_details": workflow.get_production_order_details,
			})
		return " ".join(frappe.utils.strip_html(rendered).split())
