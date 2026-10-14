export function dprFormState(request = {}) {
	if (request.mode !== "summary") {
		return {
			summaryMode: false,
			filters: { date: request.date || "", location: request.location || "" },
		}
	}
	return {
		summaryMode: true,
		filters: {
			items: [...(request.items || [])],
			lots: [...(request.lots || [])],
			location: request.location || "",
			fromDate: request.from_date || "",
			toDate: request.to_date || "",
		},
	}
}
