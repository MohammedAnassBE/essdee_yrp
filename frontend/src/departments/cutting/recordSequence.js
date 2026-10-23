import { getList } from "../../api/frappe.js"
import { parentGroupBy } from "../../components/common/listItemFilters.js"

export function adjacentRecordNames(names, current) {
	const index = (names || []).indexOf(current)
	if (!current || index < 0) return { previousName: "", nextName: "" }
	return { previousName: names[index - 1] || "", nextName: names[index + 1] || "" }
}

export async function listSnapshotNames(snapshot, fetchList = getList) {
	const rows = await fetchList(snapshot.doctype, {
		fields: ["name"],
		filters: snapshot.filters,
		orderBy: snapshot.orderBy,
		start: 0,
		pageLength: Math.max(500, Number(snapshot.total) || 0),
		groupBy: parentGroupBy(snapshot.filters, snapshot.doctype),
	})
	return rows.map((row) => row.name)
}
