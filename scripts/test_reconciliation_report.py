import unittest

from render_migration_reconciliation import render


class ReconciliationResultTest(unittest.TestCase):
	def payload(self):
		return {'summary': {key: 0 for key in (
			'source_doctypes', 'source_rows_read', 'source_field_values_seen', 'field_routes',
			'schema_gap_routes', 'ignored_field_routes_with_material_data', 'missing_auth_rows',
			'ignored_auth_rows_with_data', 'missing_target_row_field_values', 'mismatched_field_values',
			'normalized_matches', 'target_fills_from_source_blank', 'credential_value_mismatches',
			'credential_record_identity_mismatches', 'raw_source_archive_mismatches',
			'purchase_invoice_physical_grn_mismatches',
			'bin_reservation_mismatches',
			'retired_source_archive_mismatches', 'framework_value_mismatches',
			'purchase_invoice_group_mismatches', 'unsupported_debit_discriminators', 'attachment_value_mismatches')},
			'field_results': [], 'document_routes': [], 'complete_application_scope': True,
			'generated_on': 'test', 'source': {'site': 'source'}, 'target': {'site': 'target'}}

	def test_all_checked_zero_has_qualified_pass(self):
		audit = self.payload()
		audit['raw_source_archives'] = {'mismatch_count': 0, 'tables': [
			{'source_parent': 'Purchase Invoice', 'archive_field': 'original_item_rows', 'mismatch_count': 0},
		]}
		page = render(audit, {})
		self.assertIn('Database comparison checks passed', page)
		self.assertIn('Not an unconditional production-ready certificate', page)
		self.assertIn('Historical stock-valuation readiness was not included', page)
		self.assertIn('there is no third JSON item copy', page)
		self.assertNotIn('original_item_rows', page)

	def test_ignored_values_and_missing_schema_or_credentials_cannot_look_complete(self):
		for metric in ('schema_gap_routes', 'ignored_field_routes_with_material_data',
			'missing_auth_rows', 'ignored_auth_rows_with_data', 'target_fills_from_source_blank',
			'credential_record_identity_mismatches', 'purchase_invoice_physical_grn_mismatches', 'bin_reservation_mismatches'):
			with self.subTest(metric=metric):
				audit = self.payload()
				audit['summary'][metric] = 1
				self.assertIn('Database comparison needs review', render(audit, {}))

	def test_partial_or_missing_check_is_not_a_pass(self):
		audit = self.payload()
		audit['complete_application_scope'] = False
		self.assertIn('Database comparison needs review', render(audit, {}))
		audit = self.payload()
		del audit['summary']['schema_gap_routes']
		self.assertIn('Database comparison needs review', render(audit, {}))

	def test_proven_fills_remain_disclosed_and_count_disagreement_fails(self):
		audit = self.payload()
		audit['summary'].update(target_fills_from_source_blank=17, verified_default_fills=17, unverified_default_fills=0)
		page = render(audit, {})
		self.assertIn('Database comparison checks passed', page)
		self.assertIn('not counted as exact copies', page)
		self.assertIn('default-fill-detail', page)
		audit['summary']['verified_default_fills'] = 16
		self.assertIn('Database comparison needs review', render(audit, {}))

	def test_new_valuation_link_readiness_is_separate_visible_evidence(self):
		audit = self.payload()
		audit['valuation_lineage_readiness'] = {'wholly_unmapped_grn_deliverables': 7}
		page = render(audit, {})
		self.assertIn('"wholly_unmapped_grn_deliverables": 7', page)
		self.assertIn('valuation-readiness-detail', page)
		self.assertIn('7 GRN deliverable rows have no proven allocation links', page)
		self.assertIn('require review before using historical valuation adjustments', page)
		self.assertIn('Database comparison checks passed', page)
		self.assertIn('Not an unconditional production-ready certificate', page)

	def test_refreshed_framework_provenance_remains_visible(self):
		audit = self.payload()
		audit['framework_audit_refresh'] = {'original_sha256': 'proof-hash', 'original_framework_mismatches': 36}
		page = render(audit, {})
		self.assertIn('proof-hash', page)
		self.assertIn('audit-provenance', page)

	def test_builtin_normalizations_and_existing_links_are_not_hidden(self):
		live = {'report': {'values': {'normalized_numeric_value_count': 2284},
			'links': {'audited_broken_link_values': 25, 'unexpected_broken_link_values': 0}}}
		page = render(self.payload(), live)
		self.assertIn('unresolved source links retained: 25', page)
		self.assertIn('unexpected broken target links: 0', page)
		self.assertIn('"normalized_numeric_value_count": 2284', page)
		self.assertIn('builtin-numeric-note', page)

	def test_file_column_omission_fails_and_source_gap_count_comes_from_independent_audit(self):
		audit = self.payload()
		audit['summary']['attachment_value_mismatches'] = 1
		audit['attachments'] = {'missing_source_blob_count': 7}
		page = render(audit, {'report': {'files': {'audited_missing_blob_count': 999}}})
		self.assertIn('Database comparison needs review', page)
		self.assertIn('7 attachment blobs unavailable', page)
		self.assertIn('id="attachment-detail"', page)
