export function childTableColumnField(column, columnFilters, row) {
	return columnFilters
		? { ...column, link_filters: columnFilters(column, row) ?? column.link_filters }
		: column
}
