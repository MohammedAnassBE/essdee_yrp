"""Report UOM provenance planning never guesses from stock or secondary UOM."""

import importlib
import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe


def provenance():
	return importlib.import_module(
		"essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order_itemwise.mrp_uom_provenance"
	)


class TestPurchaseRound3Reports(unittest.TestCase):
	def test_parent_save_keeps_marker_and_uom_change_away_and_back_retires_it(self):
		from copy import deepcopy

		from frappe.model.document import Document

		marker = '{"source_uom":null,"stored_uom":"Nos","modified":"2026-08-02"}'
		previous = frappe._dict(items=[frappe._dict(name="ROW-1", uom="Nos", custom_mrp_report_uom=marker)])
		row = deepcopy(previous["items"][0])
		row.modified = "2026-10-20"
		doc = Document({"doctype": "Purchase Order", "name": "PO-1"})
		# Use real Documents for hook dispatch, without saving business data.
		doc.items = [row]
		doc._doc_before_save = previous
		provenance().retire_changed_uom(doc)
		self.assertEqual(row.custom_mrp_report_uom, marker)
		row.uom = "Kg"
		provenance().retire_changed_uom(doc)
		self.assertIsNone(row.custom_mrp_report_uom)
		doc._doc_before_save = frappe._dict(items=[deepcopy(row)])
		row.uom = "Nos"
		row.custom_mrp_report_uom = marker  # stale client metadata must not revive it
		provenance().retire_changed_uom(doc)
		self.assertIsNone(row.custom_mrp_report_uom)

	def test_provenance_retirement_is_registered_for_each_purchase_order_save_action(self):
		handler = provenance().__name__ + ".retire_changed_uom"
		hooks = frappe.get_hooks("doc_events")["Purchase Order"]
		for event in ("before_save", "before_submit", "before_update_after_submit", "before_cancel"):
			with self.subTest(event=event):
				self.assertIn(handler, hooks.get(event, []))

	def test_new_or_copied_items_cannot_inherit_a_report_override(self):
		from frappe.model.document import Document

		marker = '{"source_uom":null,"stored_uom":"Nos","modified":"2026-08-02"}'
		doc = Document({"doctype": "Purchase Order", "name": "PO-copy"})
		doc.items = [frappe._dict(name="NEW-ROW", uom="Nos", custom_mrp_report_uom=marker)]
		provenance().retire_changed_uom(doc)
		self.assertIsNone(doc.items[0].custom_mrp_report_uom)

	def test_parity_overlay_handles_empty_and_partial_backfill_without_losing_existing_markers(self):
		with patch.object(
			sys, "path", [str(Path(frappe.get_app_path("essdee_yrp")).parent / "scripts"), *sys.path]
		):
			parity = importlib.import_module("purchase_round3_parity")
		with sqlite3.connect(":memory:") as db:
			db.executescript(
				"CREATE TABLE `tabPurchase Order Item` (name TEXT, custom_mrp_report_uom TEXT);"
				"INSERT INTO `tabPurchase Order Item` VALUES ('A','existing'),('B',NULL);"
			)
			query = "SELECT `tabPurchase Order Item`.`custom_mrp_report_uom` FROM `tabPurchase Order Item` ORDER BY name"
			for updates, exists, expected in [
				([], True, [("existing",), (None,)]),
				([], False, [(None,), (None,)]),
				([dict(name="B", marker="new")], True, [("existing",), ("new",)]),
			]:
				with self.subTest(updates=updates, exists=exists):
					sql, values = parity.provenance_query(query, {}, updates, exists)
					sql = re.sub(r"%\((\w+)\)s", r":\1", sql)
					self.assertEqual(db.execute(sql, values).fetchall(), expected)

	def test_blank_uom_plan_only_marks_unchanged_migrated_rows(self):
		source = [
			dict(
				name="ROW-1",
				parent="PO-1",
				item_variant="Label-M",
				creation="2026-08-01",
				modified="2026-08-02",
				uom=None,
			)
		]
		target = [
			dict(
				name="ROW-1",
				parent="PO-1",
				item_code="Label-M",
				creation="2026-08-01",
				modified="2026-08-02",
				uom="Nos",
				is_yrp_managed=1,
			)
		]
		plan = provenance().plan_backfill(source, target)
		self.assertEqual(plan["skipped"], [])
		self.assertEqual(len(plan["updates"]), 1)
		self.assertEqual(
			json.loads(plan["updates"][0]["marker"]),
			{"source_uom": None, "stored_uom": "Nos", "modified": "2026-08-02"},
		)
		self.assertEqual(target[0]["uom"], "Nos")
		for field, value in [
			("parent", "OTHER"),
			("item_code", "OTHER"),
			("modified", "2026-10-01"),
			("is_yrp_managed", 0),
		]:
			with self.subTest(field=field):
				plan = provenance().plan_backfill(source, [dict(target[0], **{field: value})])
				self.assertEqual(plan["updates"], [])
				self.assertEqual(len(plan["skipped"]), 1)

	def test_real_source_uom_is_never_blank_marked_and_existing_marker_is_idempotent(self):
		source = [
			dict(
				name="ROW-1",
				parent="PO-1",
				item_variant="Label-M",
				creation="2026-08-01",
				modified="2026-08-02",
				uom="Nos",
			)
		]
		target = [
			dict(
				name="ROW-1",
				parent="PO-1",
				item_code="Label-M",
				creation="2026-08-01",
				modified="2026-08-02",
				uom="Nos",
				is_yrp_managed=1,
			)
		]
		self.assertEqual(provenance().plan_backfill(source, target)["updates"], [])
		source[0]["uom"] = None
		target[0]["custom_mrp_report_uom"] = '{"source_uom":null,"stored_uom":"Nos","modified":"2026-08-02"}'
		self.assertEqual(provenance().plan_backfill(source, target)["updates"], [])
		target[0]["custom_mrp_report_uom"] = '{"source_uom":"","stored_uom":"Nos","modified":"2026-08-02"}'
		plan = provenance().plan_backfill(source, target)
		self.assertEqual(plan["updates"], [])
		self.assertEqual(len(plan["skipped"]), 1)
