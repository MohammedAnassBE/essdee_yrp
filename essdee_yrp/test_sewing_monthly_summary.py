from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.sewing.read_models import get_monthly_summary_data, get_monthly_summary_print_data


class TestSewingMonthlySummaryLotFilter(IntegrationTestCase):
	"""Monthly Summary restricted to selected lots, checked against migrated entries."""

	def setUp(self):
		frappe.set_user("Administrator")

	def _sample(self):
		sample = frappe.db.sql(
			"""
				select sp.supplier, entry.input_type, min(entry.entry_date) from_date,
					max(entry.entry_date) to_date, count(distinct sp.lot) lot_count
				from `tabSD YRP Sewing Plan Entry Detail` entry
				join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
				where ifnull(sp.item, '') != '' and ifnull(sp.lot, '') != ''
				group by sp.supplier, entry.input_type
				having lot_count >= 3
				order by count(*) desc
				limit 1
			""",
			as_dict=True,
		)
		if not sample:
			self.skipTest("Lot filter parity requires entries across three lots")
		sample = sample[0]
		lots = frappe.db.sql_list(
			"""
				select distinct sp.lot
				from `tabSD YRP Sewing Plan Entry Detail` entry
				join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
				where sp.supplier = %s and entry.input_type = %s
				order by sp.lot
				limit 2
			""",
			(sample.supplier, sample.input_type),
		)
		return sample, lots

	def _expected_total(self, sample, lots=None):
		lot_condition = "and sp.lot in %(lots)s" if lots else ""
		return flt(
			frappe.db.sql(
				f"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSD YRP Sewing Plan Detail` detail
					join `tabSD YRP Sewing Plan Entry Detail` entry on entry.name = detail.parent
					join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
					where sp.supplier = %(supplier)s and entry.input_type = %(input_type)s
						and entry.entry_date between %(from_date)s and %(to_date)s
						and ifnull(sp.item, '') != '' {lot_condition}
				""",
				{**sample, "lots": tuple(lots or ())},
			)[0][0]
		)

	def _summary(self, sample, lots=None):
		return get_monthly_summary_data(
			sample.supplier, sample.from_date, sample.to_date, sample.input_type, lots=lots
		)

	def test_selected_lots_limit_rows_and_totals(self):
		sample, lots = self._sample()
		filtered = self._summary(sample, frappe.as_json(lots))
		expected = self._expected_total(sample, lots)
		self.assertAlmostEqual(flt(filtered["grand_total"]["total"]), expected, places=3)
		self.assertAlmostEqual(sum(flt(row["total"]) for row in filtered["rows"]), expected, places=3)
		lot_items = set(
			frappe.get_all(
				"SD YRP Sewing Plan", filters={"supplier": sample.supplier, "lot": ["in", lots]}, pluck="item"
			)
		)
		self.assertTrue(all(style.split(" (")[0] in lot_items for style in filtered["styles"]))
		self.assertLess(expected, self._expected_total(sample))

	def test_empty_lot_selection_keeps_all_lots(self):
		sample, _lots = self._sample()
		baseline = self._summary(sample)
		self.assertEqual(self._summary(sample, "[]"), baseline)
		self.assertEqual(self._summary(sample, []), baseline)
		self.assertAlmostEqual(flt(baseline["grand_total"]["total"]), self._expected_total(sample), places=3)

	def test_print_data_honours_selected_lots(self):
		sample, lots = self._sample()
		form = {
			"supplier": sample.supplier,
			"start_date": str(sample.from_date),
			"end_date": str(sample.to_date),
			"input_type": sample.input_type,
			"lots": frappe.as_json(lots),
		}
		with patch.dict(frappe.local.form_dict, form, clear=True):
			data = get_monthly_summary_print_data()
		self.assertEqual(data["lots"], lots)
		self.assertEqual(
			flt(frappe.utils.cstr(data["grand_total"]["total"]).replace(",", "")),
			self._expected_total(sample, lots),
		)

	def test_grn_mode_honours_selected_lots_and_keeps_all_when_empty(self):
		sample = frappe.db.sql(
			"""
				select grn.supplier, min(grn.posting_date) from_date, max(grn.posting_date) to_date
				from `tabYRP Goods Received Note` grn
				where grn.docstatus = 1 and grn.against = 'YRP Work Order' and ifnull(grn.lot, '') != ''
					and grn.against_id in (
						select plan.work_order from `tabSD YRP Sewing Plan` plan where plan.supplier = grn.supplier
					)
				group by grn.supplier
				having count(distinct grn.lot) >= 3
				order by count(*) desc
				limit 1
			""",
			as_dict=True,
		)
		if not sample:
			self.skipTest("GRN lot filter parity requires sewing GRNs across three lots")
		sample = sample[0]
		lots = frappe.db.sql_list(
			"""
				select distinct lot from `tabYRP Goods Received Note`
				where supplier = %s and docstatus = 1 and against = 'YRP Work Order' and ifnull(lot, '') != ''
				order by lot limit 2
			""",
			sample.supplier,
		)

		def expected(selected=None):
			lot_condition = "and grn.lot in %(lots)s" if selected else ""
			return flt(
				frappe.db.sql(
					f"""
						select coalesce(sum(item.quantity), 0)
						from `tabYRP Goods Received Note Item` item
						join `tabYRP Goods Received Note` grn on grn.name = item.parent
						where grn.supplier = %(supplier)s and grn.docstatus = 1 and grn.against = 'YRP Work Order'
							and grn.posting_date between %(from_date)s and %(to_date)s
							and grn.against_id in (
								select work_order from `tabSD YRP Sewing Plan` where supplier = %(supplier)s
							) {lot_condition}
					""",
					{**sample, "lots": tuple(selected or ())},
				)[0][0]
			)

		def summary(selected):
			return get_monthly_summary_data(
				sample.supplier, sample.from_date, sample.to_date, show_grn=1, lots=selected
			)

		self.assertAlmostEqual(flt(summary([])["grand_total"]["total"]), expected(), places=3)
		self.assertAlmostEqual(flt(summary(lots)["grand_total"]["total"]), expected(lots), places=3)
		self.assertLess(expected(lots), expected())
