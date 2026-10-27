import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cutting.web_workspace import (
	MOVEMENT_DOCTYPE,
	OPERATION_DOCTYPES,
	_append_transaction_link,
	_apply_authoritative_movement_selection,
	_apply_delivery_quantities,
	_create_grouped_stock_document,
	_delivery_groups_for_entry,
	_lot_transfer_editor_dimensions,
	_movement_editor_payload,
	_movement_identity,
	_movement_totals,
	_normalize_stock_item_details,
	_plan_stock_item_groups,
	_positive_delivery_groups,
	_resolve_stock_rows,
	_stock_editor_dimensions,
	_transaction_item_groups,
	_transaction_references,
	_validate_movement_data,
	_workspace_permissions,
	generate_movement_bundles,
	get_stock_item_schema,
	get_stock_operation_editor,
)


class TestCuttingWebWorkspace(UnitTestCase):
	def test_workspace_create_actions_require_read_and_create_permissions(self):
		plan = frappe._dict(docstatus=1, version="V2", work_order="WO-1")
		context = frappe._dict(source_supplier="CUTTING", source_warehouse="CUTTING-WH")

		def has_permission(doctype, ptype):
			if doctype in (MOVEMENT_DOCTYPE, "YRP Stock Entry") and ptype == "read":
				return False
			return True

		with patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", side_effect=has_permission):
			permissions = _workspace_permissions(plan, context)

		self.assertFalse(permissions["movement"]["can_read"])
		self.assertFalse(permissions["movement"]["can_create"])
		self.assertFalse(permissions["stock_entry"]["can_read"])
		self.assertFalse(permissions["stock_entry"]["can_create"])
		self.assertTrue(permissions["stock_update"]["can_read"])
		self.assertTrue(permissions["stock_update"]["can_create"])

	def _stock_item_schema(self):
		return {
			"item": "ITEM-TEMPLATE",
			"primary_attribute": "Size",
			"dependent_attribute": "Stage",
			"dependent_attribute_details": {
				"attribute": "Stage",
				"attr_list": {
					"Cut": {
						"attributes": ["Size", "Colour"],
						"primary_attribute": "Size",
						"primary_attribute_values": ["S", "M"],
						"uom": "Pieces",
					}
				},
			},
			"attributes": ["Stage", "Colour"],
			"primary_attribute_values": ["S", "M"],
			"default_uom": "Pieces",
			"secondary_uom": "Kg",
			"attribute_values": {
				"Stage": ["Cut"],
				"Colour": ["Red", "Blue"],
				"Size": ["S", "M"],
			},
		}

	def _stock_item_details(self, *, lot="LOT-TEST", quantity=2, rate=9):
		return [
			{
				"items": [
					{
						"name": "ITEM-TEMPLATE",
						"dimensions": {"lot": lot},
						"attributes": {"Stage": "Cut", "Colour": "Red"},
						"values": {
							"S": {
								"qty": quantity,
								"rate": rate,
								"secondary_qty": 0.5,
								"secondary_uom": "SPOOFED-UOM",
							}
						},
					}
				]
			}
		]

	def test_movement_identity_is_owned_by_cutting_plan(self):
		doc = frappe._dict(
			cutting_plan="SPOOFED",
			lot="SPOOFED",
			item="SPOOFED",
			from_warehouse="SPOOFED",
			movement_from_cutting=0,
		)
		plan = frappe._dict(name="CP-TEST", lot="LOT-TEST", item="ITEM-TEST")
		context = frappe._dict(source_supplier="CUTTING-SUPPLIER")

		_movement_identity(doc, plan, context)

		self.assertEqual(doc.cutting_plan, "CP-TEST")
		self.assertEqual(doc.lot, "LOT-TEST")
		self.assertEqual(doc.item, "ITEM-TEST")
		self.assertEqual(doc.from_warehouse, "CUTTING-SUPPLIER")
		self.assertEqual(doc.movement_from_cutting, 1)

	@patch("essdee_yrp.item_matrix.normalize_item_matrix_row_indexes")
	@patch("yrp.stock.save_stock_items.group_items_for_ui")
	def test_saved_stock_entry_uses_desk_item_matrix_projection(self, group_items, normalize):
		rows = [frappe._dict(item="ITEM-RED-S", qty=3)]
		normalized = [frappe._dict(item="ITEM-RED-S", qty=3, row_index="matrix-0000")]
		groups = [{"primary_attribute": "Size", "items": [{"name": "ITEM"}]}]
		normalize.return_value = normalized
		group_items.return_value = groups
		doc = frappe._dict(doctype="YRP Stock Entry", items=rows)

		result = _transaction_item_groups(doc, "items")

		self.assertEqual(result, groups)
		normalize.assert_called_once_with(rows)
		group_items.assert_called_once_with(normalized, "YRP Stock Entry")

	@patch("essdee_yrp.item_matrix.normalize_item_matrix_row_indexes")
	@patch("yrp.stock.save_stock_items.group_items_for_ui")
	def test_saved_lot_transfer_keeps_source_and_target_as_matrix_boundaries(
		self,
		group_items,
		normalize,
	):
		rows = [frappe._dict(item="ITEM-RED-S", qty=3, from_lot="A", to_lot="B")]
		normalized = [frappe._dict(item="ITEM-RED-S", qty=3, row_index="matrix-0000")]
		groups = [{"primary_attribute": "Size", "items": [{"name": "ITEM"}]}]
		normalize.return_value = normalized
		group_items.return_value = groups
		doc = frappe._dict(doctype="SD YRP Lot Transfer", items=rows)

		result = _transaction_item_groups(doc, "items")

		self.assertEqual(result, groups)
		normalize.assert_called_once_with(
			rows,
			extra_group_fields=("from_lot", "to_lot"),
		)
		self.assertEqual(group_items.call_args.args[:2], (normalized, "SD YRP Lot Transfer"))
		self.assertIn("config", group_items.call_args.kwargs)

	def test_new_editor_does_not_generate_bundles_implicitly(self):
		plan = frappe._dict(name="CP-TEST", lot="LOT-TEST")
		context = frappe._dict(source_supplier="CUTTING-SUPPLIER")
		with patch(
			"essdee_yrp.cutting.web_workspace.get_cut_bundle_unmoved_data"
		) as generator:
			payload = _movement_editor_payload(plan, context)

		generator.assert_not_called()
		self.assertEqual(payload["movement_data"]["data"], {})
		self.assertEqual(payload["movement_data"]["collapsed_details"], [])

	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.cutting.web_workspace._plan_context")
	@patch("essdee_yrp.cutting.web_workspace._require_active_plan")
	@patch("essdee_yrp.cutting.web_workspace._get_plan")
	@patch("essdee_yrp.cutting.web_workspace.get_cut_bundle_unmoved_data")
	@patch("essdee_yrp.cutting.web_workspace._draft_movement_message", new=lambda *_: "")
	def test_generate_action_uses_server_derived_identity(
		self,
		generator,
		get_plan,
		_require_active,
		plan_context,
		_has_permission,
	):
		plan = frappe._dict(name="CP-TEST", lot="LOT-TEST")
		get_plan.return_value = plan
		plan_context.return_value = frappe._dict(source_supplier="CUTTING-SUPPLIER")
		generator.return_value = {"data": {}}

		result = generate_movement_bundles("CP-TEST", "2026-09-30", "10:30:00")

		self.assertEqual(result, {"data": {}})
		generator.assert_called_once_with(
			"CUTTING-SUPPLIER",
			"LOT-TEST",
			"2026-09-30",
			"10:30:00",
			1,
			cutting_plan="CP-TEST",
			get_collapsed=True,
		)

	def test_movement_totals_cover_exact_collapsed_and_accessory(self):
		movement = {
			"data": {
				"Green": {
					"data": [
						{"Front_moved": True, "Back_moved": True},
						{"Front_moved": False, "Back_moved": False},
					]
				}
			},
			"collapsed_details": [{"moved": 1, "move_qty": 3}, {"moved": 1, "move_qty": 0}],
			"accessory_data": [{"moved_weight": 1.25}, {"moved_weight": 0}],
		}

		self.assertEqual(
			_movement_totals(movement),
			{
				"exact_bundles": 1,
				"selected_panels": 2,
				"collapsed_rows": 1,
				"accessory_rows": 1,
			},
		)

	def test_accessory_overdraw_is_rejected_before_save(self):
		with self.assertRaisesRegex(frappe.ValidationError, "cannot exceed"):
			_validate_movement_data(
				{"accessory_data": [{"weight": 2, "moved_weight": 2.001}]}
			)

	def test_browser_cannot_spoof_bundle_quantity_or_unknown_bundle(self):
		available = {
			"panels": ["Front"],
			"data": {
				"Green": {
					"part": None,
					"data": [
						{
							"lay_no": 1,
							"bundle_no": 2,
							"size": "M",
							"shade": "A",
							"set_combination": {},
							"Front": 10,
							"Front_moved": False,
						}
					],
				}
			},
			"collapsed_details": [],
			"accessory_data": [],
		}
		selected = {
			"data": {
				"Green": {
					"data": [
						{
							"lay_no": 1,
							"bundle_no": 2,
							"size": "M",
							"shade": "A",
							"set_combination": {},
							"Front": 999,
							"Front_moved": True,
						},
						{
							"lay_no": 99,
							"bundle_no": 99,
							"size": "M",
							"shade": "A",
							"set_combination": {},
							"Front": 999,
							"Front_moved": True,
						},
					]
				}
			}
		}

		result = _apply_authoritative_movement_selection(available, selected)

		rows = result["data"]["Green"]["data"]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["Front"], 10)
		self.assertTrue(rows[0]["Front_moved"])

	@patch("essdee_yrp.cutting.web_workspace._plan_stock_rows")
	def test_stock_selection_is_revalidated_against_live_rows(self, plan_stock_rows):
		plan_stock_rows.return_value = [
			{"selection_key": "live-row", "item": "VARIANT", "bal_qty": 2}
		]
		with self.assertRaisesRegex(frappe.ValidationError, "Stock changed"):
			_resolve_stock_rows(
				frappe._dict(name="CP-TEST"),
				frappe._dict(source_warehouse="WH-TEST"),
				["client-spoofed-row"],
			)

	@patch("essdee_yrp.item_matrix.normalize_item_matrix_row_indexes")
	@patch("yrp.stock.save_stock_items.group_items_for_ui")
	def test_plan_stock_selector_uses_parent_item_attribute_matrix(self, group_items, normalize):
		rows = [
			{
				"item": "ITEM-RED-S",
				"stock_uom": "Pieces",
				"bal_qty": 4,
				"selection_key": "stock-key",
			}
		]
		normalize.return_value = [frappe._dict(rows[0], uom="Pieces")]
		group_items.return_value = [{"items": [{"name": "ITEM"}]}]

		result = _plan_stock_item_groups(rows)

		self.assertEqual(result, group_items.return_value)
		self.assertEqual(normalize.call_args.args[0][0].uom, "Pieces")
		config = group_items.call_args.kwargs["config"]
		self.assertEqual(config["qty_field"], "bal_qty")
		self.assertIn("selection_key", config["value_fields"])

	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions_for_ui")
	def test_stock_editor_locks_plan_lot_and_defaults_received_type(self, dimensions):
		dimensions.return_value = [
			{
				"fieldname": "lot",
				"label": "Lot",
				"options": "SD YRP Lot",
				"mandatory": 1,
			},
			{
				"fieldname": "received_type",
				"label": "Received Type",
				"options": "YRP Received Type",
				"mandatory": 1,
			},
		]
		result = _stock_editor_dimensions(
			frappe._dict(lot="LOT-TEST"),
			frappe._dict(default_received_type="Accepted"),
		)

		self.assertEqual(result[0]["default_value"], "LOT-TEST")
		self.assertTrue(result[0]["locked"])
		self.assertEqual(result[1]["default_value"], "Accepted")
		self.assertFalse(result[1]["locked"])

	def test_lot_transfer_editor_is_manual_and_locks_only_the_source(self):
		result = _lot_transfer_editor_dimensions(
			frappe._dict(lot="LOT-TEST"),
			frappe._dict(default_received_type="Accepted"),
		)

		self.assertEqual([row["fieldname"] for row in result], ["from_lot", "to_lot", "received_type"])
		self.assertTrue(result[0]["locked"])
		self.assertFalse(result[1].get("locked", False))
		self.assertEqual(result[1]["filters"], {"name": ["!=", "LOT-TEST"]})

	@patch("essdee_yrp.cutting.web_workspace._assert_warehouse_access")
	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions_for_ui")
	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.cutting.web_workspace._plan_context")
	@patch("essdee_yrp.cutting.web_workspace._require_active_plan")
	@patch("essdee_yrp.cutting.web_workspace._get_plan")
	def test_stock_editor_endpoint_has_serializable_context_and_compatibility_aliases(
		self,
		get_plan,
		_require_active,
		plan_context,
		_has_permission,
		dimensions,
		_warehouse_access,
	):
		get_plan.return_value = frappe._dict(name="CP-TEST", lot="LOT-TEST")
		plan_context.return_value = frappe._dict(
			cutting_plan="CP-TEST",
			lot="LOT-TEST",
			source_warehouse="CUTTING-WH",
			default_received_type="Accepted",
		)
		dimensions.return_value = [
			{
				"fieldname": "lot",
				"label": "Lot",
				"options": "SD YRP Lot",
				"mandatory": 1,
			}
		]

		result = get_stock_operation_editor("CP-TEST", "stock_entry")

		json.dumps(result)
		self.assertEqual(result["default_dimensions"], {"lot": "LOT-TEST"})
		self.assertEqual(result["locked_dimensions"], ["lot"])
		self.assertEqual(result["context"]["source_warehouse"], "CUTTING-WH")
		self.assertEqual(result["item_filters"], {
			"is_stock_item": 1, "disabled": 0, "variant_of": ["is", "not set"],
		})

	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.cutting.web_workspace._plan_context")
	@patch("essdee_yrp.cutting.web_workspace._require_active_plan")
	@patch("essdee_yrp.cutting.web_workspace._get_plan")
	def test_stock_item_schema_endpoint_returns_allowed_attribute_values(
		self,
		get_plan,
		_require_active,
		_plan_context,
		_has_permission,
		item_schema,
	):
		get_plan.return_value = frappe._dict(name="CP-TEST")
		item_schema.return_value = self._stock_item_schema()

		result = get_stock_item_schema("CP-TEST", "stock_reconciliation", "ITEM-TEMPLATE")

		self.assertEqual(result["attribute_values"]["Colour"], ["Red", "Blue"])

	@patch("essdee_yrp.cutting.web_workspace.frappe.get_doc")
	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions")
	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	def test_grouped_stock_items_are_canonicalized(
		self, item_schema, stock_dimensions, get_doc
	):
		item_schema.return_value = self._stock_item_schema()
		stock_dimensions.return_value = [
			{
				"fieldname": "lot",
				"label": "Lot",
				"dimension_doctype": "SD YRP Lot",
				"mandatory": 1,
			},
			{
				"fieldname": "received_type",
				"label": "Received Type",
				"dimension_doctype": "YRP Received Type",
				"mandatory": 1,
			},
		]
		get_doc.return_value.check_permission = MagicMock()

		result = _normalize_stock_item_details(
			frappe._dict(name="CP-TEST", lot="LOT-TEST"),
			frappe._dict(default_received_type="Accepted"),
			"stock_entry",
			self._stock_item_details(rate=999),
		)

		entry = result[0]["items"][0]
		self.assertEqual(entry["name"], "ITEM-TEMPLATE")
		self.assertEqual(entry["dimensions"], {"lot": "LOT-TEST", "received_type": "Accepted"})
		self.assertEqual(entry["primary_attribute"], "Size")
		self.assertEqual(entry["values"]["S"]["rate"], 0)
		self.assertEqual(entry["values"]["S"]["secondary_uom"], "Kg")

	@patch("essdee_yrp.cutting.web_workspace.frappe.get_doc")
	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions")
	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	def test_reconciliation_keeps_entered_rate(self, item_schema, stock_dimensions, get_doc):
		item_schema.return_value = self._stock_item_schema()
		stock_dimensions.return_value = [
			{"fieldname": "lot", "label": "Lot", "dimension_doctype": "SD YRP Lot", "mandatory": 1}
		]
		get_doc.return_value.check_permission = MagicMock()

		result = _normalize_stock_item_details(
			frappe._dict(name="CP-TEST", lot="LOT-TEST"),
			frappe._dict(default_received_type="Accepted"),
			"stock_reconciliation",
			self._stock_item_details(rate=361.91),
		)

		self.assertEqual(result[0]["items"][0]["values"]["S"]["rate"], 361.91)

	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions")
	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	def test_grouped_stock_items_reject_cross_plan_lot(self, item_schema, stock_dimensions):
		item_schema.return_value = self._stock_item_schema()
		stock_dimensions.return_value = [
			{
				"fieldname": "lot",
				"label": "Lot",
				"dimension_doctype": "SD YRP Lot",
				"mandatory": 1,
			}
		]
		with self.assertRaisesRegex(frappe.ValidationError, "controlled by Cutting Plan"):
			_normalize_stock_item_details(
				frappe._dict(name="CP-TEST", lot="LOT-TEST"),
				frappe._dict(default_received_type="Accepted"),
				"stock_entry",
				self._stock_item_details(lot="LOT-SPOOFED"),
			)

	@patch("essdee_yrp.cutting.web_workspace.frappe.get_doc")
	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions")
	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	def test_grouped_stock_items_reject_duplicate_identity(
		self, item_schema, stock_dimensions, get_doc
	):
		item_schema.return_value = self._stock_item_schema()
		stock_dimensions.return_value = [
			{
				"fieldname": "lot",
				"label": "Lot",
				"dimension_doctype": "SD YRP Lot",
				"mandatory": 1,
			}
		]
		get_doc.return_value.check_permission = MagicMock()
		item_details = self._stock_item_details()
		item_details.append(self._stock_item_details()[0])

		with self.assertRaisesRegex(frappe.ValidationError, "Duplicate Item"):
			_normalize_stock_item_details(
				frappe._dict(name="CP-TEST", lot="LOT-TEST"),
				frappe._dict(default_received_type="Accepted"),
				"stock_reconciliation",
				item_details,
			)

	@patch("essdee_yrp.cutting.web_workspace.frappe.get_doc")
	@patch("essdee_yrp.cutting.web_workspace.get_stock_dimensions", return_value=[])
	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	def test_manual_lot_transfer_owns_source_lot_and_warehouse(
		self, item_schema, _stock_dimensions, get_doc
	):
		item_schema.return_value = self._stock_item_schema()
		get_doc.return_value.check_permission = MagicMock()
		details = self._stock_item_details()
		details[0]["items"][0]["dimensions"] = {
			"from_lot": "LOT-TEST",
			"to_lot": "LOT-TARGET",
			"received_type": "Accepted",
		}

		result = _normalize_stock_item_details(
			frappe._dict(name="CP-TEST", lot="LOT-TEST"),
			frappe._dict(source_warehouse="CUTTING-WH", default_received_type="Accepted"),
			"lot_transfer",
			details,
		)

		entry = result[0]["items"][0]
		self.assertEqual(entry["from_lot"], "LOT-TEST")
		self.assertEqual(entry["to_lot"], "LOT-TARGET")
		self.assertEqual(entry["warehouse"], "CUTTING-WH")
		self.assertEqual(entry["received_type"], "Accepted")

	@patch("essdee_yrp.cutting.web_workspace._normalize_stock_item_details")
	@patch("essdee_yrp.cutting.web_workspace._assert_warehouse_access")
	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.cutting.web_workspace.frappe.new_doc")
	def test_grouped_stock_entry_owns_source_and_uses_item_details(
		self, new_doc, _has_permission, _warehouse_access, normalize
	):
		doc = frappe._dict(doctype="YRP Stock Entry")
		doc.insert = MagicMock()
		new_doc.return_value = doc
		normalize.return_value = [{"items": [{"name": "ITEM-TEMPLATE"}]}]

		returned = _create_grouped_stock_document(
			frappe._dict(name="CP-TEST"),
			frappe._dict(source_supplier="CUTTING", source_warehouse="CUTTING-WH"),
			"stock_entry",
			{
				"purpose": "Material Issue",
				"from_warehouse": "SPOOFED-WH",
				"item_details": self._stock_item_details(),
			},
		)

		self.assertIs(returned, doc)
		self.assertEqual(doc.from_warehouse, "CUTTING-WH")
		self.assertEqual(json.loads(doc.item_details), normalize.return_value)
		doc.insert.assert_called_once_with()

	@patch("yrp.stock.save_stock_items.ungroup_items_from_ui")
	@patch("essdee_yrp.cutting.web_workspace._normalize_stock_item_details")
	@patch("essdee_yrp.cutting.web_workspace._assert_warehouse_access")
	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.cutting.web_workspace.frappe.new_doc")
	def test_reconciliation_retains_zero_primary_attribute_cells(
		self,
		new_doc,
		_has_permission,
		_warehouse_access,
		normalize,
		ungroup,
	):
		doc = frappe._dict(doctype="YRP Stock Reconciliation", items=[])
		doc.insert = MagicMock()
		doc.append = MagicMock(side_effect=lambda _field, row: doc["items"].append(row))
		new_doc.return_value = doc
		normalize.return_value = [{"items": [{"name": "ITEM-TEMPLATE"}]}]
		ungroup.return_value = [{"item": "ITEM-S", "qty": 0}]

		_create_grouped_stock_document(
			frappe._dict(name="CP-TEST"),
			frappe._dict(source_supplier="CUTTING", source_warehouse="CUTTING-WH"),
			"stock_reconciliation",
			{"item_details": self._stock_item_details(quantity=0)},
		)

		ungroup.assert_called_once_with(
			normalize.return_value,
			"YRP Stock Reconciliation",
			keep_zero=True,
		)
		self.assertEqual(
			doc["items"], [{"item": "ITEM-S", "qty": 0, "warehouse": "CUTTING-WH"}]
		)

	@patch("essdee_yrp.cutting.web_workspace._normalize_stock_item_details")
	@patch("essdee_yrp.cutting.web_workspace._assert_warehouse_access")
	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.cutting.web_workspace.frappe.new_doc")
	def test_manual_stock_update_accepts_add_or_reduce_and_owns_location(
		self, new_doc, _has_permission, _warehouse_access, normalize
	):
		doc = frappe._dict(doctype="YRP Stock Update")
		doc.insert = MagicMock()
		new_doc.return_value = doc
		normalize.return_value = [{"items": [{"name": "ITEM-TEMPLATE"}]}]

		_create_grouped_stock_document(
			frappe._dict(name="CP-TEST"),
			frappe._dict(source_supplier="CUTTING", source_warehouse="CUTTING-WH"),
			"stock_update",
			{"update_type": "Add", "item_details": self._stock_item_details()},
		)

		self.assertEqual(doc.update_type, "Add")
		self.assertEqual(doc.warehouse, "CUTTING-WH")
		self.assertEqual(doc.supplier, "CUTTING")
		self.assertEqual(json.loads(doc.item_details), normalize.return_value)

	def test_work_order_delivery_omits_zero_cells_rows_and_empty_groups(self):
		groups = [
			{"items": [
				{"name": "SHIRT", "values": {"S": {"qty": 0}, "M": {"qty": 2, "ref_docname": "ROW-M"}}},
				{"name": "EMPTY", "values": {"default": {"qty": 0}}},
			]},
			{"items": [{"name": "EMPTY-GROUP", "values": {"default": {"qty": 0}}}]},
		]
		self.assertEqual(_positive_delivery_groups(groups), [{"items": [
			{"name": "SHIRT", "values": {"M": {"qty": 2, "ref_docname": "ROW-M"}}},
		]}])
		self.assertIn("S", groups[0]["items"][0]["values"])

	def test_work_order_delivery_editor_starts_at_zero_and_applies_only_known_rows(self):
		groups = [
			{
				"items": [
					{
						"values": {
							"S": {"qty": 4, "delivered_quantity": 4, "pending_quantity": 4, "ref_docname": "ROW-S"},
							"M": {"qty": 2, "delivered_quantity": 2, "pending_quantity": 2, "ref_docname": "ROW-M"},
						}
					}
				]
			}
		]
		entry_groups = _delivery_groups_for_entry(groups)
		self.assertEqual(entry_groups[0]["items"][0]["values"]["S"]["qty"], 0)
		self.assertEqual(entry_groups[0]["items"][0]["values"]["S"]["pending_quantity"], 4)

		known = set()
		used = set()
		_apply_delivery_quantities(entry_groups, {"ROW-M": 1.5}, known, used)
		values = entry_groups[0]["items"][0]["values"]
		self.assertEqual(values["S"]["qty"], 0)
		self.assertEqual(values["M"]["qty"], 1.5)
		self.assertEqual(values["M"]["delivered_quantity"], 1.5)
		self.assertEqual(known, {"ROW-S", "ROW-M"})
		self.assertEqual(used, {"ROW-M"})

	@patch("essdee_yrp.cutting.web_workspace.frappe.db.get_value")
	@patch("essdee_yrp.cutting.web_workspace.frappe.db.sql")
	def test_transaction_relation_append_is_idempotent(self, _sql, get_value):
		relation = frappe._dict(against="YRP Stock Entry", against_id="STE-TEST")
		plan = frappe._dict(
			name="CP-TEST",
			doctype="SD YRP Cutting Plan",
			stock_transfers=[relation],
		)
		plan.reload = lambda: None
		doc = frappe._dict(doctype="YRP Stock Entry", name="STE-TEST")

		returned = _append_transaction_link(plan, doc)

		self.assertIs(returned, relation)
		get_value.assert_not_called()

	@patch("essdee_yrp.cutting.web_workspace.frappe.get_list")
	@patch("essdee_yrp.cutting.web_workspace.frappe.has_permission", return_value=True)
	def test_existing_cpm_native_transaction_is_merged_without_duplicates(
		self, _has_permission, get_list
	):
		plan = frappe._dict(
			name="CP-TEST",
			stock_transfers=[
				frappe._dict(against="YRP Stock Entry", against_id="STE-REGISTERED")
			],
		)
		get_list.return_value = [
			frappe._dict(against="YRP Stock Entry", against_id="STE-REGISTERED"),
			frappe._dict(against="YRP Delivery Challan", against_id="DC-LEGACY"),
		]

		self.assertEqual(
			_transaction_references(plan),
			[
				("YRP Stock Entry", "STE-REGISTERED"),
				("YRP Delivery Challan", "DC-LEGACY"),
			],
		)

	def test_relation_allowlist_covers_all_workspace_tabs_and_legacy_grn(self):
		self.assertEqual(OPERATION_DOCTYPES["stock_entry"], "YRP Stock Entry")
		self.assertEqual(OPERATION_DOCTYPES["stock_reconciliation"], "YRP Stock Reconciliation")
		self.assertEqual(OPERATION_DOCTYPES["stock_update"], "YRP Stock Update")
		self.assertEqual(OPERATION_DOCTYPES["lot_transfer"], "SD YRP Lot Transfer")
		self.assertEqual(OPERATION_DOCTYPES["delivery_challan"], "YRP Delivery Challan")
		self.assertEqual(OPERATION_DOCTYPES["goods_received_note"], "YRP Goods Received Note")
		self.assertEqual(MOVEMENT_DOCTYPE, "SD YRP Cut Panel Movement")
