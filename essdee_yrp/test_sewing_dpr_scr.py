import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan import sd_yrp_sewing_plan as api


class TestSewingDprScrParity(IntegrationTestCase):
	"""Set-item part split, FI scope and Lot/Item scope match production_api's DPR and SCR."""

	def setUp(self):
		super().setUp()
		point = f"sewing_dpr_scr_{frappe.generate_hash(length=10)}"
		frappe.db.savepoint(point)
		self.addCleanup(frappe.db.rollback, save_point=point)
		source = frappe.db.sql(
			"""select lot.item, lot.production_detail, ipd.set_item_attribute
			from `tabSD YRP Lot` lot
			join `tabYRP Item Production Detail` ipd on ipd.name = lot.production_detail
			join `tabSD YRP Sewing Plan` sp on sp.lot = lot.name
			join `tabSD YRP Sewing Plan Order Detail` d on d.parent = sp.name
			where ipd.is_set_item = 1 and d.item_variant is not null
			group by lot.name having count(distinct d.item_variant) > 1
			order by lot.name limit 1""",
			as_dict=True,
		)
		self.assertTrue(source, "Parity fixtures require one installed set-item Lot")
		self.source = source[0]
		self.top, self.bottom = self._part_variants()
		self.station = frappe.get_all("YRP Work Station", pluck="name", limit=1)[0]
		self.received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
		self.supplier = self._supplier()
		self.lot = self._lot()

	def _part_variants(self):
		rows = frappe.db.sql(
			"""select d.item_variant, d.set_combination, attr.attribute_value part
			from `tabSD YRP Sewing Plan Order Detail` d
			join `tabSD YRP Sewing Plan` sp on sp.name = d.parent
			join `tabSD YRP Lot` lot on lot.name = sp.lot
			join `tabItem Variant Attribute` attr on attr.parent = d.item_variant and attr.attribute = %s
			where lot.production_detail = %s order by d.name""",
			(self.source.set_item_attribute, self.source.production_detail),
			as_dict=True,
		)
		combination = frappe.parse_json(rows[0].set_combination)
		by_part = {}
		for row in rows:
			by_part.setdefault(row.part, row)
		major = by_part.pop(combination["major_part"])
		self.assertTrue(by_part, "Set-item fixture needs a non-major part variant")
		return major, next(iter(by_part.values()))

	def _supplier(self):
		group = frappe.get_all("Supplier Group", pluck="name", limit=1)[0]
		return (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": f"Parity Unit {frappe.generate_hash(length=10)}",
					"supplier_group": group,
					"supplier_type": "Company",
				}
			)
			.insert()
			.name
		)

	def _lot(self):
		return (
			frappe.get_doc(
				{
					"doctype": "SD YRP Lot",
					"lot_name": f"PARITY-{frappe.generate_hash(length=10)}",
					"item": self.source.item,
					"production_detail": self.source.production_detail,
				}
			)
			.insert()
			.name
		)

	def _plan(self, rows, fi_date="2090-01-10", lot=None):
		series = frappe.get_meta("SD YRP Sewing Plan").get_field("naming_series").options.split("\n")[0]
		return frappe.get_doc(
			{
				"doctype": "SD YRP Sewing Plan",
				"naming_series": series,
				"supplier": self.supplier,
				"lot": lot or self.lot,
				"item": self.source.item,
				"sewing_plan_order_details": [
					{
						"item_variant": variant.item_variant,
						"set_combination": variant.set_combination,
						"quantity": quantity,
						"fi_date": fi_date,
					}
					for variant, quantity in rows
				],
			}
		).insert()

	def _entry(self, plan, stage, date, rows):
		return frappe.get_doc(
			{
				"doctype": "SD YRP Sewing Plan Entry Detail",
				"sewing_plan": plan.name,
				"input_type": stage,
				"entry_date": date,
				"work_station": self.station,
				"received_type": self.received_type,
				"sewing_plan_details": [
					{"item_variant": v.item_variant, "set_combination": v.set_combination, "quantity": q}
					for v, q in rows
				],
			}
		).insert()

	def _dpr_rows(self, report):
		return [
			(stage, lot, colour["part"], colour["total"])
			for stage, by_lot in report["dpr_data"].items()
			for lot, lot_data in by_lot.items()
			for received in lot_data["details"].values()
			for colours in received.values()
			for colour in colours.values()
		]

	def test_scr_splits_a_set_item_part_wise_with_type_totals(self):
		plan = self._plan([(self.top, 40), (self.bottom, 30)])
		self._entry(plan, "Input Qty", "2090-01-01", [(self.top, 10), (self.bottom, 7)])
		result = api.get_scr_data(self.supplier, self.lot)
		self.assertTrue(result["is_set_item"])
		self.assertEqual(result["set_attr"], self.source.set_item_attribute)
		major_colour = frappe.parse_json(self.bottom.set_combination)["major_colour"]
		self.assertEqual(len(result["colours"]), 2)
		top, bottom = (result["data"][key] for key in result["colours"])
		self.assertEqual(top["part"], self.top.part)
		self.assertEqual(bottom["part"], self.bottom.part)
		self.assertTrue(bottom["colour"].endswith(f"({major_colour})"))
		self.assertEqual(
			{h: top["type_wise_total"][h] for h in ("Order Qty", "Input Qty", "Input Qty Balance")},
			{"Order Qty": 40, "Input Qty": 10, "Input Qty Balance": -30},
		)
		self.assertEqual(
			{h: bottom["type_wise_total"][h] for h in ("Order Qty", "Input Qty", "Input Qty Balance")},
			{"Order Qty": 30, "Input Qty": 7, "Input Qty Balance": -23},
		)

	def test_dpr_set_item_rows_carry_part_and_totals(self):
		plan = self._plan([(self.top, 40), (self.bottom, 30)])
		self._entry(plan, "Input Qty", "2090-01-01", [(self.top, 10), (self.bottom, 7)])
		report = api.get_sewing_plan_dpr_data(self.supplier, "2090-01-01")
		self.assertEqual(
			sorted(self._dpr_rows(report)),
			sorted(
				[("Input Qty", self.lot, self.top.part, 10), ("Input Qty", self.lot, self.bottom.part, 7)]
			),
		)
		self.assertTrue(report["dpr_data"]["Input Qty"][self.lot]["is_set_item"])

	def test_pending_fi_checks_every_plan_of_a_reported_lot(self):
		top_plan = self._plan([(self.top, 40)])
		self._plan([(self.bottom, 30)], fi_date=None)
		self._entry(top_plan, "Input Qty", "2090-01-01", [(self.top, 10)])
		report = api.get_sewing_plan_dpr_data(self.supplier, "2090-01-01")
		self.assertTrue(report["blocked"])
		self.assertEqual(report["dpr_data"], {})
		self.assertEqual([row["part"] for row in report["pending_fi"]], [self.bottom.part])

	def test_summary_reports_unblocked_dates_and_lists_blocked_ones(self):
		plan = self._plan([(self.top, 40)])
		self._entry(plan, "Input Qty", "2090-01-01", [(self.top, 10)])
		other_lot = self._lot()
		blocked = self._plan([(self.top, 20)], fi_date=None, lot=other_lot)
		self._entry(blocked, "Input Qty", "2090-01-02", [(self.top, 5)])
		result = api.get_sewing_plan_dpr_summary(self.supplier, "2090-01-01", "2090-01-02")
		self.assertTrue(result["blocked"])
		self.assertEqual([row["lot"] for row in result["pending_fi"]], [other_lot])
		self.assertEqual([row["date"] for row in result["reports"]], ["2090-01-01"])
		self.assertEqual(self._dpr_rows(result["reports"][0]), [("Input Qty", self.lot, self.top.part, 10)])

	def test_summary_accepts_lot_or_item_without_dates(self):
		plan = self._plan([(self.top, 40)])
		self._entry(plan, "Input Qty", "2090-01-01", [(self.top, 10)])
		self._entry(plan, "Line Output", "2090-01-03", [(self.top, 6)])
		other = self._plan([(self.top, 20)], lot=self._lot())
		self._entry(other, "Input Qty", "2090-01-02", [(self.top, 99)])
		by_lot = api.get_sewing_plan_dpr_summary(self.supplier, lot=self.lot)
		self.assertEqual([row["date"] for row in by_lot["reports"]], ["2090-01-01", "2090-01-03"])
		by_item = api.get_sewing_plan_dpr_summary(self.supplier, item=self.source.item)
		self.assertEqual(len(by_item["reports"]), 3)
		daily = api.get_sewing_plan_dpr_data(self.supplier, "2090-01-02", lot=self.lot)
		self.assertEqual(daily["dpr_data"], {})
		with self.assertRaises(frappe.ValidationError):
			api.get_sewing_plan_dpr_summary(self.supplier)
		with self.assertRaises(frappe.ValidationError):
			api.get_sewing_plan_dpr_summary(self.supplier, "2090-01-01", None, lot=self.lot)
