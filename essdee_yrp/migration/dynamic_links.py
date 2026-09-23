"""Read-only, exact Dynamic Link audit shared by F15 and F16 adapters."""


def _quote(value):
	return '`' + str(value).replace('`', '``') + '`'


def iter_broken_dynamic_links(frappe, schemas, parenttypes=()):
	count = 0
	for doctype, schema in sorted(schemas.items()):
		for field in schema.get('fields') or []:
			if field.get('fieldtype') != 'Dynamic Link' or not field.get('options'):
				continue
			fieldname, controller_field = field['fieldname'], field['options']
			if schema.get('issingle'):
				values = frappe.db.get_singles_dict(doctype)
				controller, value = values.get(controller_field), values.get(fieldname)
				rows = [(doctype, controller, value)] if value else []
			else:
				table, column, controller_column = _quote('tab' + doctype), _quote(fieldname), _quote(controller_field)
				scope = ' AND s.parenttype IN %s' if schema.get('istable') and parenttypes else ''
				params = (tuple(parenttypes),) if scope else ()
				controllers = frappe.db.sql(f"SELECT DISTINCT s.{controller_column} FROM {table} s WHERE COALESCE(s.{column}, '')<>''{scope}", params)
				rows = []
				for (controller,) in controllers:
					join, missing, args = '', '', (controller, *params)
					if controller and frappe.db.exists('DocType', controller):
						if frappe.get_meta(controller).issingle:
							missing = f' AND s.{column}<>%s'
							args = (controller, controller, *params)
						else:
							join = f' LEFT JOIN {_quote("tab" + controller)} linked ON linked.name=s.{column}'
							missing = ' AND linked.name IS NULL'
					rows.extend(frappe.db.sql(f"SELECT s.name, s.{controller_column}, s.{column} FROM {table} s{join} WHERE s.{controller_column}<=>%s AND COALESCE(s.{column}, '')<>''{missing}{scope} LIMIT 10001", args))
			for name, controller, value in rows:
				if schema.get('issingle') and controller and frappe.db.exists('DocType', controller):
					valid = value == controller if frappe.get_meta(controller).issingle else frappe.db.exists(controller, value)
					if valid:
						continue
				count += 1
				if count > 10000:
					raise RuntimeError('More than 10,000 broken Dynamic Links require separate review')
				yield {'doctype': doctype, 'name': str(name), 'fieldname': fieldname,
					'link_doctype': str(controller or ''), 'value': str(value)}
