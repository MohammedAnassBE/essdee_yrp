from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.cutting.movement import is_stitching_consumption_grn

LEDGER = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger"
MOVEMENT = "essdee_yrp.cutting.movement"


class TestStitchingGrnBundleConsumption(TestCase):
	def grn(self, **values):
		doc = frappe._dict(
			doctype="YRP Goods Received Note",
			name="GRN-1",
			against="YRP Work Order",
			is_return=0,
			additional_grn=0,
			process_name="Stitching",
		)
		doc.update(values)
		return doc

	def is_consumption(self, doc, is_group=0, in_group=False):
		with (
			patch(f"{MOVEMENT}.attribute_db.get_value", return_value="IPD-1"),
			patch(f"{MOVEMENT}.frappe.db.get_value", side_effect=["Stitching", is_group]),
			patch(f"{MOVEMENT}.frappe.db.exists", return_value=in_group),
		):
			return bool(is_stitching_consumption_grn(doc, "LOT-1"))

	def test_stitching_and_grouped_stitching_grns_consume_bundles(self):
		self.assertTrue(self.is_consumption(self.grn()))
		self.assertTrue(self.is_consumption(self.grn(process_name="Stitching and Packing"), 1, True))

	def test_returns_additional_and_other_process_grns_do_not(self):
		self.assertFalse(self.is_consumption(self.grn(is_return=1)))
		self.assertFalse(self.is_consumption(self.grn(additional_grn=1)))
		self.assertFalse(self.is_consumption(self.grn(process_name="Printing"), 0))

	def test_consumption_moves_grn_deliverables_out_of_the_job_worker_only(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger import (
			update_collapsed_bundle,
		)

		deliverable = frappe._dict(item_variant="TEE-Top Back-Red-M", quantity=5)
		doc = self.grn(lot="LOT-1", items=[frappe._dict(item_variant="TEE-Red-M", quantity=5)])
		doc.grn_deliverables = [deliverable]
		movement = frappe._dict(
			variant=deliverable.item_variant, item="TEE", attributes={}, set_combination={}, quantity=5
		)
		with (
			patch(f"{LEDGER}.frappe.get_doc", return_value=doc),
			patch(
				f"{LEDGER}.attribute_db.get_value",
				side_effect=["IPD-1", ("Size", "Colour", "Panel", "Cut", "Stage")],
			),
			patch(f"{LEDGER}.frappe.db.exists", return_value=True),
			patch(f"{MOVEMENT}._movement_locations", return_value=("S-0172", "S-0172")),
			patch(f"{LEDGER}._collapsed_transaction_rows", return_value=[movement]) as rows,
			patch(f"{LEDGER}.on_submit_collapsed_bundles", return_value={}) as submit,
			patch(f"{LEDGER}.create_new_collapsed_bundle"),
		):
			update_collapsed_bundle(doc.doctype, doc.name, "on_submit", consume_grn_deliverables=True)

		self.assertEqual(rows.call_args.args[0]["items"], [deliverable])
		self.assertEqual(submit.call_count, 1)
		self.assertEqual(submit.call_args.args[3], "S-0172")
		self.assertNotIn("add", submit.call_args.kwargs)

	def test_allow_non_bundle_still_consumes_the_stitched_panels(self):
		from essdee_yrp.cutting.movement import apply_transaction

		doc = self.grn(lot="LOT-1", allow_non_bundle=1, cut_panel_movement=None)
		with (
			patch(f"{MOVEMENT}._bundle_tracking_disabled", return_value=False),
			patch(f"{MOVEMENT}._is_implicit_collapsed_return", return_value=False),
			patch(f"{MOVEMENT}.is_stitching_consumption_grn", return_value=True),
			patch(f"{MOVEMENT}.frappe.db.get_value", return_value=None),
			patch(f"{LEDGER}.update_collapsed_bundle") as update,
		):
			apply_transaction(doc)

		update.assert_called_once_with(doc.doctype, doc.name, "on_submit", consume_grn_deliverables=True)
