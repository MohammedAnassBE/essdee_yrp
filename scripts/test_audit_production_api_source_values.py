"""Regression tests for the independent auditor (synthetic credentials only)."""

import base64
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from audit_production_api_source_values import FieldAudit, _audit_auth, _audit_purchase_invoice_projection, _audit_retired_tables, _compare_auth_value
from audit_production_api_source_values import (
	Auditor, Route, LAYOUT_FIELD_TYPES, TABLE_FIELD_TYPES, SYSTEM_FIELDS,
	_schema_fields, _field_route, _system_expected, _expected_value, _doctype_controllers,
)


def compare_row_uncached(auditor, route, source, target, target_columns):
	"""Pre-compilation row algorithm, retained solely as a parity reference."""
	spec = auditor.plan.specs[route.source_doctype]
	for fieldname, source_field in _schema_fields(spec.source_schema).items():
		targets, disposition, reason = _field_route(auditor.plan, route, fieldname, source_field)
		metric = auditor._metric(route, fieldname, str(source_field.get('fieldtype') or ''),
			targets, disposition, reason)
		metric.source_rows += 1
		if metric.source_fieldtype in LAYOUT_FIELD_TYPES | TABLE_FIELD_TYPES | {'Password'} or fieldname not in source:
			continue
		auditor._compare_value(metric, fieldname, source[fieldname], target, target_columns,
			identity=str(source.get('name') or ''), route=route)
	for fieldname in SYSTEM_FIELDS:
		if fieldname not in source:
			continue
		metric = auditor._metric(route, fieldname, 'System', [fieldname], 'system', 'source identity/audit metadata')
		metric.source_rows += 1
		value = _system_expected(auditor.plan, route, fieldname, source[fieldname])
		auditor._compare_value(metric, fieldname, value, target, target_columns,
			identity=str(source.get('name') or ''), route=route, already_expected=True)


class CompiledAuditRoutingParityTest(unittest.TestCase):
	def plan(self):
		fields = [
			{'fieldname': name, 'fieldtype': kind, **options}
			for name, kind, options in (
				('title', 'Data', {}), ('qty', 'Float', {}), ('payload', 'JSON', {}),
				('controller', 'Link', {'options': 'DocType'}),
				('reference', 'Dynamic Link', {'options': 'controller'}),
				('renamed', 'Data', {}), ('retired', 'Data', {}),
				('layout', 'Section Break', {}), ('children', 'Table', {'options': 'Child'}),
				('secret', 'Password', {}), ('absent', 'Data', {}),
			)
		]
		schema = {'fields': fields}
		target_schema = {'fields': [dict(row, fieldname='new_name') if row['fieldname']=='renamed' else row for row in fields]}
		spec = SimpleNamespace(source_schema=schema, target_schema=target_schema, target='YRP Example',
			field_map={'renamed': 'new_name'}, ignored_fields={'retired': 'explicitly retired'},
			custom_transformer=None, value_transformers={})
		return SimpleNamespace(specs={'Example': spec}, target_schemas={'YRP Example': target_schema})

	def test_compiled_rows_preserve_all_metrics_and_failure_samples(self):
		plan = self.plan()
		source = dict(name='row', title='original', qty='1.123456789', payload='{"a":1}',
			controller='Example', reference='other', renamed='retained', retired='historical',
			parent='P', parenttype='Example', parentfield='old_rows', idx=0)
		columns = {name: {'numeric_scale': 6} for name in source}
		target_columns = {**columns, 'new_name': {}}
		target = dict(source, controller='YRP Example', new_name='retained', parenttype='YRP Example', parentfield='new_rows')
		for actual in (target, dict(target, title='wrong', qty='1.123457'), None):
			for route in (Route('Example', 'YRP Example'),
				Route('Example', 'YRP Example', 'Example', 'old_rows', 'YRP Example', 'new_rows')):
				with self.subTest(actual=actual is not None, context=route.label):
					with patch.object(Auditor, '_work_order_invoices', return_value=set()):
						cached = Auditor(plan, None, None, 500)
						uncached = Auditor(plan, None, None, 500)
					for auditor in (cached, uncached):
						auditor.source_columns['Example'] = columns
						auditor.target_columns['YRP Example'] = target_columns
						auditor._prepare_metrics(route)
					for _ in range(2):
						cached._compare_row(route, source, actual, target_columns)
						compare_row_uncached(uncached, route, source, actual, target_columns)
					self.assertEqual({k: v.payload() for k,v in cached.metrics.items()},
						{k: v.payload() for k,v in uncached.metrics.items()})

	def test_cached_controller_set_matches_uncached_value_mapping(self):
		plan = self.plan()
		route = Route('Example', 'YRP Example')
		controllers = _doctype_controllers(plan.specs['Example'].source_schema)
		for field in ('controller', 'reference', 'title'):
			for value in ('Example', 'Unmapped', '', None, 0):
				self.assertEqual(_expected_value(plan, route, field, value),
					_expected_value(plan, route, field, value, controllers=controllers))


class IndependentFieldStatusTest(unittest.TestCase):
	def test_rounding_and_filled_blanks_are_not_labelled_pass(self):
		for key in ('normalized_matches', 'target_filled_from_source_blank'):
			with self.subTest(key=key):
				metric = FieldAudit('Example', 'YRP Example', 'parent', 'value', ['value'], 'Data', 'direct')
				setattr(metric, key, 1)
				self.assertEqual(metric.status, 'Review Required')


class IndependentRetiredBlobAuditTest(unittest.TestCase):
	def audit(self, *, available, archived_bytes):
		content = b'synthetic retired attachment'
		row = dict(name='retired-file', file_size=len(content),
			content_hash=hashlib.md5(content).hexdigest(), file_url='/files/retired.txt')
		record = {'source_doctype': 'File', 'row': row}
		if archived_bytes:
			record['blob_base64'] = base64.b64encode(content).decode()
		else:
			record['blob_issue'] = 'Source file missing'
		source, target = MagicMock(), MagicMock()
		src = source.cursor.return_value.__enter__.return_value
		dst = target.cursor.return_value.__enter__.return_value
		dst.fetchone.return_value = {'retired_source_rows_json': json.dumps([record])}

		def execute(sql, params=()):
			if 'information_schema.tables' in sql:
				src.fetchone.return_value = {'exists': 1} if params == ('tabFile',) else None
			else:
				src.fetchall.return_value = [row]

		src.execute.side_effect = execute
		with patch('audit_attachment_values.SourceBlobEvidence') as evidence:
			evidence.return_value.available.return_value = available
			result = _audit_retired_tables(source, target, 'migration', source_site_path='/synthetic/source')
			evidence.assert_called_once_with(source, '/synthetic/source')
		return result

	def test_available_blob_cannot_be_accepted_as_source_gap(self):
		result = self.audit(available=True, archived_bytes=False)
		self.assertEqual(result['mismatch_count'], 1)
		self.assertEqual(result['available_source_blobs'], 1)
		self.assertEqual(result['missing_source_blobs'], [])

	def test_independently_missing_blob_remains_explicit(self):
		result = self.audit(available=False, archived_bytes=False)
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['independently_checked_source_blobs'], 1)
		self.assertEqual(len(result['missing_source_blobs']), 1)

	def test_available_bytes_require_matching_archive(self):
		result = self.audit(available=True, archived_bytes=True)
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['verified_blobs'], 1)


class IndependentInvoiceProjectionTest(unittest.TestCase):
	def audit(self, targets):
		source = MagicMock()
		target = MagicMock()
		source.cursor.return_value.__enter__.return_value.fetchall.return_value = [{
			"name": "PII-1", "parent": "PI-1", "item": "Item-1", "lot": "Lot-1",
			"uom": "Nos", "rate": 10, "qty": 2, "amount": 20, "actual_rate": 10,
			"actual_qty": 0, "tax": "", "item_group": "Group-1", "expense_head": "Expense-1",
		}]
		target.cursor.return_value.__enter__.return_value.fetchall.return_value = targets
		return _audit_purchase_invoice_projection(source, target, set())

	def row(self, **changes):
		return {"name": "GROUP-1", "parent": "PI-1", "item": "Item-1", "lot": "Lot-1",
			"uom": "Nos", "rate": 10, "qty": 2, "amount": 20, "source_rate": 10,
			"tax": "", "item_group": "Group-1", "expense_head": "Expense-1", **changes}

	def test_exact_projection_passes(self):
		self.assertEqual(self.audit([self.row()])["mismatch_count"], 0)

	def test_extra_and_duplicate_groups_fail(self):
		for extra in (self.row(name="EXTRA", item="Item-2"), self.row(name="DUPLICATE")):
			with self.subTest(extra=extra["name"]):
				self.assertGreater(self.audit([self.row(), extra])["mismatch_count"], 0)

	def test_wrong_item_group_fails(self):
		self.assertEqual(self.audit([self.row(item_group="Wrong")])["mismatch_count"], 1)

	def test_sub_micro_quantity_or_rate_differences_fail(self):
		for field, value in (('qty', '2.0000001'), ('rate', '10.0000001'), ('source_rate', '10.0000001')):
			with self.subTest(field=field):
				self.assertEqual(self.audit([self.row(**{field: value})])['mismatch_count'], 1)


class IndependentCredentialAuditTest(unittest.TestCase):
	def test_source_orphan_requires_no_target_record_and_exact_credential_value(self):
		row = dict(doctype="Example", name="Deleted", fieldname="secret",
			password="synthetic", encrypted=0, has_value=1)
		spec = SimpleNamespace(target="YRP Example", field_map={}, ignored_fields=set(),
			source_schema={}, target_schema={})
		plan = SimpleNamespace(specs={"Example": spec})
		for source_exists, target_exists in ((False, False), (False, True), (True, False), (True, True)):
			with self.subTest(source_exists=source_exists, target_exists=target_exists):
				source, target = MagicMock(), MagicMock()
				src = source.cursor.return_value.__enter__.return_value
				dst = target.cursor.return_value.__enter__.return_value
				src.fetchall.return_value = [row]
				dst.fetchall.return_value = [{**row, "doctype": "YRP Example"}]
				src.fetchone.return_value = {"name": "Deleted"} if source_exists else None
				dst.fetchone.return_value = {"name": "Deleted"} if target_exists else None
				result = _audit_auth(plan, source, target)
				self.assertEqual(result["source_orphan_rows"], int(not source_exists))
				self.assertEqual(result["record_identity_mismatches"], int(source_exists != target_exists))
				self.assertEqual(result["value_mismatches"], 0)
				self.assertNotIn("synthetic", repr(result))

	def test_reencrypted_value_matches_without_exposing_it(self):
		source_key, target_key = Fernet.generate_key(), Fernet.generate_key()
		source = {"encrypted": 1, "password": Fernet(source_key).encrypt(b"synthetic value").decode()}
		target = {"encrypted": 1, "password": Fernet(target_key).encrypt(b"synthetic value").decode()}
		result = _compare_auth_value(source, target, source_key.decode(), target_key.decode())
		self.assertEqual(result, ("Re-encrypted value matches", True))
		self.assertNotIn("synthetic value", repr(result))

	def test_changed_secret_fails(self):
		key = Fernet.generate_key()
		source = {"encrypted": 1, "password": Fernet(key).encrypt(b"before").decode()}
		target = {"encrypted": 1, "password": Fernet(key).encrypt(b"after").decode()}
		self.assertEqual(_compare_auth_value(source, target, key.decode(), key.decode()),
			("Decrypted value mismatch", False))

	def test_unavailable_key_requires_exact_ciphertext(self):
		source = {"encrypted": 1, "password": "synthetic historical ciphertext"}
		self.assertEqual(_compare_auth_value(source, dict(source), None, None),
			("Ciphertext preserved; source key unavailable", True))
		self.assertEqual(_compare_auth_value(source, {**source, "password": "changed"}, None, None),
			("Ciphertext mismatch", False))

	def test_missing_row_or_changed_encryption_flag_fails(self):
		source = {"encrypted": 1, "password": "synthetic ciphertext"}
		self.assertEqual(_compare_auth_value(source, None, None, None), ("Missing", False))
		self.assertEqual(_compare_auth_value(source, {**source, "encrypted": 0}, None, None),
			("Encryption flag mismatch", False))


if __name__ == "__main__":
	unittest.main()
