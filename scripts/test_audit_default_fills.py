import unittest
from types import SimpleNamespace
from unittest.mock import patch

from audit_default_fills import FillEvidence, SourceDefaultEvidence, _ledger_references
from audit_production_api_source_values import Auditor, FieldAudit, Route, _field_route


class IndependentDefaultFillTest(unittest.TestCase):
	def evidence(self, doctype, field, rows=(), *, target_field=None, configured=None, schema=None):
		route = Route(doctype, 'Target')
		plan = SimpleNamespace(target_schemas={'Target': schema or {'fields': []}})
		provider = SourceDefaultEvidence(None, plan, configured)
		with patch('audit_default_fills._rows', return_value=list(rows)):
			return provider.prepare(route, field, [target_field or field])

	def test_constant_checks_exact_value_not_merely_nonblank(self):
		evidence = self.evidence('Delivery Challan Item', 'item_type', [{'value': 'Accepted'}], target_field='received_type')
		self.assertTrue(evidence.matches('row', ['Accepted']))
		for values in (['Rejected'], [], ['Accepted', 'Rejected'], [None]):
			self.assertFalse(evidence.matches('row', values))
		self.assertFalse(self.evidence('Delivery Challan Item', 'item_type', [], target_field='received_type').matches('row', ['Accepted']))

	def test_product_uses_original_style_not_target_identity(self):
		evidence = self.evidence('Product', 'item_name', [dict(name='id', style_no='style'), dict(name='fallback', style_no='')])
		self.assertTrue(evidence.matches('id', ['style']))
		self.assertFalse(evidence.matches('id', ['id']))
		self.assertTrue(evidence.matches('fallback', ['fallback']))
		self.assertFalse(evidence.matches('unknown', ['style']))

	def test_uom_queries_original_variant_field_not_target_alias(self):
		provider = SourceDefaultEvidence(None, SimpleNamespace(target_schemas={}))
		for doctype, column in (('Purchase Order Item', 'item_variant'), ('Lot BOM', 'item_name')):
			with patch('audit_default_fills._rows', return_value=[dict(name='row', source_item='item', expected='Nos')]) as query:
				evidence = provider.prepare(Route(doctype, 'Target'), 'uom', ['uom'])
				self.assertIn('v.name=r.`'+column+'`', query.call_args.args[1])
				self.assertTrue(evidence.matches('row', ['Nos']))

	def test_unknown_fields_and_unreviewed_config_are_not_waived(self):
		self.assertIsNone(self.evidence('Example', 'value'))
		for configured in ({}, {'Lot BOM.process_name': 'Different'}):
			self.assertFalse(self.evidence('Lot BOM', 'process_name', configured=configured).matches('row', ['Packing']))
		self.assertTrue(self.evidence('Lot BOM', 'process_name', configured={'Lot BOM.process_name': 'Packing'}).matches('row', ['Packing']))

	def test_select_default_requires_reviewed_value_and_real_schema(self):
		for options, expected in (('\nBody\nRib', True), ('Rib\nBody', False), ('', False)):
			evidence = self.evidence('Stiching Item Detail', 'category', schema={'fields': [
				{'fieldname': 'category', 'fieldtype': 'Select', 'options': options}]})
			self.assertEqual(evidence.matches('row', ['Body']), expected)

	def test_invoice_classification_requires_original_relationship(self):
		evidence = self.evidence('Purchase Invoice', 'against', [
			dict(name='wo', is_work_order=1, has_grn=1), dict(name='po', is_work_order=0, has_grn=1),
			dict(name='unknown', is_work_order=0, has_grn=0)])
		self.assertTrue(evidence.matches('wo', ['YRP Work Order']))
		self.assertTrue(evidence.matches('po', ['YRP Purchase Order']))
		self.assertFalse(evidence.matches('unknown', ['YRP Purchase Order']))

	def test_cpm_only_uses_explicit_nested_ledger_references(self):
		self.assertEqual(_ledger_references('{"rows":[{"cut_ref_docname":"ledger", "item":"not-ledger"}]}'), {'ledger'})
		self.assertEqual(_ledger_references('invalid json'), set())
		self.assertEqual(_ledger_references([]), set())

	def test_compared_fill_is_disclosed_separately_from_exact_and_unknown_fails(self):
		route = Route('Example', 'Target')
		auditor = object.__new__(Auditor)
		auditor.fill_rules = {(route, 'value'): FillEvidence('reviewed test default', constant='correct')}
		for actual, verified in (('correct', 1), ('wrong', 0)):
			metric = FieldAudit('Example', 'Target', 'parent', 'value', ['value'], 'Data', 'direct')
			auditor._compare_value(metric, 'value', None, {'value': actual}, {},
				identity='row', route=route, already_expected=True)
			self.assertEqual(metric.target_filled_from_source_blank, 1)
			self.assertEqual(metric.verified_default_fills, verified)
			self.assertEqual(metric.exact_matches, 0)
			self.assertEqual(metric.status, 'Verified default fill (not exact copy)' if verified else 'Review Required')

	def test_debit_discriminator_is_semantic_not_ignored_and_requires_target(self):
		spec = SimpleNamespace(custom_transformer='debit', ignored_fields={'against': 'encoded by link type'})
		plan = SimpleNamespace(specs={'Essdee Debit': spec}, target_schemas={'YRP Debit': {'fields': []}})
		route = Route('Essdee Debit', 'YRP Debit')
		fields, disposition, reason = _field_route(plan, route, 'against', {'fieldtype': 'Link'})
		self.assertEqual(disposition, 'custom_transform')
		for target, good in (({'work_order': 'WO'}, True), ({'work_order': ''}, False), (None, False)):
			metric = FieldAudit('Essdee Debit', 'YRP Debit', 'parent', 'against', fields, 'Link', disposition)
			auditor = object.__new__(Auditor)
			auditor._compare_value(metric, 'against', 'Work Order', target, {}, identity='row', route=route)
			self.assertEqual(metric.exact_matches, int(good))
			self.assertEqual(metric.mismatches, int(not good))


if __name__ == '__main__':
	unittest.main()
