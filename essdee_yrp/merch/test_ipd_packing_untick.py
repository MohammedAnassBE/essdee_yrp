import copy

import frappe
from frappe.tests import UnitTestCase
from yrp.attribute_links import value as attribute_value

from essdee_yrp.ipd_validations import save_combination_detail_fields
from essdee_yrp.merch.ipd.draft import build_draft
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_workspace import get_ipd_editor, get_ipd_grids


class TestIpdPackingUntick(UnitTestCase):
	"""Unticking a packing colour leaves a stale stitching row until that grid is rebuilt."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("ipd_packing_untick")
		self.addCleanup(lambda: frappe.db.rollback(save_point="ipd_packing_untick"))
		names = frappe.get_all(
			DOCTYPE,
			filters={"is_cloth_item": 0, "is_set_item": 1, "stiching_attribute": ["is", "set"]},
			pluck="name",
		)
		self.name, self.values = next(self.with_set_and_stitching(names), (None, None))
		if not self.name:
			self.skipTest("A set item IPD with set and stitching combinations is required")
		frappe.db.set_value(DOCTYPE, self.name, "approval_status", "Not Approved", update_modified=False)
		self.dropped = self.values["set_item_detail"]["values"][0]["major_attribute"]
		self.patch = self.untick_patch()

	def with_set_and_stitching(self, names):
		for name in names:
			values = get_ipd_editor(name)["values"]
			if len((values.get("set_item_detail") or {}).get("values") or []) > 1 and (
				values.get("stiching_item_detail") or {}
			).get("values"):
				yield name, values

	def untick_patch(self):
		set_detail = copy.deepcopy(self.values["set_item_detail"])
		set_detail["values"] = [row for row in set_detail["values"] if row["major_attribute"] != self.dropped]
		packing = [
			row for row in self.values["packing_attribute_details"] if row["attribute_value"] != self.dropped
		]
		return {
			"packing_attribute_details": packing,
			"set_item_detail": set_detail,
			"stiching_item_detail": self.values["stiching_item_detail"],
		}

	def test_stitching_grid_refresh_after_untick(self):
		result = get_ipd_grids(self.name, self.patch, ["stitching_combination"])
		majors = [row["major_attribute"] for row in result["grids"]["stitching_combination"]["values"]]
		self.assertNotIn(self.dropped, majors)

	def test_desk_save_drops_stale_stitching_rows(self):
		doc = build_draft(self.name, self.patch)
		save_combination_detail_fields(doc)
		stitched = {row.get("index") for row in doc.stiching_item_combination_details}
		set_majors = {attribute_value(row.major_attribute_value) for row in doc.set_item_combination_details}
		self.assertNotIn(self.dropped, set_majors)
		self.assertEqual(stitched, set(range(len(self.patch["set_item_detail"]["values"]))))

	def test_packed_colour_without_set_row_fails_clearly(self):
		self.patch["packing_attribute_details"] = self.values["packing_attribute_details"]
		doc = build_draft(self.name, self.patch)
		with self.assertRaisesRegex(frappe.ValidationError, "Fill the Set Item combination"):
			save_combination_detail_fields(doc)
