from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.hooks import yrp_rework_received_type
from essdee_yrp.rework_work_order import is_rework_received_type


class TestReworkReceivedTypes(TestCase):
	"""Like production_api, only Mistake and Rejected Received Types are reworked."""

	def classify(self, received_type_class):
		with patch("essdee_yrp.rework_work_order.frappe.get_cached_value", return_value=received_type_class):
			return is_rework_received_type("RT")

	def test_mistake_and_rejected_are_offered_accepted_types_are_not(self):
		self.assertTrue(self.classify("Mistake"))
		self.assertTrue(self.classify("Rejected"))
		self.assertFalse(self.classify("Accepted"))

	def test_unclassified_type_defers_to_yrp(self):
		self.assertIsNone(self.classify(None))

	def test_hook_is_registered(self):
		self.assertEqual(yrp_rework_received_type, ["essdee_yrp.rework_work_order.is_rework_received_type"])
