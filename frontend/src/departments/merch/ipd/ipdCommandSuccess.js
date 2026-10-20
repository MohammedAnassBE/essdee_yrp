export function ipdCommandSuccess(command, name) {
	const summaries = {
		approve: "IPD approved",
		revert_approval: "IPD approval reverted",
		regenerate_process_matrix: "Process matrix regenerated",
	}
	return { severity: "success", summary: summaries[command], detail: name, life: 3500 }
}
