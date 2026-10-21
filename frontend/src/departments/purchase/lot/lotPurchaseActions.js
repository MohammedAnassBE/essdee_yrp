export function purchaseLotActions(workspace, execute, acting = "") {
	const canWrite = Boolean(workspace.permissions?.can_write)
	return [
		...lotActionRows(workspace, execute, acting, [
			{ key: "edit", label: "Edit", icon: "pi pi-pencil", primary: true, visible: canWrite },
			{ key: "purchase_summary", label: "Purchase Summary", icon: "pi pi-table", visible: true },
		]),
		...purchaseOrderLinkActions(workspace, execute, acting),
	]
}

export function purchaseOrderLinkActions(workspace, execute, acting = "") {
	const canWrite = Boolean(workspace.permissions?.can_write)
	return lotActionRows(workspace, execute, acting, [
		{ key: "link_po", label: "Link to PO", icon: "pi pi-link", visible: canWrite },
		{ key: "unlink_po", label: "Unlink from PO", icon: "pi pi-unlink", visible: canWrite },
	])
}

function lotActionRows(workspace, execute, acting, actions) {
	if (!workspace.name) return []
	return actions.filter(action => action.visible).map(action => ({ ...action, disabled: Boolean(acting), command: () => execute(action.key) }))
}

export function lotPurchaseSummaryRoute(lot) {
	return { path: "/purchase/reports", query: { report: "lot-purchase-summary", lot } }
}

export function purchaseOrderLinkFilters() {
	return { docstatus: 1, open_status: "Open" }
}

export function purchaseOrderLinkArgs(lot, mode, selections, reason) {
	if (!selections.length) throw new Error("Select at least one Purchase Order")
	if (!reason.trim()) throw new Error("Reason is required")
	return { lot, add_pos: mode === "link" ? selections : [], remove_pos: mode === "unlink" ? selections : [], comment: reason }
}

export function purchaseOrderOption(row) {
	const name = typeof row === "string" ? row : row.name
	const label = typeof row === "string" ? "" : row.label
	return { value: name, label: label && label !== name ? `${name} · ${label}` : name }
}
