export function ipdAttributeLinkName(editor, fieldname, value, table, row) {
	const names = editor.context?.link_names
	const target = table ? names?.tables?.[table]?.[row]?.[fieldname] : names?.fields?.[fieldname]
	return target?.value === value ? target.name : ""
}

export function ipdLinkColumns(columns, editor, table) {
	return columns.map((column) => column.link_doctype === "YRP Item Attribute Value" ? {
		...column, linkName: (value, row) => ipdAttributeLinkName(editor, column.key, value, table, row.key),
	} : column)
}
