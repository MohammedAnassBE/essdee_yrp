import { formatDisplayDate } from "../../../utils/dateFormat.js"

export const LOT_DETAIL_GROUPS = [
	{
		key: "order",
		label: "Order",
		icon: "pi pi-shopping-bag",
		description: "Sales order, season and ownership",
		fields: ["production_order", "season", "assigned_person", "version", "capacity_planning"],
	},
	{
		key: "production",
		label: "Production",
		icon: "pi pi-cog",
		description: "Production detail and cloth settings",
		fields: [
			"production_detail",
			"primary_item_attribute",
			"size_set_colour",
			"uom",
			"cloth_excess_percentage",
		],
	},
	{
		key: "packing",
		label: "Packing",
		icon: "pi pi-box",
		description: "Pack stages and total order quantity",
		fields: ["pack_in_stage", "pack_out_stage", "packing_uom", "total_order_quantity"],
	},
	{
		key: "bom",
		label: "BOM",
		icon: "pi pi-list",
		description: "Last BOM calculation",
		fields: ["total_quantity", "last_calculated_time"],
	},
	{
		key: "transfer",
		label: "Transfer",
		icon: "pi pi-arrow-right-arrow-left",
		description: "Lot transfer state",
		fields: ["has_transferred", "is_transferred", "transferred_lot"],
	},
]

export function lotDetailFields(workspace = {}) {
	const fields = [...(workspace.header || []), ...(workspace.details || [])]
	const allowed = new Set(LOT_DETAIL_GROUPS.flatMap((group) => group.fields))
	return [
		...new Map(
			fields
				.filter((field) => allowed.has(field.fieldname))
				.map((field) => [field.fieldname, field]),
		).values(),
	]
}

export function bomSections(bom = {}) {
	return [
		{ key: "summary", label: "BOM Summary", rows: bom.summary },
		{ key: "additional", label: "BOM Additional Items", rows: bom.additional },
	].filter((section) => section.rows?.length)
}

export function lotTabs(workspace = {}) {
	return [
		{ key: "details", label: "Details", visible: true },
		{ key: "order-items", label: "Order Items", visible: Boolean(workspace.order_items) },
		{
			key: "order-details",
			label: "Lot Order Details",
			visible: Boolean(workspace.order_details),
		},
		{ key: "bom", label: "BOM Summary", visible: Boolean(workspace.bom) },
		{ key: "ocr", label: "OCR Detail", visible: Boolean(workspace.ocr) },
		{
			key: "fabric",
			label: "Cloth Program",
			visible: Boolean(workspace.permissions?.can_write || workspace.fabrics?.length || workspace.other_conversions?.length),
		},
	]
		.filter((tab) => tab.visible)
		.map(({ key, label }) => ({ key, label }))
}

export function orderItemRows(orderItems = {}) {
	if (Object.hasOwn(orderItems, "default_uom")) {
		orderItems = { ...orderItems, uom: orderItems.default_uom,
			attributes: orderItems.final_state_attr,
			sizes: orderItems.primary_attribute ? orderItems.primary_attribute_values : [] }
	}
	const columns = orderItems.sizes?.length ? orderItems.sizes : ["Value"]
	const rows = (orderItems.items || []).map((row, index) => ({
		index: index + 1,
		attributes: row.attributes,
		lines: ["qty", "ratio", "mrp"].map((key) =>
			orderItemLine(row, columns, key, Boolean(orderItems.sizes?.length)),
		),
	}))
	const visible = ["qty", "ratio", "mrp"].filter(
		(key) =>
			key === "qty" ||
			rows.some((row) =>
				Object.values(row.lines.find((line) => line.key === key).values).some(
					(value) => value !== 0,
				),
			),
	)
	return {
		columns,
		rows: rows.map((row) => ({
			...row,
			lines: row.lines.filter((line) => visible.includes(line.key)),
		})),
	}
}

function orderItemLine(row, columns, key, hasSizes) {
	const values = Object.fromEntries(
		columns.map((column) => [
			column,
			number(hasSizes ? row.values?.[column]?.[key] : row.values?.[key]),
		]),
	)
	return {
		key,
		label: { qty: "Qty", ratio: "Ratio", mrp: "MRP" }[key],
		values,
		total: key === "qty" ? Object.values(values).reduce((sum, value) => sum + value, 0) : null,
	}
}

export function orderDetailRows(group = {}, stages = []) {
	return (group.items || []).map((row, index) => ({
		index: index + 1,
		attributes: row.attributes,
		colour_note: row.colour_note,
		lines: stages.map(({ key, label }) => ({
			key,
			label,
			values: Object.fromEntries(
				(group.sizes || []).map((size) => [size, number(row.values?.[size]?.[key])]),
			),
			total: number(row.totals?.[key]),
		})),
	}))
}

export function weightMatrix(
	rows = [],
	{ dia = "dia", colour = "colour", weight = "weight" } = {},
) {
	const entries = rows.map((row) => ({
		dia: fieldValue(row, dia) || "",
		colour: fieldValue(row, colour) || "",
		weight: number(fieldValue(row, weight)),
	}))
	const dias = [...new Set(entries.map((row) => row.dia).filter(Boolean))].sort(
		(a, b) => diaNumber(a) - diaNumber(b) || String(a).localeCompare(String(b)),
	)
	const colours = [...new Set(entries.map((row) => row.colour))].sort((a, b) =>
		String(a).localeCompare(String(b)),
	)
	const cells = Object.fromEntries(
		dias.map((value) => [value, Object.fromEntries(colours.map((value) => [value, 0]))]),
	)
	for (const row of entries) {
		if (cells[row.dia]) cells[row.dia][row.colour] += row.weight
	}
	const diaTotals = Object.fromEntries(
		dias.map((value) => [
			value,
			Object.values(cells[value]).reduce((sum, value) => sum + value, 0),
		]),
	)
	const colourTotals = Object.fromEntries(
		colours.map((colour) => [colour, dias.reduce((sum, dia) => sum + cells[dia][colour], 0)]),
	)
	return {
		dias,
		colours,
		cells,
		diaTotals,
		colourTotals,
		total: Object.values(diaTotals).reduce((sum, value) => sum + value, 0),
	}
}

function fieldValue(row, field) {
	return typeof field === "function" ? field(row) : row[field]
}
function diaNumber(value) {
	const match = String(value || "").match(/-?\d+(?:\.\d+)?/)
	return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER
}
function number(value) {
	const parsed = Number(value)
	return Number.isFinite(parsed) ? parsed : 0
}

export function stepSections(steps = []) {
	return steps
		.filter((step) => step.rows?.length)
		.map((step) => ({
			process_name: step.process_name,
			shape: step.shape,
			outputs: step.rows.filter((row) => row.side !== "Input").map(stepRow),
			inputs: step.rows.filter((row) => row.side === "Input").map(stepRow),
		}))
}

function stepRow(row) {
	const planned = number(row.planned_weight)
	const received = number(row.received_weight)
	return { dia: row.dia, colour: row.colour, planned, received, balance: planned - received }
}

export function isChangedConversion(row) {
	return row.planned_item !== row.actual_item
}
export function visibleConversions(rows = [], includeUnchanged = false) {
	return rows.filter((row) => (includeUnchanged || isChangedConversion(row)))
}

export function planBadge(entry = {}) {
	const status = entry.plan_status || ""
	if (!status) return null
	if (status === "Built")
		return {
			text: `Plan ready ${formatDisplayDate(entry.plan_built_on, "")}`,
			severity: "success",
		}
	if (status === "Pending Approval")
		return { text: "Plan waiting for IPD approval", severity: "info" }
	if (status === "Stale") return { text: "Plan outdated — IPD changed", severity: "warn" }
	return { text: "Plan error — open the fabric row", severity: "danger" }
}

export function formatQuantity(value, digits = 3) {
	return number(value) === 0 ? "—" : quantityTotal(value, digits)
}

export function quantityTotal(value, digits = 3) {
	return number(value).toLocaleString("en-IN", { maximumFractionDigits: digits })
}

export function lotTabCount(workspace, key) {
	const counts = {
		"order-items": workspace.order_items?.items?.length || 0,
		"order-details": (workspace.order_details?.groups || []).reduce(
			(sum, group) => sum + (group.items?.length || 0),
			0,
		),
		bom: (workspace.bom?.summary?.length || 0) + (workspace.bom?.additional?.length || 0),
		fabric: workspace.fabrics?.length || 0,
	}
	return counts[key] ?? null
}

export function bomProcessGroups(rows = []) {
	const sorted = [...rows].sort(
		(a, b) =>
			String(a.process_name || "").localeCompare(String(b.process_name || "")) ||
			String(a.item || "").localeCompare(String(b.item || "")),
	)
	const groups = new Map()
	sorted.forEach((row, index) => {
		const process = row.process_name || "—"
		if (!groups.has(process)) groups.set(process, { process, rows: [] })
		groups.get(process).rows.push({ ...row, index: index + 1 })
	})
	return [...groups.values()]
}

export function bomUomTotals(rows = []) {
	const totals = new Map()
	for (const row of rows)
		totals.set(row.uom, (totals.get(row.uom) || 0) + number(row.required_qty))
	return [...totals].map(([uom, total]) => ({ uom, total }))
}

export const LOT_DOCUMENT_SECTIONS = [
	{
		key: "work_orders",
		label: "Work Orders",
		doctype: "YRP Work Order",
		title: "Work Order",
		dateField: "wo_date",
	},
	{
		key: "purchase_orders",
		label: "Purchase Orders",
		doctype: "Purchase Order",
		title: "Purchase Order",
		dateField: "transaction_date",
	},
	{
		key: "goods_received_notes",
		label: "Goods Received Notes",
		doctype: "YRP Goods Received Note",
		title: "Goods Received Note",
		dateField: "posting_date",
	},
	{
		key: "delivery_challans",
		label: "Delivery Challans",
		doctype: "YRP Delivery Challan",
		title: "Delivery Challan",
		dateField: "posting_date",
	},
]

export function lotDocumentSections(payload = {}, expanded = {}, previewLimit = 5, sections = LOT_DOCUMENT_SECTIONS) {
	return sections.filter((section) => payload[section.key]?.permitted !== false).map(
		(section) => {
			const data = payload[section.key] || { count: 0, rows: [] }
			return {
				...section,
				...data,
				visibleRows: expanded[section.key] ? data.rows : data.rows.slice(0, previewLimit),
				hasMore: data.rows.length > previewLimit,
			}
		},
	)
}

export function lotDocumentContext(doctype, row) {
	const supplier = row.supplier_name || row.supplier
	return [
		doctype === "Purchase Order" ? null : row.process_name,
		supplier,
		row.is_return ? "Return" : null,
	]
		.filter(Boolean)
		.join(" · ")
}

export function lotDocumentQuantityLine(doctype, row) {
	if (doctype === "YRP Work Order")
		return `Planned ${formatQuantity(row.planned_quantity)} · Dlv ${formatQuantity(row.total_no_of_pieces_delivered)} · Rcv ${formatQuantity(row.total_no_of_pieces_received)}`
	if (doctype === "Purchase Order")
		return `Qty ${formatQuantity(row.lot_qty)} · ${formatLotAmount(row.grand_total, row.currency)}`
	if (doctype === "YRP Goods Received Note")
		return `Rcv ${formatQuantity(row.total_received_quantity)}`
	return `Dlv ${formatQuantity(row.total_delivered_qty)}`
}

export function formatLotAmount(value, currency = "") {
	const amount = number(value).toLocaleString("en-IN", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	})
	return [currency, amount].filter(Boolean).join(" ")
}

export function formatLotSummaryValue(field, currency = "") {
	if (field.fieldtype !== "Currency") return formatQuantity(field.value)
	return number(field.value) === 0 ? "—" : formatLotAmount(field.value, currency)
}

export function formatLotTime(value) {
	const match = String(value || "").match(/^(\d{1,2}):(\d{2})/)
	return match ? `${match[1].padStart(2, "0")}:${match[2]}` : value || "—"
}

export function countLabel(count, singular, plural = `${singular}s`) {
	return `${count} ${Number(count) === 1 ? singular : plural}`
}

export function conversionProcesses(rows = []) {
	const stages = new Map()
	for (const row of rows) {
		const name = row.process_name
		if (name) stages.set(name, Math.min(stages.get(name) ?? Infinity, Number(row.process_stage_index ?? ({ knitting: 0, dyeing: 1, washing: 2 }[String(name).toLowerCase()] ?? Infinity))))
	}
	return [...stages].sort(([left, leftStage], [right, rightStage]) => leftStage - rightStage || left.localeCompare(right)).map(([name]) => name)
}

export function conversionView(rows = [], { search = "", process = "", includeUnchanged = false } = {}) {
	const query = search.trim().toLocaleLowerCase()
	const matching = rows.filter((row) => (!process || row.process_name === process) && [row.process_name, row.planned_item, row.actual_item, row.production_detail].some((value) => String(value || "").toLocaleLowerCase().includes(query)))
	return {
		rows: visibleConversions(matching, includeUnchanged),
		changed: rows.filter(isChangedConversion).length,
		routes: rows.length,
	}
}
