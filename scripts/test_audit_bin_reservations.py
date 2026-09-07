import unittest

from audit_bin_reservations import reconcile_reservations


class BinReservationReconciliationTest(unittest.TestCase):
	def row(self, **changes):
		return dict(name='bin-1', item_code='item', warehouse='warehouse', lot='lot', received_type='Good', **changes)

	def audit(self, *, historical=12, active=10, warehouse='warehouse'):
		source = self.row(reserved_qty=12)
		target = self.row(reserved_qty=historical)
		source_sre = self.row(reserved_qty=10, delivered_qty=0)
		target_sre = dict(self.row(reserved_qty=active, delivered_qty=0, closed_qty=0), warehouse=warehouse)
		return reconcile_reservations([source], [target], [source_sre], [target_sre])

	def test_cache_difference_is_retained_without_inventing_reservations(self):
		result = self.audit()
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['source_cached_reserved_total'], '12')
		self.assertEqual(result['target_active_sre_total'], '10')
		self.assertEqual(result['source_cache_different_buckets'], 1)

	def test_changed_history_or_active_bucket_fails(self):
		for changes in ({'historical': 0}, {'active': 12}, {'warehouse': 'other'}):
			with self.subTest(changes=changes):
				self.assertGreater(self.audit(**changes)['mismatch_count'], 0)

	def test_stale_cache_only_bucket_remains_visible(self):
		source = self.row(reserved_qty=25)
		target = self.row(reserved_qty=25)
		result = reconcile_reservations([source], [target], [], [])
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['stale_source_cache_only_buckets'], 1)
		self.assertEqual(result['stale_source_cache_only_total'], '25')

	def test_closed_qty_and_negative_remainders_cannot_hide_difference(self):
		source = self.row(reserved_qty=10, delivered_qty=0)
		target = dict(source, closed_qty=4)
		self.assertEqual(reconcile_reservations([], [], [source], [target])['mismatch_count'], 1)
		source = self.row(reserved_qty=5, delivered_qty=7)
		self.assertEqual(reconcile_reservations([], [], [source], [source])['mismatch_count'], 1)
