const ACTION_ICONS = {
	edit: "pi pi-pencil",
	build_cloth_programs: "pi pi-sitemap",
	calculate_bom: "pi pi-calculator",
	change_ppo: "pi pi-link",
}
const COMMAND_SUCCESS = {
	build_cloth_programs: "Cloth Program built",
	recalculate_cloth_program: "Cloth Program recalculated",
	calculate_bom: "BOM calculated",
	calculate_order_items: "Order Items calculated",
	change_ppo: "PPO changed",
	update_bom_additional_items: "BOM Additional Items updated",
}
export function merchLotCommandSuccess(command, lot) {
	return { severity: "success", summary: COMMAND_SUCCESS[command] || "Lot updated", detail: lot, life: 3500 }
}
export const BOX_LABELS = { qty: "Qty", ratio: "Ratio", mrp: "MRP" }

export function boxCellError(field, value) {
	return Number(value) < 0 ? `${BOX_LABELS[field]} cannot be negative.` : ""
}

export function boxGridErrors(details) {
	if (!details) return {}
	const { rows, columns, values } = boxGrid(details)
	return Object.fromEntries(
		rows.flatMap((row) => {
			const errors = columns
				.filter((column) => !column.readonly)
				.flatMap((column) => {
					const message = boxCellError(
						column.key.split(":")[1],
						values[row.key][column.key],
					)
					return message ? [[column.key, message]] : []
				})
			return errors.length ? [[row.key, Object.fromEntries(errors)]] : []
		}),
	)
}
export function merchLotActions(workspace, execute, acting = "") {
	return [
		"edit",
		"build_cloth_programs",
		"calculate_bom",
		"change_ppo",
		"calculate_order_items",
		"recalculate_cloth_program",
	]
		.filter(
			(key) =>
				workspace.capabilities?.[key]?.visible ?? workspace.capabilities?.[key]?.allowed,
		)
		.map((key) => {
			const capability = workspace.capabilities[key]
			return {
				key,
				label: capability.label,
				icon: ACTION_ICONS[key] || "pi pi-refresh",
				primary: key === "edit",
				menuOnly: ["calculate_order_items", "recalculate_cloth_program"].includes(key),
				disabled: Boolean(acting) || !capability.allowed,
				disabledReason: capability.reason,
				loading: acting === key,
				command: () => execute(key),
			}
		})
}

export function majorPieceTotal(groups) {
	return groups.reduce(
		(sum, group) =>
			sum +
			group.items.reduce((total, item) => {
				if (item.is_set_item && item.attributes[item.set_attr] !== item.major_attr_value)
					return total
				return (
					total +
					Object.values(item.values).reduce(
						(quantity, cell) => quantity + Number(cell.qty || 0),
						0,
					)
				)
			}, 0),
		0,
	)
}

export function totalsWarning(details, groups, packingCombo) {
	if (!details || !groups.length || !(Number(packingCombo) > 0)) return ""
	const boxes = details.items.reduce(
		(total, item) =>
			total +
			(details.primary_attribute
				? Object.values(item.values).reduce((sum, cell) => sum + Number(cell.qty || 0), 0)
				: Number(item.values.qty || 0)),
		0,
	)
	const pieces = majorPieceTotal(groups)
	const expected = boxes * Number(packingCombo)
	return Math.abs(pieces - expected) > 0.001
		? `Lot Order Details total ${pieces.toLocaleString("en-IN")} pieces; boxes × Packing Combo = ${expected.toLocaleString("en-IN")}. You can still save.`
		: ""
}

export function boxGrid(details) {
	const sizes = details.primary_attribute ? details.primary_attribute_values : ["default"]
	const columns = sizes.flatMap((size, index) =>
		["qty", "ratio", "mrp"].map((field) => ({
			key: `${index}:${field}`,
			label: `${size === "default" ? "" : size + " · "}${{ qty: "Qty", ratio: "Ratio", mrp: "MRP" }[field]}`,
			type: "number",
		})),
	)
	const rows = details.items.map((item, index) => ({
		key: String(index),
		label: Object.values(item.attributes).join(" / ") || `Row ${index + 1}`,
	}))
	const values = Object.fromEntries(
		rows.map((row, index) => [
			row.key,
			Object.fromEntries(
				sizes.flatMap((size, sizeIndex) =>
					["qty", "ratio", "mrp"].map((field) => [
						`${sizeIndex}:${field}`,
						(details.primary_attribute
							? details.items[index].values[size]
							: details.items[index].values)?.[field] || 0,
					]),
				),
			),
		]),
	)
	columns.push({ key: "total", label: "Total Qty", type: "number", readonly: true })
	for (const row of rows)
		values[row.key].total = sizes.reduce(
			(sum, size, index) => sum + Number(values[row.key][`${index}:qty`] || 0),
			0,
		)
	return { rows, columns, values, sizes }
}
