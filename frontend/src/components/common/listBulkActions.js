/** Desk-style list bulk actions: which rows each action applies to, its copy, and a per-document runner. */
export const BULK_ACTIONS = {
	submit: { label: "Submit", icon: "pi pi-arrow-right", severity: "primary", permission: "submit", docstatuses: [0], lifecycle: true, progress: "Submitting", done: "submitted" },
	cancel: { label: "Cancel", icon: "pi pi-ban", severity: "danger", permission: "cancel", docstatuses: [1], lifecycle: true, progress: "Cancelling", done: "cancelled" },
	delete: { label: "Delete", icon: "pi pi-trash", severity: "danger", permission: "delete", docstatuses: [0, 2], lifecycle: false, progress: "Deleting", done: "deleted" },
}

export function bulkActionRows(action, rows, { isSubmittable = false } = {}) {
	const definition = BULK_ACTIONS[action]
	if (!definition) return []
	if (!isSubmittable) return definition.lifecycle ? [] : [...rows]
	return rows.filter((row) => definition.docstatuses.includes(Number(row.docstatus)))
}

/** Actions the user may run on the selection: permitted, not workflow-driven for Submit/Cancel, and applicable to at least one row. */
export function availableBulkActions(rows, { isSubmittable = false, hasWorkflow = false, can = () => false } = {}) {
	return Object.entries(BULK_ACTIONS).flatMap(([action, definition]) => {
		if (definition.lifecycle && hasWorkflow) return []
		if (!can(definition.permission)) return []
		const candidates = bulkActionRows(action, rows, { isSubmittable })
		return candidates.length ? [{ action, ...definition, rows: candidates }] : []
	})
}

/** `definition` lets a page pass its own action (label, severity, done) instead of a standard one. */
export function bulkConfirmation(action, rows, title, definition = BULK_ACTIONS[action]) {
	const { label } = definition
	const subject = rows.length === 1 ? rows[0].name : `${rows.length} ${title}`
	return {
		title: `${label} ${rows.length === 1 ? "Document" : "Documents"}`,
		message: `${label} ${subject}?`,
		confirmLabel: label,
		severity: definition.severity,
	}
}

/** Runs `perform(row)` per row in order, so one failure never stops or hides the rest. */
export async function runBulkRows(rows, perform, onProgress = () => {}) {
	const done = []
	const failed = []
	for (const [index, row] of rows.entries()) {
		onProgress(index + 1, rows.length)
		try {
			await perform(row)
			done.push(row.name)
		} catch (reason) {
			failed.push({ name: row.name, error: reason?.message || "Failed" })
		}
	}
	return { done, failed }
}

export function bulkOutcome(action, { done, failed }, definition = BULK_ACTIONS[action]) {
	const { label = "Edit", done: verb = "updated" } = definition || {}
	const documents = (count) => `${count} document${count === 1 ? "" : "s"}`
	return {
		title: `${label} ${done.length ? "partially completed" : "failed"}`,
		summary: `${documents(done.length)} ${verb}; ${documents(failed.length)} failed.`,
		notice: `${documents(done.length)} ${verb}.`,
		failed,
	}
}
