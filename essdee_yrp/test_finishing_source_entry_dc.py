from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.finishing import source_entries, web_entries
from essdee_yrp.finishing.old_lot import _apply_lot_transfer_to_finishing
from essdee_yrp.finishing.rebuild import _apply_ironing_excess, _apply_lot_transfers
from essdee_yrp.finishing.stock import _update_ironing_excess
from essdee_yrp.finishing.web_workspace import get_linked_documents
from essdee_yrp.migration import mark_finishing_entries_dc_done

OLD = "01-01-2026 10:00:00"
NEW = {"datetime": "02-01-2026 11:00:00", "dc": "DC-1"}
REAL_GET_DOC = frappe.get_doc


def _row(**values):
	row = {"item_variant": "VAR-1", "set_combination": '{"major_colour":"Blue"}', "ironing_excess": 0}
	row.update(values)
	for field in ("lot_transferred", "accepted_qty", "dc_qty", "cutting_qty", "inward_quantity"):
		row.setdefault(field, 0)
	return frappe._dict(row)


def _plan(**values):
	doc = frappe._dict(
		{
			"name": "FP-1",
			"ironing_excess_list": "{}",
			"lot_transfer_list": "{}",
			"finishing_plan_details": [_row()],
			**values,
		}
	)
	doc.get = lambda key, default=None: doc[key] if key in doc else default
	doc.set = lambda key, value: doc.__setitem__(key, value)
	doc.save = lambda **_kwargs: doc
	doc.db_set = MagicMock(side_effect=lambda key, value: doc.__setitem__(key, value))
	return doc


def _plan_or_real(plan):
	def get_doc(doctype, *args, **kwargs):
		if doctype == "SD YRP Finishing Plan":
			return plan
		return REAL_GET_DOC(doctype, *args, **kwargs)

	return get_doc


def _source(name, **values):
	return frappe._dict(
		{
			"name": name,
			"docstatus": 1,
			"items": [frappe._dict(item="VAR-1", qty=4, set_combination='{"major_colour":"Blue"}')],
			**values,
		}
	)


class TestFinishingSourceEntryDc(IntegrationTestCase):
	def test_readers_accept_old_string_and_new_dict(self):
		entries = source_entries.get_entries(frappe.as_json({"SE-OLD": OLD, "SE-NEW": NEW}))
		self.assertEqual(entries["SE-OLD"], {"datetime": OLD, "dc": ""})
		self.assertEqual(entries["SE-NEW"], NEW)

		plan = _plan(ironing_excess_list=frappe.as_json({"SE-OLD": OLD, "SE-NEW": NEW}))
		groups = {group["key"]: group for group in get_linked_documents(plan)}
		dates = {row["name"]: row["date"] for row in groups["ironing_excess_list"]["documents"]}
		self.assertEqual(dates, {"SE-OLD": OLD, "SE-NEW": NEW["datetime"]})

	def test_new_ironing_entry_starts_without_dc_and_keeps_other_markers(self):
		plan = _plan(ironing_excess_list=frappe.as_json({"SE-OLD": OLD, "SE-NEW": NEW}))
		_update_ironing_excess(plan, _source("SE-ADD"), cancelled=False)
		stored = frappe.parse_json(plan.ironing_excess_list)
		self.assertEqual(stored["SE-ADD"]["dc"], "")
		self.assertTrue(stored["SE-ADD"]["datetime"])
		self.assertEqual(stored["SE-OLD"], OLD)
		self.assertEqual(stored["SE-NEW"], NEW)

	@patch("essdee_yrp.finishing.old_lot.apply_auto_fp_status")
	@patch("essdee_yrp.finishing.old_lot.frappe.get_doc")
	def test_lot_transfer_entry_uses_new_shape_and_cancel_removes_it(self, get_doc, _status):
		plan = _plan(lot_transfer_list=frappe.as_json({"LT-OLD": NEW}))
		get_doc.side_effect = _plan_or_real(plan)
		transfer = _source("LT-1", finishing_plan="FP-1")
		_apply_lot_transfer_to_finishing(transfer, cancelled=False)
		stored = frappe.parse_json(plan.lot_transfer_list)
		self.assertEqual(stored["LT-1"]["dc"], "")
		self.assertEqual(stored["LT-OLD"], NEW)
		_apply_lot_transfer_to_finishing(transfer, cancelled=True)
		self.assertNotIn("LT-1", frappe.parse_json(plan.lot_transfer_list))

	@patch("essdee_yrp.finishing.rebuild.frappe.get_doc")
	@patch("essdee_yrp.finishing.rebuild.frappe.db.get_value", return_value=1)
	def test_rebuild_reads_both_shapes_and_preserves_dc(self, _get_value, get_doc):
		raw = frappe.as_json({"SRC-OLD": OLD, "SRC-NEW": NEW})
		plan = _plan(ironing_excess_list=raw, lot_transfer_list=raw)
		get_doc.side_effect = lambda doctype, name: _source(name)
		key = ("VAR-1", (("major_colour", "Blue"),))
		items = {key: {"ironing_excess": 0, "lot_transferred": 0}}
		_apply_ironing_excess(plan, items)
		_apply_lot_transfers(plan, items)
		self.assertEqual(items[key], {"ironing_excess": 8, "lot_transferred": 8})
		self.assertEqual(plan.ironing_excess_list, raw)
		self.assertEqual(plan.lot_transfer_list, raw)

	def _patch_plan(self, plan, list_key):
		return (
			patch.object(source_entries, "get_source_plan", return_value=(plan.name, list_key)),
			patch.object(source_entries.frappe, "get_doc", side_effect=_plan_or_real(plan)),
		)

	def test_dc_submit_writes_dc_and_cancel_clears_it(self):
		plan = _plan(ironing_excess_list=frappe.as_json({"SE-1": OLD, "SE-2": NEW}))
		delivery_challan = frappe._dict(name="DC-9", finishing_source_entry="SE-1")
		source_plan, get_doc = self._patch_plan(plan, "ironing_excess_list")
		with source_plan, get_doc:
			source_entries.set_entry_dc(delivery_challan, cancelled=False)
			self.assertEqual(
				frappe.parse_json(plan.ironing_excess_list)["SE-1"], {"datetime": OLD, "dc": "DC-9"}
			)
			self.assertEqual(frappe.parse_json(plan.ironing_excess_list)["SE-2"], NEW)
			with self.assertRaises(frappe.ValidationError):
				source_entries.set_entry_dc(
					frappe._dict(name="DC-10", finishing_source_entry="SE-1"), cancelled=False
				)
			source_entries.set_entry_dc(
				frappe._dict(name="DC-OTHER", finishing_source_entry="SE-1"), cancelled=True
			)
			self.assertEqual(frappe.parse_json(plan.ironing_excess_list)["SE-1"]["dc"], "DC-9")
			source_entries.set_entry_dc(delivery_challan, cancelled=True)
			self.assertEqual(frappe.parse_json(plan.ironing_excess_list)["SE-1"], {"datetime": OLD, "dc": ""})

	def test_dc_without_source_entry_is_ignored(self):
		with patch.object(source_entries, "get_source_plan") as get_source_plan:
			source_entries.set_entry_dc(frappe._dict(name="DC-1"), cancelled=False)
		get_source_plan.assert_not_called()

	@patch("essdee_yrp.finishing.web_entries.get_entry_matrix", return_value={})
	@patch("essdee_yrp.finishing.web_entries.transactions.create_delivery_challan", return_value="DC-5")
	def test_create_dc_passes_source_entry_and_rejects_used_entries(self, create, _matrix):
		plan = _plan(
			lot_transfer_list=frappe.as_json({"LT-1": {"datetime": OLD, "dc": ""}, "LT-2": NEW}),
			item="ITEM",
			work_order="WO-1",
			lot="LOT-1",
		)
		values = {"from_location": "SUP", "actual_date": "2026-10-23", "selected_type": "balance"}
		result = web_entries.create_delivery_challan(plan, {**values, "source_entry": "LT-1"})
		self.assertEqual(result, {"doctype": "YRP Delivery Challan", "name": "DC-5"})
		self.assertEqual(create.call_args.kwargs["source_entry"], "LT-1")
		for used in ("LT-2", "LT-MISSING"):
			with self.assertRaises(frappe.ValidationError):
				web_entries.create_delivery_challan(plan, {**values, "source_entry": used})
		web_entries.create_delivery_challan(plan, values)
		self.assertIsNone(create.call_args.kwargs["source_entry"])

	def test_entry_quantities_follow_create_dc_matrix_keys(self):
		context = {"is_set_item": False, "pack_attr": "Colour", "primary_attr": "Size", "set_attr": None}
		rows = [
			frappe._dict(item="VAR-S", qty=3, set_combination='{"major_colour":"Blue"}'),
			frappe._dict(item="VAR-S", qty=2, set_combination='{"major_colour":"Blue"}'),
			frappe._dict(item="VAR-M", qty=1, set_combination='{"major_colour":"Blue"}'),
		]
		attributes = {"VAR-S": {"Colour": "Blue", "Size": "S"}, "VAR-M": {"Colour": "Blue", "Size": "M"}}
		with patch("essdee_yrp.finishing.views.get_variant_attr_details", side_effect=attributes.get):
			quantities = source_entries.get_entry_quantities(None, rows, context)
		self.assertEqual(quantities, {"Blue": {"S": 5, "M": 1}})

	@patch("essdee_yrp.migration.mark_finishing_entries_dc_done.frappe.db.commit")
	def test_mark_script_is_idempotent(self, _commit):
		stored = {
			"FP-1": {
				"ironing_excess_list": frappe.as_json({"SE-1": OLD, "SE-2": NEW}),
				"lot_transfer_list": frappe.as_json({"LT-1": OLD}),
			},
			"FP-2": {"ironing_excess_list": None, "lot_transfer_list": "{}"},
		}

		def get_all(_doctype, **_kwargs):
			return [frappe._dict(name=name, **fields) for name, fields in stored.items()]

		def set_value(_doctype, name, updates, update_modified=True):
			self.assertFalse(update_modified)
			stored[name].update(updates)

		with (
			patch.object(mark_finishing_entries_dc_done.frappe, "get_all", side_effect=get_all),
			patch.object(mark_finishing_entries_dc_done.frappe.db, "set_value", side_effect=set_value),
		):
			dry = mark_finishing_entries_dc_done.run(verbose=0)
			self.assertEqual(stored["FP-1"]["lot_transfer_list"], frappe.as_json({"LT-1": OLD}))
			first = mark_finishing_entries_dc_done.run(apply=1, verbose=0)
			second = mark_finishing_entries_dc_done.run(apply=1, verbose=0)

		self.assertEqual(dry["plans_changed"], 1)
		self.assertEqual(first["ironing_excess_list_converted"], 1)
		self.assertEqual(first["lot_transfer_list_converted"], 1)
		self.assertEqual(second["plans_changed"], 0)
		self.assertEqual(second["ironing_excess_list_already_new"], 2)
		ironing = frappe.parse_json(stored["FP-1"]["ironing_excess_list"])
		self.assertEqual(ironing["SE-1"], {"datetime": OLD, "dc": "existing"})
		self.assertEqual(ironing["SE-2"], NEW)
		self.assertEqual(frappe.parse_json(stored["FP-1"]["lot_transfer_list"])["LT-1"]["dc"], "existing")
