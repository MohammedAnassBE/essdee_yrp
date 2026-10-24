from datetime import datetime
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.cutting import web_workspace
from essdee_yrp.cutting.movement import (
	get_active_root_transactions,
	get_active_root_transactions_by_movement,
)

MODULE = "essdee_yrp.cutting.movement"


def _row(name, cpm, minute, docstatus=1, purpose=None, modified=0):
	return frappe._dict(
		name=name,
		cut_panel_movement=cpm,
		docstatus=docstatus,
		purpose=purpose,
		creation=datetime(2026, 1, 1, 0, minute),
		modified=modified,
	)


ROWS = {
	"YRP Stock Entry": [
		_row("STE-1", "CPM-1", 5, purpose="Material Issue"),
		_row("STE-2", "CPM-1", 1, purpose="DC Completion"),
		_row("STE-3", "CPM-2", 3, purpose="Send to Warehouse", docstatus=0),
		_row("STE-4", "CPM-2", 3, purpose="Material Consumed", modified=1),
	],
	"YRP Delivery Challan": [
		_row("DC-1", "CPM-1", 2),
		_row("DC-2", "CPM-1", 9, docstatus=2),
		_row("DC-3", "CPM-2", 3),
	],
	"YRP Goods Received Note": [_row("GRN-1", "CPM-3", 4)],
}


def _matches(row, filters):
	for field, condition in filters.items():
		operator, value = condition if isinstance(condition, list) else ("=", condition)
		actual = row.get(field)
		if operator == "=" and actual != value:
			return False
		if operator == "in" and actual not in value:
			return False
		if operator == "<" and not (actual or 0) < value:
			return False
		if operator == "not in" and (actual or "") in value:
			return False
		if operator == "!=" and actual == value:
			return False
	return True


def fake_get_all(doctype, filters, fields):
	rows = sorted(ROWS[doctype], key=lambda row: row.modified, reverse=True)
	return [frappe._dict({field: row[field] for field in fields}) for row in rows if _matches(row, filters)]


class TestActiveRootTransactionsByMovement(TestCase):
	def test_batch_matches_single_movement_answers(self):
		names = ["CPM-1", "CPM-2", "CPM-3", "CPM-EMPTY"]
		with patch(f"{MODULE}.frappe.get_all", side_effect=fake_get_all) as get_all:
			batched = get_active_root_transactions_by_movement(iter(names))
			self.assertEqual(get_all.call_count, 3)
			single = {name: get_active_root_transactions(name) for name in names}
		self.assertEqual(batched, single)
		self.assertEqual([row.name for row in batched["CPM-1"]], ["DC-1", "STE-1"])
		self.assertEqual([row.name for row in batched["CPM-2"]], ["STE-4", "STE-3", "DC-3"])
		self.assertEqual(batched["CPM-EMPTY"], [])

	def test_full_timestamp_tie_keeps_the_single_movement_read_for_that_movement(self):
		tied = {
			**ROWS,
			"YRP Delivery Challan": [*ROWS["YRP Delivery Challan"], _row("DC-4", "CPM-3", 4), _row("DC-5", "CPM-3", 4)],
		}
		with (
			patch.dict(ROWS, tied),
			patch(f"{MODULE}.frappe.get_all", side_effect=fake_get_all),
			patch(f"{MODULE}.get_active_root_transactions", return_value=["single"]) as single,
		):
			batched = get_active_root_transactions_by_movement(["CPM-1", "CPM-3"])
		single.assert_called_once_with("CPM-3")
		self.assertEqual(batched["CPM-3"], ["single"])
		self.assertEqual([row.name for row in batched["CPM-1"]], ["DC-1", "STE-1"])

	def test_empty_input_runs_no_query(self):
		with patch(f"{MODULE}.frappe.get_all") as get_all:
			self.assertEqual(get_active_root_transactions_by_movement([]), {})
		get_all.assert_not_called()

	def test_link_spelled_differently_falls_back_to_single_movement_reads(self):
		def collation_get_all(doctype, filters, fields):
			if isinstance(filters["cut_panel_movement"], list):
				return [frappe._dict(name="DC-9", cut_panel_movement="cpm-1", docstatus=1, creation=datetime(2026, 1, 1))]
			return []

		with (
			patch(f"{MODULE}.frappe.get_all", side_effect=collation_get_all),
			patch(f"{MODULE}.get_active_root_transactions", return_value=["exact"]) as single,
		):
			self.assertEqual(get_active_root_transactions_by_movement(["CPM-1", "CPM-2"]), {"CPM-1": ["exact"], "CPM-2": ["exact"]})
		self.assertEqual([call.args[0] for call in single.call_args_list], ["CPM-1", "CPM-2"])


class TestWorkspaceMovementRoots(TestCase):
	def test_workspace_reads_roots_once_for_submitted_movements_only(self):
		docs = {
			"CPM-1": frappe._dict(name="CPM-1", docstatus=1),
			"CPM-2": frappe._dict(name="CPM-2", docstatus=0),
			"CPM-3": frappe._dict(name="CPM-3", docstatus=1),
		}
		roots = {"CPM-1": [frappe._dict(doctype="YRP Delivery Challan", name="DC-1", docstatus=1)], "CPM-3": []}
		with (
			patch.object(web_workspace.frappe, "has_permission", return_value=True),
			patch.object(web_workspace.frappe, "get_list", return_value=list(docs)),
			patch.object(web_workspace.frappe, "get_doc", side_effect=lambda doctype, name: docs[name]),
			patch.object(web_workspace, "get_active_root_transactions_by_movement", return_value=roots) as batch,
			patch.object(web_workspace, "_movement_payload", side_effect=lambda doc, active_root_rows: (doc.name, active_root_rows)),
		):
			payloads = web_workspace._get_movements(frappe._dict(name="CP-1"))
		self.assertEqual(list(batch.call_args.args[0]), ["CPM-1", "CPM-3"])
		self.assertEqual(payloads, [("CPM-1", roots["CPM-1"]), ("CPM-2", []), ("CPM-3", [])])

	def test_given_root_rows_replace_the_single_movement_read(self):
		doc = frappe._dict(doctype="SD YRP Cut Panel Movement", name="CPM-1", docstatus=1, cut_panel_movement_json="{}")
		rows = [frappe._dict(doctype="YRP Delivery Challan", name="DC-1", docstatus=1, creation=None)]
		with (
			patch.object(web_workspace.frappe, "has_permission", return_value=False),
			patch.object(web_workspace, "get_document_print_formats", return_value=[]),
			patch(f"{MODULE}.get_active_root_transactions", return_value=rows) as single,
		):
			given = web_workspace._movement_payload(doc, active_root_rows=rows)
			single.assert_not_called()
			read = web_workspace._movement_payload(doc)
		single.assert_called_once_with("CPM-1")
		self.assertEqual(given, read)
		self.assertEqual(given["active_root_transactions"], [{"doctype": "YRP Delivery Challan", "name": "DC-1", "docstatus": 1}])
