import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import add_ppo_lot_qty, delete_ppo_lot_qty


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
