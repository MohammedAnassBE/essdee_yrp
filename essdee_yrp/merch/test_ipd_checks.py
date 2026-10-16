import copy
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import strip_html

from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_test_support import SAMPLES, rolled_back, unapprove

GARMENT = SAMPLES["standard"]
SET_ITEM = SAMPLES["set_item"]


def wire(value):
	return json.loads(json.dumps(value, default=str))


def editor_values(name):
	return wire(workspace.get_ipd_editor(name)["values"])


def save_error(name, values):
	with rolled_back("check_vs_save"):
		try:
			workspace.save_ipd(values, name, str(frappe.db.get_value(DOCTYPE, name, "modified")))
		except frappe.ValidationError as error:
			return strip_html(str(error)).strip()
	return None


def defects(values):
	stitching = copy.deepcopy(values["stiching_item_details"])
	stitching[0]["quantity"] = 0
	bom = copy.deepcopy(values["item_bom"])
	plain = next(row for row in bom if not row["based_on_attribute_mapping"])
	duplicate = {key: plain[key] for key in ("item", "qty_of_product", "qty_of_bom_item", "process_name")}
	duplicate["dependent_attribute_value"] = plain["dependent_attribute_value"]
	packing = copy.deepcopy(values["packing_attribute_details"])
	packing[0]["quantity"] = 1
	return {
		"stitching quantity": {"stiching_item_details": stitching},
		"duplicate BOM item": {"item_bom": [*bom, {**duplicate, "based_on_attribute_mapping": 0}]},
		"packing sum": {"auto_calculate": 0, "packing_attribute_details": packing, "packing_combo": 5},
		"over-length": {"tech_pack_version": "x" * 200},
		"bad select": {"stiching_item_details": [{**stitching[1], "category": "Bogus"}]},
	}


class TestIpdChecks(IntegrationTestCase):
	"""check_ipd runs the save rules on a draft, lists every problem and writes nothing."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		unapprove(GARMENT)
		unapprove(SET_ITEM)

	def test_clean_ipd_passes(self):
		result = workspace.check_ipd(GARMENT)
		self.assertEqual(result["state"], "draft")
		self.assertEqual(result["problems"], [])
		self.assertIn("validate_packing_fields", {row["rule"] for row in result["passed"]})

	def test_server_checks_match_save(self):
		values = editor_values(GARMENT)
		for label, patch_values in defects(values).items():
			with self.subTest(defect=label):
				expected = save_error(GARMENT, patch_values)
				self.assertTrue(expected, label)
				problems = workspace.check_ipd(GARMENT, patch_values)["problems"]
				self.assertTrue(problems, label)
				self.assertEqual(problems[0]["message"], expected)

	def test_all_problems_are_listed(self):
		cases = defects(editor_values(GARMENT))
		combined = {**cases["stitching quantity"], **cases["over-length"], **cases["duplicate BOM item"]}
		result = workspace.check_ipd(GARMENT, combined)
		rules = [row["rule"] for row in result["problems"]]
		self.assertEqual(rules, ["validate_duplicate_bom_items", "validate_stiching_fields", "length"])
		stitching = next(row for row in result["problems"] if row["rule"] == "validate_stiching_fields")
		self.assertEqual((stitching["section"], stitching["column"]), ("stitching", "quantity"))
		self.assertEqual(
			stitching["row_key"], combined["stiching_item_details"][0]["stiching_attribute_value"]
		)
		self.assertEqual(result["section_counts"], {"accessories": 1, "stitching": 1, "item": 1})
		duplicate = next(row for row in result["problems"] if row["rule"] == "validate_duplicate_bom_items")
		self.assertEqual(
			(duplicate["row_key"], duplicate["column"]), (f"new:{len(combined['item_bom']) - 1}", "item")
		)

	def test_client_rules_have_locations(self):
		values = editor_values(SET_ITEM)
		combination = values["stiching_item_detail"]
		column = combination["attributes"][1]
		combination["values"][0]["val"][column] = None
		result = workspace.check_ipd(SET_ITEM, {"stiching_item_detail": combination})
		problem = next(row for row in result["problems"] if row["rule"] == "stitching_combination_cells")
		self.assertEqual(problem["message"], "Fill all the combinations")
		self.assertEqual(
			(problem["row_key"], problem["column"]), (combination["values"][0]["major_attribute"], column)
		)

		cloths = copy.deepcopy(values["cutting_cloths_json"])
		cloths["items"][0]["Cloth"] = "NOT A CLOTH"
		problems = workspace.check_ipd(SET_ITEM, {"cutting_cloths_json": cloths})["problems"]
		self.assertEqual(problems[0]["rule"], "cloth_name")
		self.assertEqual(problems[0]["column"], "Cloth")

	def test_mandatory_depends_on_is_enforced(self):
		problems = workspace.check_ipd(GARMENT, {"packing_attribute": None})["problems"]
		self.assertIn(
			("mandatory_depends_on", "packing_attribute"), {(row["rule"], row["field"]) for row in problems}
		)

	def test_checks_write_nothing(self):
		values = editor_values(GARMENT)
		rows = [
			*values["stiching_item_details"],
			{"stiching_attribute_value": "Sleeve", "quantity": 1, "category": "Body"},
		]
		counts = {
			doctype: frappe.db.count(doctype)
			for doctype in ("YRP Item Attribute Value", "YRP Item Item Attribute Mapping", DOCTYPE)
		}
		stored = frappe.db.get_value(DOCTYPE, GARMENT, "modified")
		messages = len(frappe.get_message_log())
		frappe.flags.delete_bom_mapping = ["keep-me"]
		with patch.object(frappe.db, "commit", side_effect=AssertionError("checks must not commit")):
			workspace.check_ipd(GARMENT, {"stiching_item_details": rows, "description": "QA"})
		self.assertEqual({doctype: frappe.db.count(doctype) for doctype in counts}, counts)
		self.assertEqual(frappe.db.get_value(DOCTYPE, GARMENT, "modified"), stored)
		self.assertEqual(len(frappe.get_message_log()), messages)
		self.assertEqual(frappe.flags.delete_bom_mapping, ["keep-me"])
		for cache in ("attribute_link_names", "attribute_link_values", "attribute_link_context"):
			self.assertFalse(hasattr(frappe.local, cache), cache)

	def test_approved_ipd_runs_no_rules(self):
		result = workspace.check_ipd(SAMPLES["panel_wise"])
		self.assertEqual(
			result, {"state": "approved", "problems": [], "warnings": [], "passed": [], "section_counts": {}}
		)

	def test_new_ipd_checks_only_the_item(self):
		self.assertEqual(workspace.check_ipd(None, {})["problems"][0]["field"], "item")
		item = frappe.db.get_value(DOCTYPE, GARMENT, "item")
		result = workspace.check_ipd(None, {"item": item})
		self.assertEqual((result["state"], result["problems"]), ("new", []))

	def test_cloth_ipd_runs_cloth_rules_once(self):
		name = SAMPLES["cloth"]
		unapprove(name)
		values = editor_values(name)
		values["yarn_ratio_details"][0]["ratio"] = 10
		problems = workspace.check_ipd(name, {"yarn_ratio_details": values["yarn_ratio_details"]})["problems"]
		rules = [row["rule"] for row in problems]
		self.assertEqual(rules.count("validate_cloth_ipd"), 1)
		self.assertNotIn("validate_packing_fields", rules)
		self.assertEqual(
			problems[0]["message"], save_error(name, {"yarn_ratio_details": values["yarn_ratio_details"]})
		)

	def test_cloth_problems_point_at_their_rows(self):
		name = SAMPLES["cloth"]
		unapprove(name)
		values = editor_values(name)
		compacting = [{"colour": None, "input_dia": "14 Dia", "compacting_dia": None, "notes": None}]
		problems = workspace.check_ipd(name, {"compacting_reference_details": compacting})["problems"]
		self.assertTrue(problems)
		for problem in problems:
			self.assertEqual(
				(problem["section"], problem["field"], problem["row_key"], problem["column"]),
				("compacting", "compacting_reference_details", "new:0", "compacting_dia"),
			)
		route = values["fabric_routes"][0]
		route["use_dyed_yarn"] = 1
		problem = workspace.check_ipd(name, {"fabric_routes": [route]})["problems"][0]
		self.assertEqual(
			(problem["section"], problem["field"], problem["row_key"]),
			("fabric_routes", "fabric_routes", route["name"]),
		)

	def test_cloth_context_names_the_settings_attributes(self):
		cloth = workspace.get_ipd_workspace(SAMPLES["cloth"])["context"]["cloth"]
		self.assertTrue(cloth["colour_attribute"] and cloth["dia_attribute"])
		self.assertIn("14 Dia", cloth["dia_values"])
		self.assertEqual(cloth["mapping_roles"], ["Change", "Introduce", "Pin", "Consume"])
		self.assertIsNone(workspace.get_ipd_workspace(GARMENT)["context"]["cloth"])


class TestDeskClientRules(IntegrationTestCase):
	"""Each Desk widget rule (W/*.vue get_data, grid reqd toggles) is reported where Desk throws."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		unapprove(SET_ITEM)
		unapprove(SAMPLES["panel_grouped"])

	def rules_for(self, name, patch_values):
		return {(row["rule"], row["message"]) for row in workspace.check_ipd(name, patch_values)["problems"]}

	def test_widget_rules(self):
		values = editor_values(SET_ITEM)
		panels = [row["stiching_attribute_value"] for row in values["stiching_item_details"]]
		fill = "Fill all the combinations"

		def edited(key, change):
			data = copy.deepcopy(values[key])
			change(data)
			return {key: data}

		cases = [
			(
				edited("cutting_items_json", lambda data: data["items"][0].update(Dia=None)),
				("cutting_cells", fill),
			),
			(
				edited("cloth_accessory_json", lambda data: data["items"][0].update(Weight=None)),
				("cloth_accessory_cells", fill),
			),
			(
				edited(
					"stiching_accessory_json", lambda data: data["items"][0].update(cloth_type="NOT A CLOTH")
				),
				("stitching_accessory_cloth", "Some Cloths not in the Accessory Select List"),
			),
			(
				edited("stiching_accessory_json", lambda data: data["items"][0].update(accessory_colour="")),
				("stitching_accessory_cells", fill),
			),
			(
				{"marker_groups": [[panels[0]], [panels[0]]]},
				("bundle_groups", f"Panel {panels[0]} is grouped multiple times"),
			),
			({"marker_groups": [[panels[0]]]}, ("bundle_groups", "Select All the Panels")),
			(
				edited("stiching_item_details", lambda rows: rows[0].update(set_item_attribute_value=None)),
				("stitching_set_part", f"Stitching panel {panels[0]}: choose its set part."),
			),
			(
				edited("item_bom", lambda rows: rows[0].update(dependent_attribute_value=None)),
				("bom_dependent_value", "BOM row 1: Dependent Attribute Value is required."),
			),
		]
		for patch_values, expected in cases:
			with self.subTest(rule=expected[0]):
				self.assertIn(expected, self.rules_for(SET_ITEM, patch_values))

	def test_required_gsm_may_stay_blank(self):
		values = editor_values(SET_ITEM)
		data = copy.deepcopy(values["cutting_items_json"])
		data["attributes"].append("Required GSM")
		for item in data["items"]:
			item["Required GSM"] = None
		self.assertNotIn(
			"cutting_cells",
			{rule for rule, _message in self.rules_for(SET_ITEM, {"cutting_items_json": data})},
		)

	def test_panel_weights_must_be_positive(self):
		name = SAMPLES["panel_grouped"]
		matrix = editor_values(name)["panel_wise_consumption_matrix_json"]
		cell = next(iter(matrix["panels"][0]["rows"][0]["values"].values()))
		cell["weight"] = -1
		rules = {
			rule for rule, _message in self.rules_for(name, {"panel_wise_consumption_matrix_json": matrix})
		}
		self.assertIn("panel_weights", rules)


class TestProcessStage(IntegrationTestCase):
	"""Process rows edit one stage; it is written to both in_stage and out_stage."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		unapprove(GARMENT)

	def save(self, rows):
		modified = str(frappe.db.get_value(DOCTYPE, GARMENT, "modified"))
		return workspace.save_ipd({"ipd_processes": rows}, GARMENT, modified)["values"]["ipd_processes"]

	def test_single_stage_writes_both(self):
		with rolled_back("process_stage_write"):
			rows = copy.deepcopy(editor_values(GARMENT)["ipd_processes"])
			ironing = next(index for index, row in enumerate(rows) if row["process_name"] == "Ironing")
			rows[ironing]["in_stage"] = "Pack"
			rows.append({"process_name": "Washing", "in_stage": "Cut"})
			saved = {row["process_name"]: (row["in_stage"], row["out_stage"]) for row in self.save(rows)}
			self.assertEqual(saved["Ironing"], ("Pack", "Pack"))
			self.assertEqual(saved["Washing"], ("Cut", "Cut"))
			stored = frappe.get_doc(DOCTYPE, GARMENT).ipd_processes
			self.assertTrue(all(row.in_stage == row.out_stage for row in stored))

	def test_legacy_mismatch_is_flagged_not_rewritten(self):
		with rolled_back("process_stage_legacy"):
			doc = frappe.get_doc(DOCTYPE, GARMENT)
			row = next(row for row in doc.ipd_processes if row.process_name == "Ironing")
			other = next(other for other in doc.ipd_processes if other.in_stage != row.in_stage)
			frappe.db.set_value(row.doctype, row.name, "out_stage", other.in_stage, update_modified=False)
			result = workspace.check_ipd(GARMENT)
			self.assertNotIn("process_stages", {entry["rule"] for entry in result["problems"]})
			problem = next(entry for entry in result["warnings"] if entry["rule"] == "process_stages")
			self.assertEqual(
				(problem["section"], problem["row_key"], problem["column"]),
				("processes", row.name, "in_stage"),
			)
			rows = copy.deepcopy(editor_values(GARMENT)["ipd_processes"])
			rows.reverse()
			saved = {entry["process_name"]: entry for entry in self.save(rows)}
			self.assertNotEqual(saved["Ironing"]["in_stage"], saved["Ironing"]["out_stage"])
