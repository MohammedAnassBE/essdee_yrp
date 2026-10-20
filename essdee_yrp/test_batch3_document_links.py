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


class TestBatch3DocumentLinks(TestCase):
	def test_common_facts_resolve_dynamic_target_without_displaying_controller(self):
		field = SimpleNamespace(
			fieldname="against_id",
			label="Source",
			fieldtype="Dynamic Link",
			options="against",
			hidden=False,
			reqd=False,
			read_only=False,
			depends_on="",
			mandatory_depends_on="",
			read_only_depends_on="",
			get=lambda key: False,
		)
		values = {"against": "YRP Work Order", "against_id": "WO/1"}
		doc = SimpleNamespace(doctype="Test", docstatus=1, get=values.get)
		module = functions(
			"fabric_store/documents/common.py",
			{"get_effective_fields"},
			Iterable=list,
			_document_meta=lambda doc: SimpleNamespace(get_field=lambda name: field),
			_permitted_fields=lambda *args: ["against_id"],
			get_allow_on_submit_fields=lambda *args: [],
			EFFECTIVE_FIELD_TYPES={"Dynamic Link"},
			cint=int,
		)
		facts = module.get_effective_fields(doc, ["against_id"])
		self.assertEqual(facts[0]["fieldtype"], "Dynamic Link")
		self.assertEqual(facts[0]["options"], "against")
		self.assertEqual(facts[0]["link_doctype"], "YRP Work Order")
		self.assertEqual(facts[0]["value"], "WO/1")

	def test_purchase_order_allowlist_includes_default_lot(self):
		tree = ast.parse((ROOT / "fabric_store/documents/purchase_order.py").read_text())
		assignment = next(
			node
			for node in tree.body
			if isinstance(node, ast.Assign)
			and any(
				isinstance(target, ast.Name) and target.id == "PURCHASE_ORDER_FIELDS"
				for target in node.targets
			)
		)
		self.assertIn("default_lot", ast.literal_eval(assignment.value))

	def test_production_order_fields_use_meta_and_keep_raw_names(self):
		meta = {
			"production_detail": SimpleNamespace(fieldtype="Link", options="YRP Item Production Detail"),
			"production_term": SimpleNamespace(fieldtype="Link", options="YRP Production Term"),
			"submitted_by": SimpleNamespace(fieldtype="Link", options="User"),
			"transferred_to_ppo": SimpleNamespace(fieldtype="Link", options="YRP Production Order"),
			"comments": SimpleNamespace(fieldtype="Small Text", options=None),
		}
		record = dict(
			production_detail="IPD/1",
			production_term="TERM/1",
			submitted_by="USER/1",
			transferred_to_ppo="PPO/1",
			comments="Plain",
		)
		module = functions(
			"sales/web_workspace.py",
			{"_production_order_fields"},
			RECORD_FIELDS=list(record),
			FIELD_LABELS={},
		)
		facts = module._production_order_fields(
			SimpleNamespace(meta=SimpleNamespace(get_field=meta.get)), record
		)
		self.assertEqual(
			[fact["options"] for fact in facts[:4]], [field.options for field in list(meta.values())[:4]]
		)
		self.assertEqual(facts[2]["value"], "USER/1")
		self.assertEqual(facts[-1]["fieldtype"], "Small Text")
		self.assertIn("_production_order_fields(doc, record)", (ROOT / "sales/web_workspace.py").read_text())

	def test_invoice_grns_include_dynamic_controller(self):
		get_list = Mock(return_value=[])
		module = functions(
			"accounts/purchase_invoice_workspace.py",
			{"serialize_grns"},
			frappe=SimpleNamespace(get_list=get_list),
		)
		module.serialize_grns(SimpleNamespace(get=lambda key: [{"grn": "GRN/1"}]))
		self.assertIn("against", get_list.call_args.kwargs["fields"])

	def test_cutting_order_detail_payload_uses_actual_field_metadata(self):
		meta = {
			"cutting_order_detail": SimpleNamespace(fieldtype="Link", options="SD YRP Cutting Order Detail"),
			"item": SimpleNamespace(fieldtype="Data", options=None),
		}
		module = functions(
			"cutting/order_workspace.py", {"_overview_detail"}, _doc_value=lambda doc, key: key
		)
		doc = SimpleNamespace(meta=SimpleNamespace(get_field=meta.get))
		self.assertEqual(
			module._overview_detail(doc, "cutting_order_detail", "Detail")["options"],
			"SD YRP Cutting Order Detail",
		)
		self.assertEqual(module._overview_detail(doc, "item", "Item")["fieldtype"], "Data")

	def test_invoice_masked_links_keep_display_without_inventing_a_record_name(self):
		values = {"supplier": "XXXXXXXX", "billing_supplier": "XXXXXXXX"}
		doc = SimpleNamespace(
			doctype="YRP Purchase Invoice",
			name="PI/1",
			docstatus=1,
			get=values.get,
			flags=SimpleNamespace(masked_fieldnames={"supplier", "billing_supplier"}),
			meta=SimpleNamespace(
				get_field=lambda key: SimpleNamespace(label="Supplier", fieldtype="Link", options="Supplier")
			),
		)
		module = functions(
			"accounts/purchase_invoice_workspace.py",
			{"_record", "_detail_field", "_invoice_link_name"},
			cint=int,
			_=lambda value: value,
		)
		self.assertEqual(module._record(doc)["supplier"], "XXXXXXXX")
		self.assertEqual(module._record(doc)["supplier_link_name"], "")
		self.assertEqual(module._detail_field(doc, "billing_supplier")["link_name"], "")
