import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer import (
	ITEM_EDITOR_CONFIG,
	SDYRPLotTransfer,
)
from essdee_yrp.fabric_store import web_workspace


class LotTransferRow(frappe._dict):
	def as_dict(self):
		return dict(self)

	@property
	def meta(self):
		return frappe.get_meta("SD YRP Lot Transfer Item")

	def set(self, fieldname, value):
		self[fieldname] = value


class TestLotTransferEditorParity(TestCase):
	def test_cutting_grouping_contract_does_not_export_display_indexes(self):
		self.assertEqual(ITEM_EDITOR_CONFIG["entry_fields"], ["from_lot", "to_lot", "warehouse", "received_type", "set_combination"])

	def setUp(self):
		fields = json.loads((Path(__file__).parent.parent / "sd_yrp_lot_transfer_item/sd_yrp_lot_transfer_item.json").read_text())["fields"]
		fields = {field["fieldname"]: frappe._dict(field) for field in fields}
		fields["quality_grade"] = frappe._dict(fieldtype="Data")
		meta = MagicMock()
		meta.get_field.side_effect = fields.get
		patches = [
			patch("frappe.get_meta", return_value=meta),
			patch("frappe.get_hooks", return_value=[]),
			patch("frappe.get_doc", side_effect=lambda doctype, variant: frappe._dict(attributes=[frappe._dict(attribute="Size", attribute_value=variant.split("-")[-1])])),
			patch("yrp.yrp.doctype.yrp_item.yrp_item.get_parent_item", return_value="STYLE"),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.get_parent_item", return_value="STYLE"),
			patch("yrp.yrp.doctype.yrp_item.yrp_item.get_attribute_details", return_value={"item": "STYLE", "attributes": [], "primary_attribute": "Size", "primary_attribute_values": ["XS", "S"], "default_uom": "Box"}),
			patch("yrp.stock.save_stock_items._resolve_or_create_variant", side_effect=lambda item, attributes: f"{item}-{attributes['Size']}"),
			patch("yrp.stock.save_stock_items.get_dimension_fieldnames", return_value=["received_type", "quality_grade"]),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.get_dimension_fieldnames", return_value=["lot", "received_type", "quality_grade"]),
			patch("yrp.stock.utils.apply_posting_datetime"),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.apply_dimension_defaults"),
			patch("yrp.stock.uom.resolve_item_uom", return_value=frappe._dict(uom="Box", stock_uom="Nos", conversion_factor=2)),
			patch("yrp.stock.utils.get_stock_balance", return_value=(100, 10)),
		]
		for name in ("validate_disabled", "validate_is_stock_item", "validate_cancelled_item"):
			patches.append(patch(f"yrp.yrp.doctype.yrp_item.yrp_item.{name}"))
		for mock in patches:
			mock.start()
			self.addCleanup(mock.stop)

	def make_document(self):
		doc = MagicMock(doctype="SD YRP Lot Transfer", docstatus=0, _action="save")
		doc.name = "LT-TEST"
		doc.items = []
		doc.get.side_effect = lambda key: getattr(doc, key, None)
		doc.set.side_effect = lambda key, values: setattr(doc, key, [LotTransferRow(row, idx=index + 1) for index, row in enumerate(values)])
		doc.set_onload.side_effect = lambda key, value: setattr(doc, "__onload", {key: value})
		doc.run_method.side_effect = lambda method: SDYRPLotTransfer.onload(doc)
		doc._stock_dimensions.side_effect = lambda row, lot: SDYRPLotTransfer._stock_dimensions(doc, row, lot)
		doc._validate_row.side_effect = lambda row: SDYRPLotTransfer._validate_row(doc, row)
		return doc

	def groups(self, combination=None):
		entry = {"name": "STYLE", "from_lot": "FROM", "to_lot": "TO", "warehouse": "WH", "received_type": "Accepted", "dimensions": {"quality_grade": "A"}, "primary_attribute": "Size", "default_uom": "Box", "values": {"XS": {"qty": 3}, "S": {"qty": 5}}}
		if combination is not None:
			entry["set_combination"] = combination
		return [{"attributes": [], "primary_attribute": "Size", "primary_attribute_values": ["XS", "S"], "items": [entry]}]

	def prepare(self, doc):
		SDYRPLotTransfer.before_validate(doc)
		SDYRPLotTransfer.validate(doc)
		return [dict(row) for row in doc.items]

	def test_web_and_desk_rows_match_field_for_field_with_and_without_set_combination(self):
		for combination in (None, '{"Colour":"Blue"}'):
			with self.subTest(combination=combination):
				desk, web = self.make_document(), self.make_document()
				desk.item_details = frappe.as_json(self.groups(combination))
				groups = self.groups(combination)
				for group in groups:
					for entry in group["items"]:
						entry["dimensions"].update({key: entry.pop(key) for key in ("from_lot", "to_lot", "warehouse", "received_type")})
				web.insert.side_effect = lambda: self.prepare(web)
				with (
					patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
					patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=web),
					patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={}),
				):
					web_workspace.save_stock_operation("lot_transfer", {"item_details": groups})
				self.assertEqual([dict(row) for row in web.items], self.prepare(desk))
				self.assertEqual({row.item: (row.table_index, row.row_index, row.stock_qty, row.conversion_factor) for row in web.items}, {"STYLE-XS": (0, 0, 6, 2), "STYLE-S": (0, 0, 10, 2)})
				self.assertEqual([row.get("set_combination") for row in web.items], [combination, combination])

	def test_reopen_and_resave_preserves_rows_including_legacy_indexes_and_dimensions(self):
		doc = self.make_document()
		doc.item_details = frappe.as_json(self.groups('{"Colour":"Blue"}'))
		self.prepare(doc)
		for row in doc.items:
			row.table_index, row.row_index = 4, 9
		before = [dict(row) for row in doc.items]
		doc.save.side_effect = lambda: self.prepare(doc)
		with (
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=doc),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace._permission_flags", return_value={"can_write": True}),
			patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={}),
		):
			groups = web_workspace.get_stock_operation_editor("lot_transfer", name=doc.name)["item_groups"]
			self.assertEqual(len(groups[0]["items"]), 2)
			self.assertEqual(sorted(sum(value["qty"] for value in entry["values"].values()) for entry in groups[0]["items"]), [3, 5])
			web_workspace.save_stock_operation("lot_transfer", {"item_details": groups}, name=doc.name)
		self.assertEqual([dict(row) for row in doc.items], before)


class TestLotTransfer(IntegrationTestCase):
	def test_posting_fields_require_edit_checkbox(self):
		meta = frappe.get_meta("SD YRP Lot Transfer", cached=False)
		edit_control = meta.get_field("edit_posting_date_and_time")
		posting_date = meta.get_field("posting_date")
		posting_time = meta.get_field("posting_time")

		self.assertEqual(edit_control.fieldtype, "Check")
		self.assertLess(edit_control.idx, posting_date.idx)
		self.assertEqual(posting_date.read_only_depends_on, "eval: !doc.edit_posting_date_and_time")
		self.assertEqual(posting_time.read_only_depends_on, "eval: !doc.edit_posting_date_and_time")
		self.assertTrue(posting_date.no_copy)
		self.assertTrue(posting_time.no_copy)
		self.assertEqual(meta.get_field("items").options, "SD YRP Lot Transfer Item")
		finishing_plan = meta.get_field("finishing_plan")
		self.assertEqual(finishing_plan.options, "SD YRP Finishing Plan")
		self.assertTrue(finishing_plan.hidden)

		item_meta = frappe.get_meta("SD YRP Lot Transfer Item", cached=False)
		self.assertEqual(item_meta.get_field("warehouse").options, "Warehouse")
		self.assertTrue(item_meta.get_field("warehouse").reqd)
		self.assertEqual(item_meta.get_field("received_type").options, "YRP Received Type")
		self.assertTrue(item_meta.get_field("received_type").reqd)

	def test_valuation_lookup_passes_stock_dimensions_by_name(self):
		transfer = frappe.new_doc("SD YRP Lot Transfer")
		transfer.posting_date = "2026-07-29"
		transfer.posting_time = "12:34:56"
		row = frappe._dict(
			{
				"idx": 1,
				"item": "_Test Lot Transfer Variant",
				"from_lot": "LOT-A",
				"to_lot": "LOT-B",
				"warehouse": "Main Warehouse",
				"received_type": "Accepted",
				"quality_grade": "A",
				"qty": 2,
				"uom": "Kg",
				"rate": 0,
			}
		)

		with (
			patch(
				"frappe.db.get_value",
				return_value="_Test Lot Transfer Item",
			),
			patch(
				"yrp.yrp.doctype.yrp_item.yrp_item.validate_disabled",
			),
			patch(
				"yrp.yrp.doctype.yrp_item.yrp_item.validate_is_stock_item",
			),
			patch(
				"yrp.yrp.doctype.yrp_item.yrp_item.validate_cancelled_item",
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.apply_item_uom",
				side_effect=lambda target, item_field: target.update(
					{"uom": "Kg", "stock_uom": "Kg", "conversion_factor": 1}
				),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.get_dimension_fieldnames",
				return_value=["lot", "received_type", "quality_grade"],
			),
			patch(
				"yrp.stock.utils.get_stock_balance",
				return_value=(6.67, 130),
			) as get_stock_balance,
		):
			transfer._validate_row(row)

		get_stock_balance.assert_called_once_with(
			"_Test Lot Transfer Variant",
			"Main Warehouse",
			posting_date="2026-07-29",
			posting_time="12:34:56",
			with_valuation_rate=True,
			lot="LOT-A",
			received_type="Accepted",
			quality_grade="A",
		)
		self.assertEqual(row.rate, 130)
		self.assertEqual(row.stock_qty, 2)
		self.assertEqual(row.stock_uom_rate, 130)
		self.assertEqual(row.amount, 260)

	def test_submit_persists_actual_fifo_transfer_value(self):
		transfer = frappe.new_doc("SD YRP Lot Transfer")
		transfer.name = "LT-ACTUAL-RATE"
		transfer.docstatus = 1
		transfer.posting_date = "2026-07-29"
		transfer.posting_time = "12:34:56"
		row = frappe._dict(
			doctype="SD YRP Lot Transfer Item",
			name="LT-ROW-1",
			item="_Test Lot Transfer Variant",
			from_lot="LOT-A",
			to_lot="LOT-B",
			warehouse="Main Warehouse",
			received_type="Accepted",
			quality_grade="A",
			stock_qty=4,
			stock_uom="Kg",
			stock_uom_rate=100,
			conversion_factor=2,
		)
		transfer.items = [row]

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.get_dimension_fieldnames",
				return_value=["lot", "received_type", "quality_grade"],
			),
			patch(
				"yrp.stock.stock_ledger.make_sl_entries",
				return_value={"LT-ACTUAL-RATE:LT-ROW-1": 125},
			) as make_entries,
			patch("frappe.db.set_value") as set_value,
		):
			transfer._update_stock_ledger()

		entries = make_entries.call_args.args[0]
		self.assertAlmostEqual(entries[0]["qty"] + entries[1]["qty"], 0)
		self.assertEqual(entries[0]["_transfer_role"], "outgoing")
		self.assertEqual(entries[1]["_transfer_role"], "incoming")
		self.assertEqual(entries[0]["_transfer_key"], entries[1]["_transfer_key"])
		self.assertEqual(row.stock_uom_rate, 125)
		self.assertEqual(row.rate, 250)
		self.assertEqual(row.amount, 500)
		set_value.assert_called_once_with(
			"SD YRP Lot Transfer Item",
			"LT-ROW-1",
			{"stock_uom_rate": 125.0, "rate": 250.0, "amount": 500.0},
			update_modified=False,
		)
