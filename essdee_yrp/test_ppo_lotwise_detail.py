import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import add_ppo_lot_qty, delete_ppo_lot_qty
from essdee_yrp.patches import backfill_ppo_ordered_lot_links


class TestProductionOrderLotQuantity(IntegrationTestCase):
	"""Lot rows on the Production Order's Lotwise Ordered Detail."""

	def setUp(self):
		suffix = frappe.generate_hash(length=8)
		self.production_order = f"_Test PPO Lotwise {suffix}"
		self.lot = (
			frappe.get_doc(
				{
					"doctype": "SD YRP Lot",
					"lot_name": f"_Test Lotwise {suffix}",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.variant = frappe.db.get_value("Item", {"variant_of": ["is", "set"]}, "name")

	def get_rows(self):
		return frappe.get_all(
			"YRP Production Ordered Detail",
			filters={"parent": self.production_order},
			fields=["lot", "reference_doctype", "reference_name", "quantity"],
		)

	def insert_row(self, **values):
		row = frappe.new_doc("YRP Production Ordered Detail")
		row.update(
			{
				"parent": self.production_order,
				"parenttype": "YRP Production Order",
				"parentfield": "production_ordered_details",
				"item_variant": self.variant,
				"quantity": 5,
				**values,
			}
		)
		row.db_insert()

	def test_lot_rows_carry_direct_and_dynamic_lot_links(self):
		add_ppo_lot_qty(self.production_order, self.lot, [frappe._dict(item_variant=self.variant, qty=7)])

		self.assertEqual(
			self.get_rows(),
			[
				{
					"lot": self.lot,
					"reference_doctype": "SD YRP Lot",
					"reference_name": self.lot,
					"quantity": 7,
				}
			],
		)

	def test_delete_removes_migrated_rows_with_only_the_direct_lot_link(self):
		self.insert_row(lot=self.lot)
		self.insert_row(reference_doctype="SD YRP Lot", reference_name=self.lot)

		delete_ppo_lot_qty(self.production_order, self.lot)

		self.assertEqual(self.get_rows(), [])

	def test_backfill_links_migrated_rows_and_drops_duplicates_of_resaved_lots(self):
		other = (
			frappe.get_doc(
				{
					"doctype": "SD YRP Lot",
					"lot_name": f"_Test Lotwise Other {frappe.generate_hash(length=8)}",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.insert_row(lot=self.lot, reference_doctype="", reference_name="", quantity=5)
		self.insert_row(lot="", reference_doctype="SD YRP Lot", reference_name=self.lot, quantity=5)
		self.insert_row(lot=other, quantity=3)

		backfill_ppo_ordered_lot_links.execute()
		backfill_ppo_ordered_lot_links.execute()

		rows = sorted(self.get_rows(), key=lambda row: row.lot or "")
		expected = sorted(
			[
				{
					"lot": self.lot,
					"reference_doctype": "SD YRP Lot",
					"reference_name": self.lot,
					"quantity": 5,
				},
				{"lot": other, "reference_doctype": "SD YRP Lot", "reference_name": other, "quantity": 3},
			],
			key=lambda row: row["lot"],
		)
		self.assertEqual(rows, expected)
