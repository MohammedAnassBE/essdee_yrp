import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

ROOT = Path(__file__).parent


def functions(path, names, **namespace):
	tree = ast.parse((ROOT / path).read_text())
	tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
	for node in tree.body:
		node.decorator_list = []
	exec(compile(tree, str(path), "exec"), namespace)
	return SimpleNamespace(**namespace)


def field(name, fieldtype="Link", options="Item"):
	return SimpleNamespace(
		fieldname=name,
		label=name.title(),
		fieldtype=fieldtype,
		options=options,
		hidden=False,
		read_only=False,
	)


class TestBatch2DocumentLinks(TestCase):
	def test_work_order_fact_targets_preserve_metadata_and_resolve_dynamic_links(self):
		fields = [
			field("process_name", options="YRP Process"),
			field("against_id", "Dynamic Link", "against"),
		]
		values = {"process_name": "Stitching", "against": "Item", "against_id": "A/B"}
		doc = SimpleNamespace(
			meta=SimpleNamespace(get_field=lambda name: next(f for f in fields if f.fieldname == name)),
			get=values.get,
		)
		module = functions(
			"fabric_store/web_workspace.py",
			{"_work_order_details", "_detail_link_target"},
			WORK_ORDER_DETAIL_FIELDS=["process_name", "against_id"],
		)
		facts = module._work_order_details(doc)
		self.assertEqual((facts[0]["fieldtype"], facts[0]["options"]), ("Link", "YRP Process"))
		self.assertEqual(facts[1]["link_doctype"], "Item")
		self.assertEqual(facts[1]["value"], "A/B")

	def test_document_facts_keep_dynamic_target_when_controller_is_not_displayed(self):
		fields = [field("against_id", "Dynamic Link", "against"), field("supplier", options="Supplier")]
		values = {"against": "Item", "against_id": "A/B", "supplier": "SUP/1"}
		doc = SimpleNamespace(
			doctype="Test", docstatus=1, meta=SimpleNamespace(fields=fields), get=values.get
		)
		module = functions(
			"fabric_store/web_workspace.py",
			{"_document_details", "_detail_link_target"},
			get_permitted_fields=lambda *args, **kwargs: [f.fieldname for f in fields],
			DETAIL_FIELD_TYPES={"Link", "Dynamic Link"},
		)
		facts = module._document_details(doc)
		self.assertEqual(facts[0]["link_doctype"], "Item")
		self.assertEqual(facts[1]["options"], "Supplier")

	def test_item_price_overview_retains_raw_approver(self):
		fields = [
			{
				"fieldname": "approved_by",
				"fieldtype": "Link",
				"options": "User",
				"value": "user@example.test",
			},
			{"fieldname": "item_name", "fieldtype": "Link", "options": "Item", "value": "A/B"},
		]
		module = functions(
			"purchase/item_price_workspace.py",
			{"_overview_fields"},
			get_effective_fields=Mock(return_value=fields),
			VIEW_FIELDS=["approved_by", "item_name"],
		)
		facts = module._overview_fields(SimpleNamespace(get=lambda key: "user@example.test"))
		self.assertEqual(facts[0]["link_name"], "user@example.test")
		self.assertEqual(facts[0]["options"], "User")
		self.assertEqual(facts[1]["value"], "A/B")

	def test_lot_derived_stages_keep_raw_names_separate_from_visible_values(self):
		values = {"pack_in_stage": "IAV/1", "pack_out_stage": "IAV/2", "uom": "Nos"}
		module = functions(
			"purchase/lot_editor.py",
			{"derived_values"},
			DERIVED_FIELDS=list(values),
			attribute_value=lambda value: {"IAV/1": "Cut", "IAV/2": "Packed"}.get(value),
		)
		facts = module.derived_values(SimpleNamespace(get=values.get))
		self.assertEqual(facts["pack_in_stage"], "Cut")
		self.assertEqual(facts["pack_in_stage_name"], "IAV/1")
		self.assertEqual(facts["pack_out_stage_name"], "IAV/2")
		self.assertEqual(facts["uom"], "Nos")

	def test_ipd_attribute_links_keep_top_level_and_child_raw_names(self):
		stage = field("pack_in_stage", options="YRP Item Attribute Value")
		process_stage = field("in_stage", options="YRP Item Attribute Value")
		meta = {
			"IPD": SimpleNamespace(
				fields=[stage],
				get_table_fields=lambda: [SimpleNamespace(fieldname="ipd_processes", options="Process Row")],
			),
			"Process Row": SimpleNamespace(fields=[process_stage]),
		}
		frappe = SimpleNamespace(get_meta=meta.get)
		row = SimpleNamespace(name="ROW/1", get={"in_stage": "IAV/1"}.get)
		doc = SimpleNamespace(get={"pack_in_stage": "IAV/1", "ipd_processes": [row]}.get)
		module = functions(
			"merch/ipd/payload.py",
			{"link_names", "attribute_link_fields"},
			frappe=frappe,
			registry=SimpleNamespace(DOCTYPE="IPD", ATTRIBUTE_VALUE="YRP Item Attribute Value"),
			attribute_value=lambda value: "Cut" if value == "IAV/1" else value,
		)
		names = module.link_names(doc)
		self.assertEqual(names["fields"]["pack_in_stage"], {"name": "IAV/1", "value": "Cut"})
		self.assertEqual(
			names["tables"]["ipd_processes"]["ROW/1"]["in_stage"], {"name": "IAV/1", "value": "Cut"}
		)

	def test_changed_lot_ipd_context_also_carries_raw_stage_names(self):
		frappe = SimpleNamespace(
			get_message_log=lambda: [],
			db=SimpleNamespace(
				get_value=Mock(return_value={"pack_in_stage": "IAV/1", "pack_out_stage": "IAV/2"})
			),
		)
		module = functions(
			"purchase/lot_editor.py",
			{"get_lot_production_detail_context"},
			frappe=frappe,
			check_context_permission=lambda: None,
			get_isfinal_uom=lambda *args, **kwargs: {
				"uom": "Nos",
				"pack_in_stage": "Cut",
				"pack_out_stage": "Packed",
			},
			get_item_details=lambda **kwargs: None,
			IPD_DERIVED={"uom": "uom", "pack_in_stage": "pack_in_stage", "pack_out_stage": "pack_out_stage"},
		)
		facts = module.get_lot_production_detail_context("IPD/1", "Item")["derived"]
		self.assertEqual(facts["pack_in_stage_name"], "IAV/1")
		self.assertEqual(facts["pack_in_stage"], "Cut")
