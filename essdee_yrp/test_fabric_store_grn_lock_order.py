from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.fabric_store.documents.goods_received_note import save_goods_received_note
from essdee_yrp.overrides.goods_received_note import _lock_versioned_cloth_lot


class TestFabricStoreGRNLockOrder(TestCase):
	def test_web_submit_locks_lot_before_save_or_insert_and_reuses_flag(self):
		for existing in (True, False):
			with self.subTest(existing=existing):
				events = []
				doc = frappe._dict(
					name="GRN-1",
					docstatus=0,
					against="YRP Work Order",
					against_id="WO-1",
					items=[],
					correction_items=[],
					flags=frappe._dict(),
				)
				doc.set = MagicMock(side_effect=lambda fieldname, value: doc.update({fieldname: value}))

				def persist():
					self.assertEqual(doc.flags.cloth_execution_lot_locked, "LOT-1")
					events.append("save" if existing else "insert")

				def submit():
					# The controller calls the same helper before Frappe submission.
					_lock_versioned_cloth_lot(doc)
					self.assertEqual(doc.flags.cloth_execution_lot_locked, "LOT-1")
					events.append("submit")

				doc.save = MagicMock(side_effect=persist)
				doc.insert = MagicMock(side_effect=persist)
				doc.submit = MagicMock(side_effect=submit)
				with (
					patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._resolve_source", return_value=(None, "YRP Work Order", "WO-1", None)),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._source_defaults", return_value={}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=doc),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._special_source_context", return_value={"active": True}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
					patch("essdee_yrp.fabric_substitution.get_default_knitting_grn_context", return_value=frappe._dict(lot="LOT-1")),
					patch("essdee_yrp.fabric_substitution._lock_lot", side_effect=lambda _lot: events.append("lot")) as lock_lot,
				):
					save_goods_received_note({}, name=doc.name if existing else None, submit=True)
				self.assertEqual(events, ["lot", "save" if existing else "insert", "submit"])
				lock_lot.assert_called_once_with("LOT-1")
