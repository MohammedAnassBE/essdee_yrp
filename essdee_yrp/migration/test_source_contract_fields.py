from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


BENCH_ROOT = Path(__file__).resolve().parents[4]
YRP_ROOT = BENCH_ROOT / "apps" / "yrp" / "yrp"
ESSDEE_ROOT = BENCH_ROOT / "apps" / "essdee_yrp" / "essdee_yrp"


DIRECT_FIELDS = {
	"SD YRP Cut Panel Movement": {"process_name": ("Link", "YRP Process")},
	"SD YRP Cutting Marker": {
		"cutting_marker_parts": ("Table", "SD YRP Cutting Marker Part")
	},
	"SD YRP Essdee Quality Inspection": {"unit_name": ("Link", "Supplier")},
	"SD YRP FG Stock Entry": {"lot": ("Link", "SD YRP Lot")},
	"SD YRP Lot": {
		"version": ("Select", "\nV1\nV2"),
		"capacity_planning": ("Check", None),
		"primary_item_attribute": ("Link", "Item Attribute"),
	},
	"SD YRP Lotwise Item Profit Qty Rate": {
		"ratio": ("Int", None),
		"weight": ("Float", None),
	},
	"SD YRP MRP Settings": {
		"auto_send_notifications": (
			"Table",
			"SD YRP MRP Settings Notification Doctype List",
		),
		"yrp_api_key": ("Data", None),
		"yrp_api_secret": ("Password", None),
		"yrp_site_url": ("Data", None),
	},
	"SD YRP Production Items": {"process_name": ("Link", "YRP Process")},
	"SD YRP Sewing Plan": {
		"strength_report_date": ("Date", None),
		"strength_report_from_time": ("Time", None),
		"strength_report_to_time": ("Time", None),
	},
	"YRP Goods Received Note": {
		"billing_address": ("Link", "Address"),
		"billing_address_display": ("Small Text", None),
	},
	"YRP Goods Received Note Item": {
		"received_quantity": ("Float", None),
		"rework_details": ("Small Text", None),
	},
	"YRP Item BOM": {
		"attribute_mapping_based_on": ("Link", "Item Attribute")
	},
	"YRP Item BOM Attribute Mapping Value": {
		"bom_item_attribute": ("Data", None),
		"product_attribute": ("Data", None),
	},
	"YRP Item Price": {"price": ("Float", None)},
	"YRP Item Production Detail": {"description": ("Small Text", None)},
	"YRP Process Cost": {
		"dependent_attribute": ("Link", "Item Attribute"),
		"dependent_attribute_values": ("Select", None),
	},
	"YRP Production Order": {
		"production_detail": ("Link", "YRP Item Production Detail")
	},
	"YRP Purchase Invoice": {
		"debit_no": ("Data", None),
		"debit_type": ("Select", "\nPermanent\nTemporary"),
		"debit_value": ("Currency", None),
	},
	"YRP ZPL Raw Print Format": {"raw_code": ("Code", None)},
	"YRP Bin": {"reserved_qty": ("Float", None)},
}


SCHEMA_PATHS = {
	"SD YRP Cut Panel Movement": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_cut_panel_movement/sd_yrp_cut_panel_movement.json",
	"SD YRP Cutting Marker": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_cutting_marker/sd_yrp_cutting_marker.json",
	"SD YRP Essdee Quality Inspection": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_essdee_quality_inspection/sd_yrp_essdee_quality_inspection.json",
	"SD YRP FG Stock Entry": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_fg_stock_entry/sd_yrp_fg_stock_entry.json",
	"SD YRP Lot": ESSDEE_ROOT / "essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json",
	"SD YRP Lotwise Item Profit Qty Rate": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_lotwise_item_profit_qty_rate/sd_yrp_lotwise_item_profit_qty_rate.json",
	"SD YRP MRP Settings": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_mrp_settings/sd_yrp_mrp_settings.json",
	"SD YRP Production Items": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_production_items/sd_yrp_production_items.json",
	"SD YRP Sewing Plan": ESSDEE_ROOT
	/ "essdee_yrp/doctype/sd_yrp_sewing_plan/sd_yrp_sewing_plan.json",
	"YRP Goods Received Note": YRP_ROOT
	/ "yrp/doctype/yrp_goods_received_note/yrp_goods_received_note.json",
	"YRP Goods Received Note Item": YRP_ROOT
	/ "yrp/doctype/yrp_goods_received_note_item/yrp_goods_received_note_item.json",
	"YRP Item BOM": YRP_ROOT / "yrp/doctype/yrp_item_bom/yrp_item_bom.json",
	"YRP Item BOM Attribute Mapping Value": YRP_ROOT
	/ "yrp/doctype/yrp_item_bom_attribute_mapping_value/yrp_item_bom_attribute_mapping_value.json",
	"YRP Item Price": YRP_ROOT / "yrp/doctype/yrp_item_price/yrp_item_price.json",
	"YRP Item Production Detail": YRP_ROOT
	/ "yrp/doctype/yrp_item_production_detail/yrp_item_production_detail.json",
	"YRP Process Cost": YRP_ROOT / "yrp/doctype/yrp_process_cost/yrp_process_cost.json",
	"YRP Production Order": YRP_ROOT
	/ "yrp/doctype/yrp_production_order/yrp_production_order.json",
	"YRP Purchase Invoice": YRP_ROOT
	/ "yrp/doctype/yrp_purchase_invoice/yrp_purchase_invoice.json",
	"YRP ZPL Raw Print Format": YRP_ROOT
	/ "yrp/doctype/yrp_zpl_raw_print_format/yrp_zpl_raw_print_format.json",
	"YRP Bin": YRP_ROOT / "yrp_stock/doctype/yrp_bin/yrp_bin.json",
}


PHYSICAL_OVERLAYS = {
	"Cut Panel Movement": {"process_name"},
	"Cutting Marker": {"cutting_marker_parts"},
	"Cutting Laysheet Planner": {"description", "item", "lot"},
	"Essdee Quality Inspection": {"unit_name"},
	"Essdee Raw Print Format": {"raw_code"},
	"FG Stock Entry": {"lot"},
	"Goods Received Note": {"billing_address", "billing_address_display"},
	"Goods Received Note Item": {"received_quantity", "rework_details"},
	"Item BOM": {"attribute_mapping_based_on"},
	"Item BOM Attribute Mapping": {"lot_template"},
	"Item BOM Attribute Mapping Value": {"bom_item_attribute", "product_attribute"},
	"Item Price": {"price"},
	"Item Production Detail": {"additional_cloth", "stiching_attribute_quantity"},
	"Lot": {"capacity_planning", "primary_item_attribute", "version"},
	"Lotwise Item Profit Qty Rate": {"ratio", "weight"},
	"Process Cost": {"dependent_attribute", "dependent_attribute_values"},
	"Production Items": {"process_name"},
	"Production Order": {"production_detail"},
	"Purchase Invoice": {"debit_no", "debit_type", "debit_value"},
	"Purchase Order": {"billing_address", "billing_address_display"},
	"Sewing Plan": {
		"strength_report_date",
		"strength_report_from_time",
		"strength_report_to_time",
	},
	"Supplier": {"deparments"},
}


def _load_overlays() -> dict[str, list[dict]]:
	path = ESSDEE_ROOT.parent / "scripts" / "f15_source_bridge.py"
	tree = ast.parse(path.read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == "SOURCE_SCHEMA_OVERLAYS"
			for target in node.targets
		):
			return ast.literal_eval(node.value)
	raise AssertionError("SOURCE_SCHEMA_OVERLAYS is not declared")


class SourceContractFieldTest(unittest.TestCase):
	def test_owner_fields_are_direct_doctype_fields(self):
		self.assertEqual(set(SCHEMA_PATHS), set(DIRECT_FIELDS))
		for doctype, path in SCHEMA_PATHS.items():
			schema = json.loads(path.read_text(encoding="utf-8"))
			self.assertEqual(schema["name"], doctype)
			fields = {field["fieldname"]: field for field in schema["fields"]}
			for fieldname, (fieldtype, options) in DIRECT_FIELDS[doctype].items():
				with self.subTest(doctype=doctype, fieldname=fieldname):
					self.assertEqual(fields[fieldname]["fieldtype"], fieldtype)
					self.assertEqual(fields[fieldname].get("options"), options)
					self.assertIn(fieldname, schema["field_order"])

	def test_high_precision_historical_numeric_columns_stay_nine_place(self):
		for doctype, fieldname in (
			("SD YRP Lotwise Item Profit Qty Rate", "weight"),
			("YRP Goods Received Note Item", "received_quantity"),
			("YRP Item Price", "price"),
			("YRP Purchase Invoice", "debit_value"),
		):
			schema = json.loads(SCHEMA_PATHS[doctype].read_text(encoding="utf-8"))
			fields = {field["fieldname"]: field for field in schema["fields"]}
			self.assertEqual(fields[fieldname].get("precision"), "9")

	def test_essdee_extensions_of_yrp_are_fixtures_only(self):
		fixture_path = ESSDEE_ROOT / "fixtures" / "custom_field.json"
		fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
		fields = {(row["dt"], row["fieldname"]): row for row in fixture}
		expected = {
			"YRP Goods Received Note": {
				"essdee_yrp_stock_entry",
				"essdee_yrp_stock_entry_created",
			},
			"YRP Item BOM Attribute Mapping": {"lot_template"},
			"YRP Item Production Detail": {
				"additional_cloth",
				"original_process_rows",
				"stiching_attribute_quantity",
			},
			"YRP YRP Stock Settings": {
				"location_mapping",
				"sms_old_database_host",
				"sms_old_database_name",
				"sms_old_database_password",
				"sms_old_database_port",
				"sms_old_database_user",
			},
		}
		for doctype, fieldnames in expected.items():
			for fieldname in fieldnames:
				self.assertIn((doctype, fieldname), fields)
		self.assertNotIn(("YRP Supplier", "deparments"), fields)
		for source in (ESSDEE_ROOT / "setup.py", ESSDEE_ROOT / "lot_packing_setup.py"):
			self.assertNotIn("create_custom_fields", source.read_text(encoding="utf-8"))

	def test_every_populated_or_owner_restored_physical_column_is_exported(self):
		overlays = _load_overlays()
		for doctype, expected_fields in PHYSICAL_OVERLAYS.items():
			actual_fields = {row["fieldname"] for row in overlays[doctype]}
			with self.subTest(doctype=doctype):
				self.assertTrue(expected_fields <= actual_fields)


if __name__ == "__main__":
	unittest.main()
