"""Read-only source closure for framework records belonging to the app data.

This module runs under the configured F15 interpreter. It performs SELECTs
only. Configuration/sharing/workflow records are exported as inert evidence,
never installed as configuration on the target.
"""

import hashlib
import json
from types import SimpleNamespace


def quote(value):
	return '`' + str(value).replace('`', '``') + '`'


def controllers(meta):
	result = {f.fieldname: None for f in meta.fields
		if f.fieldtype == 'Link' and f.options == 'DocType'}
	for field in meta.fields:
		if field.fieldtype == 'Dynamic Link' and field.options:
			result[field.options] = field.fieldname
	if meta.name == 'Version':
		result['ref_doctype'] = 'docname'
	return result


def source_metadata(frappe, doctype):
	if frappe.db.exists('DocType', doctype):
		return frappe.get_meta(doctype)
	# A retired framework table can retain DocFields and real rows even after
	# its DocType was removed. Inspect those stored definitions, do not skip it.
	fields = frappe.db.sql('SELECT fieldname,fieldtype,options FROM tabDocField WHERE parent=%s',
		(doctype,), as_dict=True)
	fields += frappe.db.sql('SELECT fieldname,fieldtype,options FROM `tabCustom Field` WHERE dt=%s',
		(doctype,), as_dict=True)
	meta = SimpleNamespace(name=doctype, fields=fields)
	meta.get_table_fields = lambda: [f for f in fields if f.fieldtype in {'Table', 'Table MultiSelect'}]
	return meta


def build_scope(frappe, schemas, retired_tables, business_names, app_file_names=()):
	"""Return parameterized row predicates, including children and attachments."""
	app_types = tuple(sorted(set(schemas) | set(retired_tables)))
	scope = {}
	metadata = {}
	# Runtime custom controllers matter as much as standard DocFields.
	types = frappe.db.sql("SELECT DISTINCT parent FROM tabDocField WHERE "
		"fieldtype='Dynamic Link' OR (fieldtype='Link' AND options='DocType')")
	types += frappe.db.sql("SELECT DISTINCT dt FROM `tabCustom Field` WHERE "
		"fieldtype='Dynamic Link' OR (fieldtype='Link' AND options='DocType')")
	for doctype in sorted({row[0] for row in types}):
		if doctype in app_types or doctype == 'File' or not frappe.db.table_exists(doctype):
			continue
		meta = metadata.setdefault(doctype, source_metadata(frappe, doctype))
		columns = set(frappe.db.get_table_columns(doctype))
		parts, params = [], []
		for controller, name_field in controllers(meta).items():
			if controller not in columns:
				continue
			parts.append(f'{quote(controller)} IN %s')
			params.append(app_types)
			if name_field and name_field in columns:
				for master, names in sorted(business_names.items()):
					if names:
						parts.append(f'({quote(controller)}=%s AND {quote(name_field)} IN %s)')
						params.extend((master, tuple(names)))
		if parts:
			scope[doctype] = ('(' + ' OR '.join(parts) + ')', tuple(params))
	# Comment is site business history, not merely history of the DocTypes owned
	# by production_api. Preserve and restore the complete table. Version is an
	# intentionally excluded change-log table for this migration: the owner does
	# not require it on the new site, so do not archive or activate a partial set.
	if frappe.db.table_exists('Comment'):
		scope['Comment'] = ('1=1', ())
	scope.pop('Version', None)
	for doctype, names in business_names.items():
		if names:
			scope[doctype] = ('name IN %s', (tuple(names),))
	# These records refer to an app-owned framework record instead of directly
	# to a DocType. Prepared Report.report_name is Data, not a declared Link.
	# Preserve the evidence/configuration without activating email/report jobs.
	for doctype, fieldname, parent in (
		('Prepared Report', 'report_name', 'Report'),
		('Auto Email Report', 'report', 'Report'),
		('Data Import Log', 'data_import', 'Data Import'),
		('Number Card Link', 'card', 'Number Card'),
	):
		if parent not in scope or not frappe.db.table_exists(doctype):
			continue
		if fieldname not in frappe.db.get_table_columns(doctype):
			raise RuntimeError(f'Missing supporting history relationship: {doctype}.{fieldname}')
		predicate, params = scope[parent]
		clause = f'{quote(fieldname)} IN (SELECT name FROM {quote("tab" + parent)} WHERE {predicate})'
		if doctype in scope:
			previous, previous_params = scope[doctype]
			scope[doctype] = (f'({previous} OR {clause})', (*previous_params, *params))
		else:
			scope[doctype] = (clause, params)
	# Close actual parent/table relationships. Do not collect millions of names
	# in Python or argv; use source-side subqueries bounded by the parent scope.
	for doctype, (predicate, params) in list(scope.items()):
		meta = metadata.setdefault(doctype, source_metadata(frappe, doctype))
		for field in meta.get_table_fields():
			child = field.options
			if child in app_types:
				continue  # Already fully included by the main application loader.
			clause = ('(parenttype=%s AND parentfield=%s AND parent IN '
				f'(SELECT name FROM {quote("tab" + doctype)} WHERE {predicate}))')
			child_params = (doctype, field.fieldname, *params)
			if child in scope:
				old, old_params = scope[child]
				scope[child] = (f'({old} OR {clause})', (*old_params, *child_params))
			else:
				scope[child] = (clause, child_params)
	# App File rows have their own metadata/blob preservation route. Include
	# additional attachments only when their framework/supporting parent is in
	# this exact closure. Never import an unrelated site's files.
	parts, file_params = [], []
	for doctype, (predicate, params) in sorted(scope.items()):
		parts.append('(attached_to_doctype=%s AND attached_to_name IN '
			f'(SELECT name FROM {quote("tab" + doctype)} WHERE {predicate}))')
		file_params.extend((doctype, *params))
	if parts:
		scope['File'] = ('(' + ' OR '.join(parts) + ')', tuple(file_params))
	# File.folder is a Link to another File. Preserve the complete ancestor
	# graph for app and supporting attachments, including roots as raw evidence.
	file_condition, file_values = scope.get('File', ('0=1', ()))
	names = {row[0] for row in frappe.db.sql(
		"SELECT DISTINCT folder FROM tabFile WHERE is_folder=0 AND COALESCE(folder,'')<>'' "
		f"AND (COALESCE(attached_to_doctype,'') IN %s OR name IN %s OR ({file_condition}))",
		(app_types, tuple(app_file_names) or ('',), *file_values))}
	folders, pending = set(), names
	while pending:
		rows = frappe.db.sql('SELECT name,folder,is_folder FROM tabFile WHERE name IN %s',
			(tuple(sorted(pending)),), as_dict=True)
		if {row.name for row in rows} != pending or any(not row.is_folder for row in rows):
			raise RuntimeError('Source attachment folder graph has missing/non-folder ancestors')
		folders.update(pending)
		pending = {row.folder for row in rows if row.folder} - folders
	if folders:
		scope['File'] = (f'({file_condition} OR (is_folder=1 AND name IN %s))',
			(*file_values, tuple(sorted(folders))))
	return scope


def iter_rows(frappe, scope, batch_size=500):
	for doctype, (predicate, params) in sorted(scope.items()):
		last = ''
		while True:
			rows = frappe.db.sql(f'SELECT * FROM {quote("tab" + doctype)} '
				f'WHERE {predicate} AND name>%s ORDER BY name LIMIT %s',
				(*params, last, batch_size), as_dict=True)
			if not rows:
				break
			for row in rows:
				yield doctype, dict(row)
			last = rows[-1]['name']


def census(frappe, scope):
	result = {}
	for doctype, (predicate, params) in sorted(scope.items()):
		# Password rows are not ordinary table columns. Refuse an unexpected
		# auxiliary credential until it has its own explicit encrypted route.
		auth_count = frappe.db.sql('SELECT COUNT(*) FROM __Auth WHERE doctype=%s '
			f'AND name IN (SELECT name FROM {quote("tab" + doctype)} WHERE {predicate})',
			(doctype, *params))[0][0]
		if auth_count:
			raise RuntimeError(f'{doctype} has {auth_count} supporting credentials; add an explicit preservation route')
		columns = set(frappe.db.get_table_columns(doctype))
		modified = 'MAX(modified)' if 'modified' in columns else 'NULL'
		count, latest = frappe.db.sql(f'SELECT COUNT(*),{modified} '
			f'FROM {quote("tab" + doctype)} WHERE {predicate}', params)[0]
		result[doctype] = {'rows': int(count), 'max_modified': str(latest or ''),
			'columns': sorted(columns)}
		# Bind small configuration datasets even if db_set skipped modified.
		if count <= 10000:
			digest = hashlib.sha256()
			for _, row in iter_rows(frappe, {doctype: (predicate, params)}):
				digest.update(json.dumps(row, sort_keys=True, separators=(',', ':'), default=str).encode())
			result[doctype]['value_digest'] = digest.hexdigest()
	return result
