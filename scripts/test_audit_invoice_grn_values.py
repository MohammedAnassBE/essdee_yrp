import unittest

from audit_invoice_grn_values import compare_physical_projection


class InvoiceGRNAuditTest(unittest.TestCase):
	def fixture(self):
		original = [dict(invoice='PI', item='Physical', uom='Nos', lot='Lot',
			set_combination='{}', quantity='2.0005', rate=3)]
		physical = [dict(invoice='PI', item='Physical', uom='Nos', lot='Lot',
			set_combination={}, qty='2.0005', actual_qty='2.0005', actual_rate=3,
			rate=5, amount='10.0025', essdee_group_key='GROUP', essdee_rate_weight=1)]
		commercial = [dict(invoice='PI', group_key='GROUP', qty='2.0005', rate=5)]
		return original, physical, commercial

	def test_exact_physical_and_commercial_projection_passes(self):
		self.assertEqual(compare_physical_projection(*self.fixture())['mismatch_count'], 0)

	def test_rounding_physical_quantity_is_not_accepted(self):
		original, physical, commercial = self.fixture()
		physical[0]['qty'] = '2.001'
		result = compare_physical_projection(original, physical, commercial)
		self.assertTrue(any(r['reason'] == 'Direct GRN quantity changed' for r in result['failures']))

	def test_wrong_variant_is_not_hidden_by_matching_total(self):
		original, physical, commercial = self.fixture()
		physical[0]['item'] = 'Billing Item'
		self.assertGreater(compare_physical_projection(original, physical, commercial)['mismatch_count'], 0)

	def test_rate_weight_original_rate_and_missing_group_are_checked(self):
		for field, value in [('essdee_rate_weight', 2), ('actual_rate', 4), ('essdee_group_key', 'Missing')]:
			with self.subTest(field=field):
				original, physical, commercial = self.fixture()
				physical[0][field] = value
				self.assertGreater(compare_physical_projection(original, physical, commercial)['mismatch_count'], 0)

	def test_legitimate_unlinked_draft_does_not_need_invented_physical_rows(self):
		_, _, commercial = self.fixture()
		self.assertEqual(compare_physical_projection([], [], commercial, {'PI'})['mismatch_count'], 0)
		self.assertGreater(compare_physical_projection([], [], commercial)['mismatch_count'], 0)

	def test_duplicate_groups_and_extra_physical_rows_fail(self):
		original, physical, commercial = self.fixture()
		self.assertGreater(compare_physical_projection(original, physical, commercial * 2)['mismatch_count'], 0)
		self.assertGreater(compare_physical_projection(original, physical * 2, commercial)['mismatch_count'], 0)
