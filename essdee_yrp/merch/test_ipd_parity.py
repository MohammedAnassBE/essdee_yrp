import copy
import json

import frappe
from frappe.tests import IntegrationTestCase
from yrp.attribute_links import value as attribute_value

from essdee_yrp.ipd_ui import duplicate_ipd, get_complete_item_details
from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.fields import DOCTYPE, writable_keys
from essdee_yrp.merch.ipd_test_support import (
	SAMPLES,
	desk_equivalent_save,
	desk_validate_payload,
	payload_patch,
	rolled_back,
	snapshot,
	unapprove,
)

STRIDE_SAMPLES = 12


def wire(value):
	return json.loads(json.dumps(value, default=str))


def editor(name):
	return wire(workspace.get_ipd_editor(name))


def web_save(name, patch):
	payload = editor(name)
	return workspace.save_ipd(wire(patch(payload["values"])), name, payload["record"]["modified"])


def outcome(save):
	try:
		save()
	except frappe.ValidationError as error:
		return ("error", frappe.utils.strip_html(str(error)))
	except Exception as error:
		return ("crash", type(error).__name__)
	return ("saved", None)


class TestIpdParity(IntegrationTestCase):
	"""Web saves store exactly what the Desk form stores for the same document and edit."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for name in SAMPLES.values():
			unapprove(name)

	def assert_edit_parity(self, name, desk_edit, web_patch):
		with rolled_back("desk_edit"):
			doc = frappe.get_doc(DOCTYPE, name)
			desk_validate_payload(doc)
			desk_edit(doc)
			doc.save()
			desk = snapshot(name)
		with rolled_back("web_edit"):
			web_save(name, web_patch)
			web = snapshot(name)
		self.assertEqual(desk, web)
		return web

	def test_open_has_no_side_effects(self):
		for name in SAMPLES.values():
			before = snapshot(name)
			workspace.get_ipd_workspace(name)
			workspace.get_ipd_editor(name)
			workspace.check_ipd(name)
			self.assertEqual(snapshot(name), before, name)

	def test_noop_save_equals_desk_save(self):
		for name in [*SAMPLES.values(), *stride_samples()]:
			unapprove(name)
			with self.subTest(name=name):
				with rolled_back("desk_noop"):
					desk_result = outcome(lambda name=name: desk_equivalent_save(name))
					desk = snapshot(name)
				with rolled_back("web_noop"):
					web_result = outcome(lambda name=name: web_save(name, lambda _values: {}))
					web = snapshot(name)
				if desk_result[0] == "crash":
					# Desk cannot save this stored IPD at all; the web no-op save must still work.
					self.assertEqual(web_result, ("saved", None))
					continue
				self.assertEqual(web_result, desk_result)
				self.assertEqual(web, desk)

	def test_full_payload_roundtrip(self):
		for name in SAMPLES.values():
			with self.subTest(name=name):
				with rolled_back("desk_full"):
					desk_equivalent_save(name)
					desk = snapshot(name)
				with rolled_back("web_full"):
					keys = writable_keys(frappe.get_doc(DOCTYPE, name))
					web_save(name, lambda values, keys=keys: payload_patch({"values": values}, keys))
					web = snapshot(name)
				self.assertEqual(web, desk)

	def test_stitching_quantity(self):
		def desk(doc):
			doc.stiching_item_details[0].quantity = 2

		def web(values):
			values["stiching_item_details"][0]["quantity"] = 2
			return pick(values, "stiching_item_details", "stiching_item_detail")

		saved = self.assert_edit_parity(SAMPLES["standard"], desk, web)
		self.assertEqual(saved["doc"]["stiching_item_details"][0]["quantity"], 2)

	def test_packing_subset_row(self):
		name = SAMPLES["set_item"]
		colour = next(value for value in packing_values(name) if value != "Pink Stripes Bow AO")

		def desk(doc):
			doc.append("packing_attribute_details", {"attribute_value": colour, "quantity": 0})
			doc.packing_attribute_no = 2

		def web(values):
			values["packing_attribute_details"].append({"attribute_value": colour, "quantity": 0})
			values["packing_attribute_no"] = 2
			return pick(
				values,
				"packing_attribute_details",
				"packing_attribute_no",
				"set_item_detail",
				"stiching_item_detail",
			)

		saved = self.assert_edit_parity(name, desk, web)
		self.assertEqual(
			[row["attribute_value"] for row in saved["doc"]["packing_attribute_details"]][-1], colour
		)

	def test_size_ratio_quantity(self):
		def desk(doc):
			doc.packing_size_details[0].quantity += 1
			doc.packing_combo += 1

		def web(values):
			values["packing_size_details"][0]["quantity"] += 1
			values["packing_combo"] += 1
			return pick(values, "packing_size_details", "packing_combo")

		self.assert_edit_parity(SAMPLES["set_size_ratio"], desk, web)

	def test_set_item_off(self):
		def desk(doc):
			doc.is_set_item = 0
			doc.set_item_detail = None

		def web(values):
			values["is_set_item"] = 0
			return pick(values, "is_set_item", "stiching_item_detail")

		saved = self.assert_edit_parity(SAMPLES["set_item"], desk, web)
		self.assertEqual(saved["doc"]["set_item_combination_details"], [])

	def test_set_combination_cell(self):
		name = SAMPLES["set_item"]
		colour = next(value for value in packing_values(name) if value != "Pink Stripes Bow AO")

		def desk(doc):
			data = json.loads(doc.set_item_detail)
			data["values"][0]["val"]["Bottom"] = colour
			doc.set_item_detail = json.dumps(data)

		def web(values):
			values["set_item_detail"]["values"][0]["val"]["Bottom"] = colour
			return pick(values, "set_item_detail", "stiching_item_detail")

		saved = self.assert_edit_parity(name, desk, web)
		bottom = [
			row
			for row in saved["doc"]["set_item_combination_details"]
			if row["set_item_attribute_value"] == "Bottom"
		]
		self.assertEqual(bottom[0]["attribute_value"], colour)

	def test_stitching_combination_cell_on_set_item(self):
		name = SAMPLES["set_size_ratio"]

		def desk(doc):
			data = json.loads(doc.stiching_item_detail)
			first = data["attributes"][-1]
			data["values"][0]["val"][first] = "White"
			doc.stiching_item_detail = json.dumps(data)

		def web(values):
			first = values["stiching_item_detail"]["attributes"][-1]
			values["stiching_item_detail"]["values"][0]["val"][first] = "White"
			return pick(values, "stiching_item_detail")

		self.assert_edit_parity(name, desk, web)

	def test_combination_rows_follow_attribute_order(self):
		name = SAMPLES["standard"]

		def desk(doc):
			pass

		def web(values):
			combination = values["stiching_item_detail"]
			for row in combination["values"]:
				row["val"] = dict(reversed(list(row["val"].items())))
			return pick(values, "stiching_item_detail")

		self.assert_edit_parity(name, desk, web)

	def test_cutting_weight(self):
		def desk(doc):
			data = frappe.parse_json(doc.cutting_items_json)
			data["items"][0]["Weight"] = 0.1234
			doc.cutting_items_json = data

		def web(values):
			values["cutting_items_json"]["items"][0]["Weight"] = 0.1234
			return pick(values, "cutting_items_json")

		self.assert_edit_parity(SAMPLES["standard"], desk, web)

	def test_cloth_choice(self):
		def desk(doc):
			data = frappe.parse_json(doc.cutting_cloths_json)
			data["items"][0]["Cloth"] = "RIB FABRIC"
			doc.cutting_cloths_json = data

		def web(values):
			values["cutting_cloths_json"]["items"][0]["Cloth"] = "RIB FABRIC"
			return pick(values, "cutting_cloths_json")

		self.assert_edit_parity(SAMPLES["standard"], desk, web)

	def test_accessory_name_keeps_trailing_space(self):
		def desk(doc):
			data = frappe.parse_json(doc.accessory_clothtype_json)
			data["NEW TAPE "] = None
			doc.accessory_clothtype_json = data

		def web(values):
			values["accessory_clothtype_json"]["NEW TAPE "] = None
			return pick(values, "accessory_clothtype_json")

		saved = self.assert_edit_parity(SAMPLES["standard"], desk, web)
		self.assertIn("NEW TAPE ", saved["doc"]["accessory_clothtype_json"])

	def test_stitching_accessory_colour(self):
		def desk(doc):
			data = frappe.parse_json(doc.stiching_accessory_json)
			data["items"][0]["accessory_colour"] = "White"
			doc.stiching_accessory_json = data

		def web(values):
			values["stiching_accessory_json"]["items"][0]["accessory_colour"] = "White"
			return pick(values, "stiching_accessory_json")

		self.assert_edit_parity(SAMPLES["standard"], desk, web)

	def test_embellishment_adds_process_row(self):
		def desk(doc):
			data = frappe.parse_json(doc.emblishment_details_json)
			data["Printing"] = ["Front"]
			doc.emblishment_details_json = data

		def web(values):
			values["emblishment_details_json"]["Printing"] = ["Front"]
			return pick(values, "emblishment_details_json")

		saved = self.assert_edit_parity(SAMPLES["standard"], desk, web)
		self.assertIn("Printing", [row["process_name"] for row in saved["doc"]["ipd_processes"]])

	def test_bom_based_on_toggle_seeds_packing_attribute(self):
		name = SAMPLES["standard"]
		index = next(
			i
			for i, row in enumerate(frappe.get_doc(DOCTYPE, name).item_bom)
			if row.based_on_attribute_mapping
		)

		def desk_off(doc):
			doc.item_bom[index].based_on_attribute_mapping = 0

		def web_off(values):
			values["item_bom"][index]["based_on_attribute_mapping"] = 0
			return pick(values, "item_bom")

		saved = self.assert_edit_parity(name, desk_off, web_off)
		self.assertIsNone(saved["bom_mappings"][index])

		def desk_retick(doc):
			doc.item_bom[index].based_on_attribute_mapping = 1

		def web_retick(values):
			values["item_bom"][index]["based_on_attribute_mapping"] = 1
			return pick(values, "item_bom")

		with rolled_back("bom_off"):
			row_name = frappe.get_doc(DOCTYPE, name).item_bom[index].name
			frappe.db.set_value(
				"YRP Item BOM", row_name, {"based_on_attribute_mapping": 0, "attribute_mapping": None}
			)
			saved = self.assert_edit_parity(name, desk_retick, web_retick)
		attributes = saved["bom_mappings"][index]["attributes"]
		self.assertEqual(
			[row.attribute for row in attributes if row.parentfield == "item_attributes"], ["Colour"]
		)

	def test_panel_wise_weight(self):
		def edit(matrix):
			cell = next(iter(matrix["panels"][0]["rows"][0]["values"].values()))
			cell["weight"] = 0.0321
			return matrix

		def desk(doc):
			doc.panel_wise_consumption_matrix_json = edit(
				frappe.parse_json(doc.panel_wise_consumption_matrix_json)
			)

		def web(values):
			values["panel_wise_consumption_matrix_json"] = edit(values["panel_wise_consumption_matrix_json"])
			return pick(values, "panel_wise_consumption_matrix_json")

		self.assert_edit_parity(SAMPLES["panel_grouped"], desk, web)

	def test_panel_wise_toggle_refresh_and_save(self):
		from essdee_yrp.panel_wise_cloth_mapping import get_panel_wise_cloth_mapping_matrix
		from essdee_yrp.panel_wise_consumption import get_panel_wise_consumption_matrix

		name = SAMPLES["standard"]

		def desk(doc):
			doc.enable_panel_wise_consumption_matrix = 1
			doc.panel_wise_consumption_matrix_json = get_panel_wise_consumption_matrix(doc)["matrix"]
			doc.panel_wise_cloth_mapping_json = get_panel_wise_cloth_mapping_matrix(doc)["matrix"]

		def web(values):
			patch = {"enable_panel_wise_consumption_matrix": 1}
			grids = workspace.get_ipd_grids(
				name, patch, ["panel_wise_consumption", "panel_wise_cloth_mapping"]
			)["grids"]
			return {
				**patch,
				"panel_wise_consumption_matrix_json": wire(grids["panel_wise_consumption"]["matrix"]),
				"panel_wise_cloth_mapping_json": wire(grids["panel_wise_cloth_mapping"]["matrix"]),
			}

		saved = self.assert_edit_parity(name, desk, web)
		self.assertEqual(saved["doc"]["enable_panel_wise_consumption_matrix"], 1)

	def test_marker_groups_written_and_cleared(self):
		name = SAMPLES["standard"]
		panels = [row["stiching_attribute_value"] for row in editor(name)["values"]["stiching_item_details"]]

		def desk(doc):
			doc.marker_details = [{"selected": list(panels)}]

		def web(values):
			return {"marker_groups": [list(reversed(panels))]}

		saved = self.assert_edit_parity(name, desk, web)
		self.assertEqual(saved["doc"]["cutting_marker_groups"][0]["group_panels"], ",".join(sorted(panels)))
		with rolled_back("clear_groups"):
			web_save(name, lambda _values: {"marker_groups": [list(panels)]})
			web_save(name, lambda _values: {"marker_groups": []})
			self.assertEqual(snapshot(name)["doc"]["cutting_marker_groups"], [])

	def test_historical_attribute_value_id_is_kept(self):
		name = SAMPLES["standard"]
		row = frappe.get_doc(DOCTYPE, name).packing_attribute_details[0]
		label = attribute_value(row.attribute_value)
		legacy = f"IAV-legacy-{frappe.generate_hash(length=10)}"
		with rolled_back("legacy_roundtrip"):
			frappe.db.sql(
				"insert into `tabYRP Item Attribute Value` (name, attribute_name, attribute_value, creation, modified)"
				" values (%s, 'Size', %s, now(), now())",
				(legacy, label),
			)
			frappe.db.set_value(row.doctype, row.name, "attribute_value", legacy, update_modified=False)
			keys = writable_keys(frappe.get_doc(DOCTYPE, name))
			web_save(name, lambda values: payload_patch({"values": values}, keys))
			self.assertEqual(frappe.db.get_value(row.doctype, row.name, "attribute_value"), legacy)

	def test_new_draft_matches_desk_insert(self):
		source = frappe.get_doc(DOCTYPE, SAMPLES["standard"])
		values = {"item": source.item, "tech_pack_version": "QA-TP", "pattern_version": "QA-P"}
		with rolled_back("desk_insert"):
			doc = frappe.new_doc(DOCTYPE)
			doc.update(values)
			details = get_complete_item_details(source.item)
			doc.primary_item_attribute = details.primary_attribute
			doc.set("item_attributes", details.attributes)
			doc.dependent_attribute = details.dependent_attribute
			doc.dependent_attribute_mapping = details.dependent_attribute_mapping
			doc.insert()
			desk = snapshot(doc.name)
		with rolled_back("web_insert"):
			payload = workspace.save_ipd(values)
			web = snapshot(payload["record"]["name"])
		self.assertEqual(web, desk)

	def test_cloth_yarn_ratio_and_compacting(self):
		name = SAMPLES["cloth"]

		def desk(doc):
			doc.yarn_ratio_details[0].ratio = 60
			doc.yarn_ratio_details[1].ratio = 40

		def web(values):
			values["yarn_ratio_details"][0]["ratio"] = 60
			values["yarn_ratio_details"][1]["ratio"] = 40
			return pick(values, "yarn_ratio_details")

		saved = self.assert_edit_parity(name, desk, web)
		self.assertEqual([row["ratio"] for row in saved["doc"]["yarn_ratio_details"]], [60, 40])

	def test_copy_matches_duplicate(self):
		source = SAMPLES["set_item"]
		with rolled_back("desk_copy"):
			doc = frappe.get_doc(DOCTYPE, duplicate_ipd(source))
			doc.tech_pack_version, doc.pattern_version, doc.copied_from = "QA-TP", "QA-P", source
			doc.save()
			desk = snapshot(doc.name)
		with rolled_back("web_copy"):
			name = workspace.copy_ipd(source, "QA-TP", "QA-P", ["cutting", "accessories", "processes"])[
				"name"
			]
			web = snapshot(name)
		self.assertEqual(web, desk)


def pick(values, *keys):
	return {key: copy.deepcopy(values[key]) for key in keys}


def packing_values(name):
	payload = editor(name)
	return next(entry["values"] for entry in payload["context"]["attributes"] if "packing" in entry["roles"])


def stride_samples():
	names = frappe.get_all(
		DOCTYPE, filters={"is_cloth_item": 0}, pluck="name", order_by="name asc", limit_page_length=0
	)
	step = max(1, len(names) // STRIDE_SAMPLES)
	return [name for name in names[::step][:STRIDE_SAMPLES] if name not in SAMPLES.values()]
