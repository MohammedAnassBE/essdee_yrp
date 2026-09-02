import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import ui_registry
from yrp.yrp.api.ui_metrics import get_calculation_registry, get_metric_registry


class TestEssdeeUIRegistry(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_lot_entries_are_contributed_through_hooks(self):
		metrics = get_metric_registry()
		calculations = get_calculation_registry()
		self.assertIn("open_lots", metrics)
		self.assertIn("active_lots", metrics)
		self.assertIn("lot_balance", calculations)
		self.assertTrue(metrics["open_lots"]["home_queue"])

	def test_active_lots_goto_matches_the_computed_names(self):
		spec = ui_registry.get_metrics()["active_lots"]
		names = ui_registry._active_lot_names()
		self.assertEqual(spec["compute"](), len(names))
		self.assertEqual(
			spec["goto"](),
			{"doctype": 'SD YRP Lot', "filters": [["name", "in", names]]},
		)

	def test_lot_balance_rejects_a_dangling_lot(self):
		with self.assertRaises(frappe.DoesNotExistError):
			ui_registry._calc_lot_balance({"lot": "NO-SUCH-LOT-XXXXX"})
