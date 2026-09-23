import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from essdee_yrp.migration.dynamic_links import iter_broken_dynamic_links
from essdee_yrp.migration.live import _identity_scope_count, _verify_link_integrity


class DynamicLinkAuditTest(unittest.TestCase):
	def test_exact_row_audit_keeps_null_controller_and_child_scope(self):
		sql = Mock(side_effect=[[(None,), ('Missing Type',)], [('row-1', None, 'missing')], [('row-2', 'Missing Type', 'missing')]])
		fake = SimpleNamespace(db=SimpleNamespace(sql=sql, exists=lambda *a: False))
		schemas = {'Child': {'istable': 1, 'fields': [{'fieldname':'ref', 'fieldtype':'Dynamic Link', 'options':'kind'}]}}
		rows = list(iter_broken_dynamic_links(fake, schemas, ['Parent']))
		self.assertEqual([r['name'] for r in rows], ['row-1', 'row-2'])
		self.assertEqual(rows[0]['link_doctype'], '')
		for call in sql.call_args_list:
			self.assertIn('parenttype IN %s', call.args[0])
			self.assertEqual(call.args[1][-1], ('Parent',))

	def test_shared_child_identity_count_excludes_other_framework_parents(self):
		plan = SimpleNamespace(specs={'SMS Settings':SimpleNamespace(target='SMS Settings',is_child=False)})
		with patch('essdee_yrp.migration.live.frappe.db.count', return_value=1) as count:
			self.assertEqual(_identity_scope_count('Has Role', SimpleNamespace(issingle=0,istable=1),plan),1)
			count.assert_called_once_with('Has Role', {'parenttype':['in',['SMS Settings']]})

	def test_only_exact_source_invalid_dynamic_link_is_audited(self):
		spec = SimpleNamespace(target='YRP Stock Entry',field_map={},is_child=False,source_schema={})
		linked = SimpleNamespace(target='SD YRP Finishing Plan',field_map={},is_child=False,source_schema={})
		plan = SimpleNamespace(specs={'Stock Entry':spec,'Finishing Plan':linked},target_schemas={'YRP Stock Entry':{'fields':[]}})
		source = {'doctype':'Stock Entry','name':'STE-1','fieldname':'against_id','link_doctype':'Finishing Plan','value':'FP-1'}
		actual = {**source,'doctype':'YRP Stock Entry','link_doctype':'SD YRP Finishing Plan'}
		with patch('essdee_yrp.migration.live._migration_physical_target_doctypes',return_value=['YRP Stock Entry']), \
			patch('essdee_yrp.migration.live.frappe.get_meta',return_value=SimpleNamespace(istable=0)), \
			patch('essdee_yrp.migration.dynamic_links.iter_broken_dynamic_links',return_value=iter([actual,{**actual,'name':'STE-2'}])):
			result = _verify_link_integrity(plan,source_dynamic_links=[source])
		self.assertEqual(result['audited_broken_link_values'],1)
		self.assertEqual(result['unexpected_broken_link_values'],1)
		self.assertIn('STE-2',result['failures'][0])
