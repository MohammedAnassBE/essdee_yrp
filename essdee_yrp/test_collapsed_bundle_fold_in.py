import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.utils import get_variant_attr_details

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_movement_ledger.sd_yrp_cut_bundle_movement_ledger import (
	cancel_collapse_bundles,
	create_new_collapsed_bundle,
	get_collapsed_previous_cbm_list,
	get_collapsed_variant,
	on_submit_collapsed_bundles,
)

LEDGER = "SD YRP Cut Bundle Movement Ledger"
POSTING_DATE = "2099-01-01"


class TestCollapsedBundleFoldIn(IntegrationTestCase):
	"""Exact bundles arriving after the first collapse join the collapsed balance on the next GRN."""

	panel = "Bottom Left,Bottom Right"

	def setUp(self):
		frappe.db.savepoint("collapsed_bundle_fold_in")
		self.addCleanup(frappe.db.rollback, save_point="collapsed_bundle_fold_in")
		row = frappe.db.sql(
			"""
			SELECT cbml.lot, cbml.item, cbml.size, cbml.colour, cbml.supplier
			FROM `tabSD YRP Cut Bundle Movement Ledger` cbml
			JOIN `tabSD YRP Lot` lot ON lot.name = cbml.lot AND lot.production_detail IS NOT NULL
			WHERE cbml.collapsed_bundle = 0 AND cbml.is_cancelled = 0 AND cbml.panel = %s
			LIMIT 1
			""",
			self.panel,
			as_dict=True,
		)
		vouchers = frappe.get_all("YRP Goods Received Note", filters={"docstatus": 1}, pluck="name", limit=5)
		if not row or len(vouchers) < 5:
			self.skipTest(f"No {self.panel} exact-bundle oracle is available")
		row = attribute_db.business_values(row)[0]
		self.lot, self.item, self.location = row.lot, row.item, row.supplier
		self.size, self.colour = _attribute_value(row.size), _attribute_value(row.colour)
		self.vouchers = vouchers
		self.combination = {"major_colour": f"Fold-In {frappe.generate_hash(length=8)}"}
		ipd = frappe.get_doc(
			"YRP Item Production Detail", attribute_db.get_value("SD YRP Lot", self.lot, "production_detail")
		)
		fields = [
			"primary_item_attribute",
			"packing_attribute",
			"stiching_attribute",
			"stiching_in_stage",
			"dependent_attribute",
		]
		self.attrs = dict(
			zip(
				["primary", "pack", "stich", "stich_stage", "stage"],
				attribute_db.get_value("YRP Item Production Detail", ipd.name, fields),
				strict=True,
			)
		)
		quantities = {
			_attribute_value(detail.stiching_attribute_value): flt(detail.quantity)
			for detail in ipd.stiching_item_details
		}
		self.panels = {}
		for panel in self.panel.split(","):
			if panel not in quantities:
				self.skipTest(f"Panel {panel} is not configured on the oracle IPD")
			variant = get_collapsed_variant(self.item, ipd, self.attrs, self.size, self.colour, panel)
			self.panels[panel] = frappe._dict(
				variant=variant,
				attributes=get_variant_attr_details(variant),
				quantity=quantities[panel],
			)
		self.sequence = 990000 + frappe.db.count(LEDGER)

	def exact_bundles(self, posting_time, quantities):
		names = []
		for quantity in quantities:
			self.sequence += 1
			doc = frappe.get_doc(
				{
					"doctype": LEDGER,
					"lot": self.lot,
					"supplier": self.location,
					"lay_no": self.sequence,
					"bundle_no": self.sequence,
					"panel": self.panel,
					"shade": "TEST",
					"collapsed_bundle": 0,
					"item": self.item,
					"voucher_type": "YRP Goods Received Note",
					"voucher_no": self.vouchers[4],
					"size": self.size,
					"colour": self.colour,
					"quantity": quantity,
					"quantity_after_transaction": quantity,
					"set_combination": json.dumps(self.combination),
					"posting_date": POSTING_DATE,
					"posting_time": posting_time,
				}
			)
			doc.flags.ignore_permissions = 1
			doc.set_posting_datetime()
			doc.set_key()
			doc.insert(ignore_permissions=True)
			doc.submit()
			names.append(doc.name)
		return names

	def voucher(self, index, posting_time):
		return frappe._dict(
			doctype="YRP Goods Received Note",
			name=self.vouchers[index],
			posting_date=POSTING_DATE,
			posting_time=posting_time,
		)

	def consume(self, voucher, quantity):
		"""Mirror a Stitching GRN: each panel leaves the location as collapsed stock."""
		opening = {}
		for panel in self.panels.values():
			opening = on_submit_collapsed_bundles(
				voucher,
				voucher.doctype,
				voucher.name,
				self.location,
				panel.variant,
				self.combination,
				panel.attributes,
				self.attrs,
				self.item,
				quantity * panel.quantity,
				opening,
				self.lot,
			)
		for key, values in opening.items():
			create_new_collapsed_bundle(
				key, values["bundle_qty"], values["qty"], self.location, voucher, {}, self.attrs
			)

	def cancel(self, voucher):
		for panel in self.panels.values():
			cancel_collapse_bundles(
				voucher,
				panel.variant,
				self.combination,
				0,
				self.location,
				panel.attributes,
				self.attrs,
				self.item,
				self.lot,
			)

	def balances(self, posting_time="23:59:59"):
		"""Collapsed balance per panel, in pieces."""
		result = []
		for panel in self.panels.values():
			rows = get_collapsed_previous_cbm_list(
				POSTING_DATE,
				posting_time,
				self.location,
				panel.variant,
				lot=self.lot,
				set_combination=self.combination,
			)
			result.append(flt(rows[0].quantity_after_transaction) / panel.quantity if rows else 0)
		return result

	def collapsed_flags(self, names):
		return [frappe.db.get_value(LEDGER, name, "is_collapsed") for name in names]

	def first_cycle(self):
		first_batch = self.exact_bundles("01:00:00", [6, 4])
		first_grn = self.voucher(0, "02:00:00")
		self.consume(first_grn, 3)
		second_batch = self.exact_bundles("03:00:00", [5, 2])
		return first_batch, first_grn, second_batch

	def test_later_exact_bundles_fold_into_the_next_grn(self):
		first_batch, _first_grn, second_batch = self.first_cycle()
		self.assertEqual(self.balances(), [7] * len(self.panels))
		self.assertEqual(self.collapsed_flags(second_batch), [0, 0])

		self.consume(self.voucher(1, "04:00:00"), 12)

		self.assertEqual(self.balances(), [2] * len(self.panels))
		self.assertEqual(self.collapsed_flags(first_batch + second_batch), [1, 1, 1, 1])

	def test_cancelling_the_second_grn_undoes_only_its_fold(self):
		first_batch, _first_grn, second_batch = self.first_cycle()
		second_grn = self.voucher(1, "04:00:00")
		self.consume(second_grn, 12)

		self.cancel(second_grn)

		self.assertEqual(self.balances(), [7] * len(self.panels))
		self.assertEqual(self.collapsed_flags(first_batch), [1, 1])
		self.assertEqual(self.collapsed_flags(second_batch), [0, 0])
		self.assertFalse(
			frappe.db.exists(
				LEDGER,
				{
					"voucher_no": second_grn.name,
					"set_combination": ["like", f"%{self.combination['major_colour']}%"],
					"is_cancelled": 0,
				},
			)
		)

	def test_cancel_is_last_in_first_out(self):
		first_batch, first_grn, second_batch = self.first_cycle()
		second_grn = self.voucher(1, "04:00:00")
		self.consume(second_grn, 12)

		with self.assertRaisesRegex(frappe.ValidationError, "Cancel the later collapsed-bundle movement"):
			self.cancel(first_grn)
		self.cancel(second_grn)
		self.cancel(first_grn)

		self.assertEqual(self.balances(), [0] * len(self.panels))
		self.assertEqual(self.collapsed_flags(first_batch + second_batch), [0, 0, 0, 0])

	def test_genuine_shortage_still_throws(self):
		self.first_cycle()
		with self.assertRaisesRegex(frappe.ValidationError, "Collapsed-bundle stock is not available"):
			self.consume(self.voucher(1, "04:00:00"), 15)

	def test_backdated_grn_does_not_fold_bundles_that_arrived_later(self):
		_first_batch, _first_grn, second_batch = self.first_cycle()
		backdated = self.voucher(2, "02:30:00")
		frappe.db.savepoint("before_backdated_shortage")
		with self.assertRaisesRegex(frappe.ValidationError, "Collapsed-bundle stock is not available"):
			self.consume(backdated, 8)
		frappe.db.rollback(save_point="before_backdated_shortage")

		self.consume(backdated, 5)

		self.assertEqual(self.balances("02:59:59"), [2] * len(self.panels))
		self.assertEqual(self.collapsed_flags(second_batch), [0, 0])
		self.consume(self.voucher(3, "04:00:00"), 9)
		self.assertEqual(self.balances(), [0] * len(self.panels))
		self.assertEqual(self.collapsed_flags(second_batch), [1, 1])


class TestCollapsedBundleFoldInPanelQuantity(TestCollapsedBundleFoldIn):
	"""Same flow for a single panel cut twice per piece, so collapsed stock is in panels."""

	panel = "Sleeve"

	def setUp(self):
		super().setUp()
		if self.panels["Sleeve"].quantity == 1:
			self.skipTest("The oracle IPD cuts Sleeve once per piece")
