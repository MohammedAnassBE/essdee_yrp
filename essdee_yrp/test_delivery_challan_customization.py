from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import hooks
from essdee_yrp.cutting.movement import (
	_overlay_source_rows,
)
from essdee_yrp.delivery_challan_hooks import (
	before_validate,
	create_return_grn,
	sync_cutting_plan_received_cloth,
)
from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import (
	fetch_received_cloth,
)
from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes
from essdee_yrp.overrides.delivery_challan import EssdeeDeliveryChallan
from yrp.yrp.doctype.delivery_challan.delivery_challan import DeliveryChallan


class TestDeliveryChallanCustomization(FrappeTestCase):
	def test_dc_submit_and_cancel_hooks_rebuild_linked_cutting_plans(self):
		doc = frappe._dict(work_order="WO-CUTTING")
		plan = frappe._dict(name="CP-1")
		with (
			patch.object(frappe, "get_all", return_value=["CP-1"]),
			patch.object(frappe, "get_doc", return_value=plan),
			patch(
				"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.rebuild_received_cloth"
			) as rebuild,
		):
			sync_cutting_plan_received_cloth(doc)
		rebuild.assert_called_once_with(plan)

	def test_custom_return_matrix_uses_authoritative_base_endpoints(self):
		source = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "public/js/delivery_challan.js"
		).read_text(encoding="utf-8")
		component = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "public/js/DeliveryChallan/ReturnItemsMatrix.vue"
		).read_text(encoding="utf-8")
		self.assertIn("Return Whole Bundles", source)
		self.assertIn("get_return_delivery_items", source)
		self.assertIn("essdee_yrp.delivery_challan_hooks.create_return_grn", source)
		self.assertNotIn('fieldtype: "Table"', source)
		self.assertIn("returnable_quantity", component)
		self.assertIn("selectAll", component)

	def test_return_wrapper_preserves_base_validation(self):
		with patch(
			"yrp.yrp.doctype.delivery_challan.delivery_challan.create_return_grn",
			return_value="GRN-RETURN-1",
		) as base_return:
			name = create_return_grn(
				"DC-1",
				[{"delivery_challan_item": "DCI-1", "return_quantity": 2}],
				"Accepted",
			)
		self.assertEqual(name, "GRN-RETURN-1")
		base_return.assert_called_once()

	def test_secondary_quantity_uses_the_base_inline_dc_matrix(self):
		app_path = Path(frappe.get_app_path("essdee_yrp"))
		source = (app_path / "public/js/delivery_challan.js").read_text(
			encoding="utf-8"
		)
		plugins = (app_path / "public/js/vue_plugins.js").read_text(
			encoding="utf-8"
		)
		base_editor = (
			Path(frappe.get_app_path("yrp"))
			/ "public/js/WorkOrder/WorkOrderItemEditor.vue"
		).read_text(encoding="utf-8")
		base_matrix = (
			Path(frappe.get_app_path("yrp"))
			/ "public/js/Stock/components/ItemDimensionFetch.vue"
		).read_text(encoding="utf-8")

		self.assertNotIn("mount_secondary_quantity_editor", source)
		self.assertNotIn("DeliverySecondaryQuantity", plugins)
		self.assertIn("name: 'secondary_qty'", base_editor)
		self.assertIn("inline_edit: true", base_editor)
		self.assertIn("on_inline_table_field_change", base_matrix)

	def test_manual_source_property_setter_is_packaged(self):
		name = "Delivery Challan-from_location-fetch_from"
		fixture = frappe.parse_json(
			(
				Path(frappe.get_app_path("essdee_yrp"))
				/ "fixtures"
				/ "property_setter.json"
			).read_text(encoding="utf-8")
		)
		setter = next(row for row in fixture if row.get("name") == name)
		self.assertEqual(
			(
				setter["doc_type"],
				setter["field_name"],
				setter["property"],
				setter["value"],
			),
			("Delivery Challan", "from_location", "fetch_from", ""),
		)
		property_fixture = next(row for row in hooks.fixtures if row["dt"] == "Property Setter")
		self.assertIn(name, property_fixture["filters"][0][2])

	def test_site_uses_essdee_delivery_challan_controller(self):
		self.assertIsInstance(frappe.new_doc("Delivery Challan"), EssdeeDeliveryChallan)

	def test_same_location_and_warehouse_delivery_is_allowed(self):
		doc = EssdeeDeliveryChallan(
			{
				"doctype": "Delivery Challan",
				"docstatus": 1,
				"from_location": "SAME-LOCATION",
				"supplier": "SAME-LOCATION",
				"from_warehouse": "SAME-WAREHOUSE",
				"to_warehouse": "SAME-WAREHOUSE",
				"items": [
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "SAME-WAREHOUSE-ITEM",
						"qty": 1,
					}
				],
			}
		)

		doc.validate_items()
		doc.compute_internal_unit()

		self.assertEqual(doc.is_internal_unit, 0)

		doc.items[0].item_variant = ""
		with self.assertRaisesRegex(frappe.ValidationError, "Item Variant is required"):
			doc.validate_items()

		doc.items[0].item_variant = "SAME-WAREHOUSE-ITEM"
		doc.items[0].qty = 0
		with self.assertRaisesRegex(frappe.ValidationError, "Qty must be greater than zero"):
			doc.validate_items()

	def test_same_warehouse_delivery_builds_balanced_stock_legs(self):
		doc = EssdeeDeliveryChallan(
			{
				"doctype": "Delivery Challan",
				"name": "DC-SAME-WAREHOUSE-1",
				"posting_date": "2026-08-28",
				"posting_time": "12:00:00",
				"from_warehouse": "SAME-WAREHOUSE",
				"to_warehouse": "SAME-WAREHOUSE",
				"items": [
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "SAME-WAREHOUSE-ITEM",
						"uom": "Nos",
						"stock_uom": "Nos",
						"qty": 5,
						"stock_qty": 5,
						"rate": 12.5,
						"valuation_rate": 12.5,
					}
				],
			}
		)

		with (
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=[]),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_sl_entries,
		):
			doc.make_stock_ledger_entries()

		entries = make_sl_entries.call_args.args[0]
		self.assertEqual(len(entries), 2)
		self.assertEqual([row["warehouse"] for row in entries], ["SAME-WAREHOUSE"] * 2)
		self.assertEqual([row["qty"] for row in entries], [-5, 5])
		self.assertEqual(
			[row["_transfer_role"] for row in entries],
			["outgoing", "incoming"],
		)
		self.assertEqual(entries[0]["_transfer_key"], entries[1]["_transfer_key"])
		make_sl_entries.assert_called_once_with(entries, cancel=False)

	def test_same_location_delivery_updates_work_order_and_cutting_plan(self):
		doc = EssdeeDeliveryChallan(
			{
				"doctype": "Delivery Challan",
				"work_order": "WO-SAME-LOCATION",
				"from_location": "MACHINE-CUTTING",
				"supplier": "MACHINE-CUTTING",
				"from_warehouse": "MACHINE-CUTTING-WAREHOUSE",
				"to_warehouse": "MACHINE-CUTTING-WAREHOUSE",
				"items": [
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "CUTTING-CLOTH",
						"qty": 4,
						"delivered_quantity": 4,
					}
				],
			}
		)
		doc.compute_internal_unit()
		self.assertEqual(doc.is_internal_unit, 0)

		deliverable = frappe._dict(pending_quantity=10)
		deliverable.db_set = MagicMock()
		work_order = frappe._dict(deliverables=[deliverable])
		with (
			patch(
				"yrp.yrp.doctype.delivery_challan.delivery_challan.frappe.get_doc",
				return_value=work_order,
			),
			patch(
				"yrp.yrp.doctype.delivery_challan.delivery_challan._find_matching_row",
				return_value=deliverable,
			),
			patch(
				"yrp.yrp.doctype.delivery_challan.delivery_challan._update_work_order_status"
			),
		):
			doc.update_work_order_deliverables()

		deliverable.db_set.assert_called_once_with(
			"pending_quantity", 6.0, update_modified=False
		)

		cloth_row = frappe._dict(
			cloth_item_variant="CUTTING-CLOTH",
			weight=0,
			used_weight=1.5,
		)
		cutting_plan = MagicMock()
		cutting_plan.work_order = doc.work_order
		cutting_plan.cutting_plan_cloth_details = [cloth_row]
		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan._get_submitted_cutting_plan",
				return_value=cutting_plan,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.frappe.get_all",
				return_value=["DC-SAME-LOCATION"],
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.frappe.get_value",
				return_value=(
					doc.is_internal_unit,
					doc.from_location,
					doc.supplier,
				),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.frappe.get_doc",
				return_value=doc,
			),
		):
			fetch_received_cloth("CP-SAME-LOCATION")

		self.assertEqual(cloth_row.weight, 4)
		self.assertEqual(cloth_row.balance_weight, 2.5)
		cutting_plan.save.assert_called_once_with(ignore_permissions=True)

	def test_desk_clears_source_when_work_order_changes(self):
		source = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "public"
			/ "js"
			/ "delivery_challan.js"
		).read_text(encoding="utf-8")

		self.assertIn("work_order(frm)", source)
		self.assertIn('from_location: ""', source)
		self.assertIn('from_warehouse: ""', source)

	def test_work_order_defaults_cannot_refill_manual_source_fields(self):
		doc = EssdeeDeliveryChallan({"doctype": "Delivery Challan"})

		def apply_base_defaults(target):
			target.from_location = (
				target.from_location or "WORK-ORDER-DELIVERY-LOCATION"
			)
			target.from_warehouse = (
				target.from_warehouse or "WORK-ORDER-DELIVERY-WAREHOUSE"
			)

		for from_location, from_warehouse in (
			("", ""),
			("SELECTED-LOCATION", ""),
			("SELECTED-LOCATION", "SELECTED-WAREHOUSE"),
		):
			with self.subTest(
				from_location=from_location,
				from_warehouse=from_warehouse,
			):
				doc.from_location = from_location
				doc.from_warehouse = from_warehouse
				with patch.object(
					DeliveryChallan,
					"set_missing_values",
					autospec=True,
					side_effect=apply_base_defaults,
				):
					doc.set_missing_values()

				self.assertEqual(doc.from_location, from_location)
				self.assertEqual(doc.from_warehouse, from_warehouse)

	def test_specialized_service_can_resolve_its_explicit_source_warehouse(self):
		doc = EssdeeDeliveryChallan(
			{
				"doctype": "Delivery Challan",
				"from_finishing": 1,
				"from_location": "FINISHING-LOCATION",
			}
		)

		def apply_base_defaults(target):
			target.from_warehouse = "FINISHING-WAREHOUSE"

		with patch.object(
			DeliveryChallan,
			"set_missing_values",
			autospec=True,
			side_effect=apply_base_defaults,
		):
			doc.set_missing_values()

		self.assertEqual(doc.from_location, "FINISHING-LOCATION")
		self.assertEqual(doc.from_warehouse, "FINISHING-WAREHOUSE")

	def test_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Delivery Challan", cached=False)
		expected = {
			"actual_date": ("Date", None),
			"additional_goods_value": ("Currency", None),
			"allow_non_bundle": ("Check", None),
			"cut_panel_movement": ("Link", "Cut Panel Movement"),
			"from_address": ("Link", "Address"),
			"from_address_details": ("Small Text", None),
			"from_finishing": ("Check", None),
			"from_location_name": ("Data", None),
			"includes_packing": ("Check", None),
			"letter_head": ("Link", "Letter Head"),
			"loose_piece_dc": ("Check", None),
			"pack_piece_dc": ("Check", None),
			"supplier_address": ("Link", "Address"),
			"supplier_address_details": ("Small Text", None),
			"supplier_name": ("Data", None),
		}

		for fieldname, definition in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), definition)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Delivery Challan",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_approved_field_attributes(self):
		meta = frappe.get_meta("Delivery Challan", cached=False)

		from_location = meta.get_field("from_location")
		self.assertEqual(from_location.reqd, 1)
		self.assertFalse(from_location.read_only)
		self.assertFalse(from_location.fetch_from)
		self.assertTrue(
			frappe.db.exists(
				"Property Setter", "Delivery Challan-from_location-fetch_from"
			)
		)
		self.assertEqual(meta.get_field("is_internal_unit").read_only, 1)
		self.assertFalse(meta.get_field("is_internal_unit").fetch_from)
		self.assertEqual(meta.get_field("is_rework").read_only, 1)
		self.assertEqual(meta.get_field("is_rework").fetch_from, "work_order.is_rework")

		lot = meta.get_field("lot")
		self.assertEqual(
			(lot.reqd, lot.read_only, lot.fetch_from, lot.fetch_if_empty),
			(1, 1, "work_order.lot", 1),
		)

		ste_transferred = meta.get_field("ste_transferred")
		self.assertEqual(ste_transferred.depends_on, "eval: doc.is_internal_unit")
		self.assertEqual(str(ste_transferred.precision), "2")
		self.assertEqual(
			meta.get_field("transfer_complete").depends_on,
			"eval: doc.is_internal_unit",
		)
		self.assertEqual(meta.get_field("vehicle_no").allow_on_submit, 1)

	def test_better_base_attributes_are_preserved(self):
		parent = frappe.get_meta("Delivery Challan", cached=False)
		child = frappe.get_meta("Delivery Challan Item", cached=False)

		self.assertEqual(parent.get_field("naming_series").options, "DC-.YYYY.-")
		self.assertEqual(parent.get_field("comments").fieldtype, "Small Text")
		self.assertEqual(parent.get_field("supplier").fetch_from, "to_warehouse.supplier")
		self.assertEqual(str(parent.get_field("total_delivered_qty").precision), "3")
		self.assertEqual(str(child.get_field("pending_quantity").precision), "3")
		self.assertEqual(str(child.get_field("secondary_qty").precision), "3")

	def test_work_order_context_is_enforced_server_side(self):
		doc = frappe.new_doc("Delivery Challan")
		doc.work_order = "TEST-WO"
		doc.is_internal_unit = 0

		with patch(
			"essdee_yrp.delivery_challan_hooks.frappe.db.get_value",
			return_value=frappe._dict(
				is_internal_unit=1,
				is_rework=1,
				lot="LOT-001",
				includes_packing=1,
			),
		):
			before_validate(doc)

		# Transaction routing is computed by base Delivery Challan from both
		# endpoints; the Work Order's supplier-only flag must not overwrite it.
		self.assertEqual(doc.is_internal_unit, 0)
		self.assertEqual(doc.is_rework, 1)
		self.assertEqual(doc.lot, "LOT-001")
		self.assertEqual(doc.includes_packing, 1)

	def test_cutting_dc_sizes_share_one_logical_row(self):
		variants = {
			"BOTTOM-LEFT-45": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Bottom Front Left"),
					frappe._dict(attribute="Colour", attribute_value="Dark Grey"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"BOTTOM-LEFT-50": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Bottom Front Left"),
					frappe._dict(attribute="Colour", attribute_value="Dark Grey"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(primary_attribute="Size")

		def get_cached_doc(doctype, name):
			return variants[name] if doctype == "Item Variant" else item

		rows = [
			frappe._dict(
				item_variant=variant,
				lot="C0826-57",
				received_type="Accepted",
				set_combination={"major_part": "Bottom", "major_colour": "Dark Grey"},
			)
			for variant in variants
		]
		with (
			patch(
				"essdee_yrp.item_matrix.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"essdee_yrp.item_matrix.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			normalized = normalize_item_matrix_row_indexes(rows)

		self.assertEqual(len({row.row_index for row in normalized}), 1)

	def test_cpm_display_indexes_replace_work_order_indexes(self):
		source_rows = [
			{
				"item_variant": variant,
				"qty": 10,
				"row_index": source_index,
				"table_index": source_index,
				"conversion_factor": 1,
				"set_combination": {},
			}
			for variant, source_index in (("BOTTOM-LEFT-45", 11), ("BOTTOM-LEFT-50", 12))
		]
		movement_rows = [
			frappe._dict(
				item_variant=variant,
				qty=qty,
				row_index=3,
				table_index=2,
				set_combination={},
			)
			for variant, qty in (("BOTTOM-LEFT-45", 12), ("BOTTOM-LEFT-50", 18))
		]

		overlaid = _overlay_source_rows(
			source_rows,
			movement_rows,
			target_doctype="Delivery Challan",
		)

		self.assertEqual([row.qty for row in overlaid], [12, 18])
		self.assertEqual({row.row_index for row in overlaid}, {3})
		self.assertEqual({row.table_index for row in overlaid}, {2})
