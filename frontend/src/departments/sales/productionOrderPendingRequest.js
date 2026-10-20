function number(value) {
	const parsed = Number(value)
	return Number.isFinite(parsed) ? parsed : 0
}

export function productionOrderRequestRows(request) {
	if (request?.request_type === "quantity_ratio") {
		return (request.changes || []).filter((row) => number(row.current_quantity) !== number(row.requested_quantity) || number(row.current_ratio) !== number(row.requested_ratio)).map((row) => ({
			size: row.size,
			quantity: `${number(row.current_quantity)} → ${number(row.requested_quantity)}`,
			ratio: `${number(row.current_ratio)} → ${number(row.requested_ratio)}`,
		}))
	}
	if (request?.request_type === "transfer") {
		return Object.entries(request.transfers || {}).map(([size, quantity]) => {
			const current = number(request.target_original_quantities?.[size])
			return { size, quantity: `${current} → ${current + number(quantity)}`, ratio: "—", transferred: number(quantity) }
		})
	}
	return []
}

export function productionOrderApprovalRequest(command, request) {
	const types = { approve_status: "status", approve_quantity_ratio: "quantity_ratio", approve_transfer: "transfer", approve_ppo: "ppo_approval" }
	return request && types[command] === request.request_type ? request : null
}
