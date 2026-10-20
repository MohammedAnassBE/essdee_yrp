export function lotOcrView(payload) {
	const data = payload || {}
	return {
		sizes: data.sizes || [],
		processRows: Object.entries(data.processes || {}).map(([name, process]) => ({
			name,
			...process,
			wo_list: process?.wo_list || [],
			cp_list: process?.cp_list || [],
			data: process?.data || {},
		})),
		dispatchDetail: data.dispatch_detail || {},
		finishingPlans: data.finishing_plan_list || [],
		totalDispatch: data.total_dispatch || 0,
	}
}
