export const productionOrderItemFilters = {
	has_variants: 1,
	variant_of: ["is", "not set"],
	disabled: 0,
}

export const productionOrderStatusOptions = [
	{ label: "Draft", value: "Draft", filters: [["docstatus", "=", 0], ["status", "in", ["Draft", ""]]] },
	{ label: "PPO Request", value: "PPO Request", filters: [["docstatus", "=", 0], ["status", "=", "PPO Request"]] },
	...["Open", "Pending Request", "Item Changed", "Not Processed", "Closed"].map((status) => ({
		label: status,
		value: status,
		filters: [["docstatus", "=", 1], ["status", "=", status]],
	})),
	{ label: "Cancelled", value: "Cancelled", filters: [["docstatus", "=", 2]] },
]
