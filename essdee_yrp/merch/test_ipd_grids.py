import json
import time
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.attribute_links import value as attribute_value

from essdee_yrp import ipd_ui
from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd.grids import GRID_KEYS, build_grids
from essdee_yrp.merch.ipd.payload import mapping_memo, mapping_of
from essdee_yrp.merch.ipd_test_support import SAMPLES, rolled_back, unapprove
from essdee_yrp.panel_wise_cloth_mapping import get_panel_wise_cloth_mapping_matrix
from essdee_yrp.panel_wise_consumption import get_panel_wise_consumption_matrix

GRID_SAMPLES = (SAMPLES["set_item"], SAMPLES["standard"], SAMPLES["panel_grouped"])
WRITE_STATEMENTS = ("insert", "update", "delete", "replace")


def wire(value):
	return json.loads(json.dumps(value, default=str))


def desk_grids(name):
	"""What each Desk "Get … Combination" button returns for the saved document."""
	doc = frappe.get_doc(DOCTYPE, name)
	attributes = {
		key: [row.attribute for row in doc.get(key)]
		for key in ("cutting_attributes", "cloth_attributes", "accessory_attributes")
	}
	cloths = [row.name1 for row in doc.cloth_detail]
	packing = [row.as_dict() for row in doc.packing_attribute_details]
	grids = {
		"stitching_combination": ipd_ui.get_new_combination(
			mapping_of(doc, doc.stiching_attribute),
			packing,
			attribute_value(doc.stiching_major_attribute_value),
			doc.is_same_packing_attribute,
			doc.name,
		),
		"stiching_accessory": ipd_ui.get_stiching_accessory_combination(cloths, name),
		"cloth_accessory": ipd_ui.get_combination(name, attributes["accessory_attributes"], "Accessory"),
	}
	if doc.is_set_item:
		grids["set_combination"] = ipd_ui.get_new_combination(
			mapping_of(doc, doc.set_item_attribute), packing, attribute_value(doc.major_attribute_value)
		)
	if doc.packing_mode == "Size Ratio Packing":
		grids["packing_sizes"] = ipd_ui.get_packing_size_values(name)
	if doc.enable_panel_wise_consumption_matrix:
		grids["panel_wise_consumption"] = get_panel_wise_consumption_matrix(name)
		grids["panel_wise_cloth_mapping"] = get_panel_wise_cloth_mapping_matrix(name)
	else:
		grids["cutting_items"] = ipd_ui.get_combination(name, attributes["cutting_attributes"], "Cutting")
		grids["cutting_cloths"] = ipd_ui.get_combination(
			name, attributes["cloth_attributes"], "Cloth", cloths
		)
	return wire(grids)


class TestIpdGrids(IntegrationTestCase):
	"""Editor skeletons come from the Desk generators, over the draft, with no writes."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for name in GRID_SAMPLES:
			unapprove(name)

	def test_grid_cores_match_desk(self):
		for name in GRID_SAMPLES:
			with self.subTest(name=name):
				expected = desk_grids(name)
				grids = wire(workspace.get_ipd_grids(name, {}, list(expected))["grids"])
				self.assertEqual(grids, expected)

	def test_draft_grids_match_desk_after_save(self):
		name = SAMPLES["set_item"]
		values = wire(workspace.get_ipd_editor(name)["values"])
		colour = next(
			value
			for value in colour_values(name)
			if value != values["set_item_detail"]["values"][0]["major_attribute"]
		)
		values["set_item_detail"]["values"][0]["val"]["Bottom"] = colour
		draft = {
			"set_item_detail": values["set_item_detail"],
			"stiching_item_detail": values["stiching_item_detail"],
		}
		keys = ["stiching_accessory", "cloth_accessory", "cutting_items"]
		grids = wire(workspace.get_ipd_grids(name, draft, keys)["grids"])
		with rolled_back("draft_grids"):
			workspace.save_ipd(draft, name, str(frappe.db.get_value(DOCTYPE, name, "modified")))
			expected = desk_grids(name)
		self.assertEqual(grids, {key: expected[key] for key in keys})
		bottom = [item for item in grids["stiching_accessory"]["items"] if item.get("Part") == "Bottom"]
		self.assertEqual({item["major_colour"] for item in bottom}, {colour})

	def test_grids_make_no_writes(self):
		real_sql = frappe.db.sql

		def read_only_sql(query, *args, **kwargs):
			statement = str(query).lstrip().split(" ", 1)[0].lower()
			if statement in WRITE_STATEMENTS:
				raise AssertionError(f"grid refresh wrote: {query}")
			return real_sql(query, *args, **kwargs)

		for name in GRID_SAMPLES:
			values = wire(workspace.get_ipd_editor(name)["values"])
			values["stiching_item_details"][0]["quantity"] = 3
			with patch.object(frappe.db, "sql", side_effect=read_only_sql):
				workspace.get_ipd_grids(
					name, {"stiching_item_details": values["stiching_item_details"]}, list(GRID_KEYS)
				)

	def test_cores_do_not_reload_the_ipd(self):
		real_get_doc = frappe.get_doc

		def no_ipd_reload(*args, **kwargs):
			if args and args[0] == DOCTYPE:
				raise AssertionError("generator reloaded the saved IPD")
			return real_get_doc(*args, **kwargs)

		for name in GRID_SAMPLES:
			doc = frappe.get_doc(DOCTYPE, name)
			with mapping_memo(doc), patch.object(frappe, "get_doc", side_effect=no_ipd_reload):
				grids, errors = build_grids(
					doc, [key for key in GRID_KEYS if not key.startswith("panel")], True
				)
			self.assertEqual(errors, {})
			self.assertTrue(grids["stitching_combination"])

	def test_unknown_grid_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Unknown grids"):
			workspace.get_ipd_grids(SAMPLES["standard"], {}, ["everything"])

	def test_query_budgets(self):
		"""Fixed query counts per request whatever the IPD size: first measurement + 20%."""
		budgets = {"editor": 66, "grids": 41, "check": 360}
		editor_counts = []
		for name in (SAMPLES["set_item"], SAMPLES["set_size_ratio"], SAMPLES["panel_grouped"]):
			unapprove(name)
			for label, call in (
				("editor", lambda name=name: workspace.get_ipd_editor(name)),
				("grids", lambda name=name: workspace.get_ipd_grids(name, {}, list(GRID_KEYS))),
				("check", lambda name=name: workspace.check_ipd(name)),
			):
				measure(call)
				count, elapsed = measure(call)
				with self.subTest(name=name, call=label):
					self.assertLessEqual(count, budgets[label])
					if label == "check":
						self.assertLess(elapsed, 0.4)
				if label == "editor":
					editor_counts.append(count)
		self.assertLessEqual(max(editor_counts) - min(editor_counts), 3, editor_counts)


def measure(call):
	for cache in ("attribute_link_values", "attribute_link_names", "attribute_link_context"):
		if hasattr(frappe.local, cache):
			delattr(frappe.local, cache)
	frappe.db.value_cache.clear()
	real_sql = frappe.db.sql
	count = 0

	def counting_sql(*args, **kwargs):
		nonlocal count
		count += 1
		return real_sql(*args, **kwargs)

	started = time.monotonic()
	with patch.object(frappe.db, "sql", side_effect=counting_sql):
		call()
	return count, time.monotonic() - started


def colour_values(name):
	payload = workspace.get_ipd_editor(name)
	return next(
		entry["values"] for entry in payload["context"]["attributes"] if entry["attribute"] == "Colour"
	)
