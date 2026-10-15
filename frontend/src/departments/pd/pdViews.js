export const PD_ROUTES = {
	products: "pd-products",
	productNew: "pd-product-new",
	product: "pd-product",
	productEdit: "pd-product-edit",
	releases: "pd-product-releases",
	release: "pd-product-release",
	lotwiseList: "pd-lotwise-item-profits",
	lotwiseNew: "pd-lotwise-item-profit-new",
	lotwise: "pd-lotwise-item-profit",
}

const RECORD_BASES = {
	product: "/web/pd/products",
	release: "/web/pd/product-releases",
	lotwise: "/web/pd/lotwise-item-profits",
}

export function pdRecordPath(kind, name) {
	if (!RECORD_BASES[kind]) throw new Error(`Unknown PD record kind: ${kind}`)
	return `${RECORD_BASES[kind]}/${encodeURIComponent(String(name))}`
}

export const PRODUCT_TABS = [
	{ key: "basic", label: "Basic" },
	{ key: "silhouette", label: "Silhouette" },
	{ key: "trims", label: "Trims" },
	{ key: "colours", label: "Colours" },
	{ key: "graphics", label: "Graphic Designs" },
	{ key: "accessories", label: "Accessories" },
	{ key: "measurement", label: "Measurement" },
	{ key: "costing", label: "Costing" },
	{ key: "extras", label: "Extras" },
]

export function releaseTabs() {
	return PRODUCT_TABS.filter((tab) => !["costing", "extras"].includes(tab.key))
}

export const PRODUCT_FIELD_GROUPS = {
	basic: [
		{
			key: "style",
			label: "Style",
			fields: [
				"style_no",
				"item_name",
				"description",
				"season",
				"product_group",
				"brand",
				"sub_brand",
				"category",
			],
		},
		{
			key: "fabric",
			label: "Fabric",
			fields: ["fabric_details", "gsm", "dia"],
			tables: ["product_fabric_composition_details"],
		},
		{
			key: "sizes",
			label: "Sizes",
			fields: ["size_range"],
		},
		{
			key: "production",
			label: "Production setup",
			fields: ["template", "fg_item_category", "product_category", "pieces_per_box", "is_set_item"],
		},
	],
	basicTables: ["sizes", "product_fabric_composition_details"],
	colourTables: ["product_colours", "product_set_colours"],
	measurement: ["measurement", "top_measurement", "bottom_measurement"],
	extrasTables: ["product_info_extras"],
}

export const PRODUCT_EDITABLE_FIELDS = [
	"style_no",
	"item_name",
	"product_group",
	"description",
	"season",
	"fabric_details",
	"gsm",
	"dia",
	"brand",
	"sub_brand",
	"category",
	"product_category",
	"fg_item_category",
	"template",
	"pieces_per_box",
	"is_set_item",
	"size_range",
	"measurement",
	"top_measurement",
	"bottom_measurement",
	"product_image",
	"top_image",
	"bottom_image",
]

export const PRODUCT_EDITABLE_TABLES = [
	"sizes",
	"product_fabric_composition_details",
	"product_colours",
	"product_set_colours",
	"product_designs",
	"product_box_details",
	"product_info_extras",
]

const PRODUCT_COPY_FIELDS = PRODUCT_EDITABLE_FIELDS.filter(
	(fieldname) => !["product_image", "top_image", "bottom_image"].includes(fieldname),
)
const PRODUCT_COPY_TABLES = PRODUCT_EDITABLE_TABLES.filter(
	(table) => !["product_designs", "product_box_details"].includes(table),
)

const SET_ITEM_VISIBILITY = {
	product_colours: false,
	measurement: false,
	product_set_colours: true,
	top_measurement: true,
	bottom_measurement: true,
	bottom_image: true,
}

export function visibleForSetItem(fieldname, isSetItem) {
	if (!Object.hasOwn(SET_ITEM_VISIBILITY, fieldname)) return true
	return SET_ITEM_VISIBILITY[fieldname] === Boolean(isSetItem)
}

export function isFieldReadOnly(fieldname, isNew) {
	return fieldname === "style_no" && !isNew
}

export function editableValues(form) {
	const values = {}
	for (const fieldname of [...PRODUCT_EDITABLE_FIELDS, ...PRODUCT_EDITABLE_TABLES]) {
		if (!Object.hasOwn(form || {}, fieldname)) continue
		values[fieldname] = fieldname === "sizes"
			? (form[fieldname] || []).map(({ size: _size, ...row }) => row)
			: form[fieldname]
	}
	return values
}

export function productActionItems(permissions = {}, handlers = {}, { busy = false, acting = "" } = {}) {
	const definitions = [
		{ key: "edit", label: "Edit", icon: "pi pi-pencil", primary: true, allowed: permissions.can_write },
		{ key: "release", label: "Release Tech Pack", icon: "pi pi-send", allowed: permissions.can_release },
		{ key: "duplicate", label: "Duplicate", icon: "pi pi-copy", menuOnly: true, allowed: permissions.can_create },
		{ key: "delete", label: "Delete", icon: "pi pi-trash", menuOnly: true, allowed: permissions.can_delete },
	]
	return definitions.filter((action) => action.allowed).map(({ allowed: _allowed, ...action }) => ({
		...action,
		disabled: busy,
		...(action.key === "release" ? { loading: acting === "release" } : {}),
		command: handlers[action.key],
	}))
}

export const LOTWISE_STATUS_COLOURS = {
	Costing: "warning",
	"Planned Qty": "info",
	"Cutting Qty": "neutral",
	"Final Qty": "success",
	"Audited Final": "success",
}

export const LOTWISE_SECTIONS = {
	header: ["product", "item", "lot", "lot_costing_type", "disabled"],
	qtyAndRate: ["qty_rate_chart", "additional_rate"],
	clothValue: ["cloth_value", "piece_cloth_weight"],
	productionCost: ["production_cost_template", "cmt", "packing_materials", "trims"],
	tradeDiscounts: ["trade_discounts_template", "trade_discounts"],
	otherCosts: ["other_costs_template", "other_costs"],
	gst: ["gst"],
}

export const LOTWISE_TABLE_COLUMNS = {
	qty_rate_chart: ["size", "qty", "rate", "weight", "group_index", "net_rate"],
	cloth_value: [
		"yarn",
		"qty",
		"rate",
		"knitting_cost",
		"dyeing_cost",
		"compacting_cost",
		"wastage_allowance",
		"total_cost",
		"net_rate",
	],
	piece_cloth_weight: ["size", "cloth_group", "weight"],
	cmt: ["costing_name", "cost"],
	packing_materials: ["costing_name", "cost"],
	trims: ["costing_name", "cost"],
	trade_discounts: ["costing_name", "based_on", "rate", "total"],
	other_costs: ["costing_name", "based_on", "rate", "total"],
}

export const LOTWISE_COMPUTED_FIELDS = [
	"total_qty",
	"total_selling_value",
	"total_weight",
	"total_cloth_value",
	"cloth_value_per_piece",
	"production_cost_per_piece",
	"production_cost",
	"total_trade_discount",
	"total_other_cost",
	"gst_value",
	"cost_price",
	"avg_cost_per_piece",
	"avg_rate_per_piece",
	"profit",
	"profit_percent",
	"profit_percent_markdown",
]

const LOTWISE_COMPUTED_COLUMNS = {
	qty_rate_chart: ["net_rate"],
	cloth_value: ["total_cost", "net_rate"],
	trade_discounts: ["total"],
	other_costs: ["total"],
}

export function lotwiseChildMeta(table, metadata) {
	const columns = LOTWISE_TABLE_COLUMNS[table]
	if (!columns) throw new Error(`Columns for ${table} are not configured.`)
	if (!metadata) throw new Error(`Metadata for ${table} was not returned.`)
	const fields = new Map((metadata.fields || []).map((field) => [field.fieldname, field]))
	return {
		...metadata,
		fields: columns.map((fieldname) => {
			const field = fields.get(fieldname)
			if (!field) throw new Error(`Metadata for ${table}.${fieldname} was not returned.`)
			return {
				...field,
				in_list_view: 1,
				read_only: LOTWISE_COMPUTED_COLUMNS[table]?.includes(fieldname) ? 1 : field.read_only,
			}
		}),
	}
}

export function mergeComputedValues(current, computed) {
	const merged = { ...(current || {}) }
	for (const fieldname of LOTWISE_COMPUTED_FIELDS) {
		if (Object.hasOwn(computed || {}, fieldname)) merged[fieldname] = computed[fieldname]
	}
	for (const [table, columns] of Object.entries(LOTWISE_COMPUTED_COLUMNS)) {
		const currentRows = current?.[table]
		const computedRows = computed?.[table]
		if (!Array.isArray(currentRows) || !Array.isArray(computedRows)) continue
		if (currentRows.length !== computedRows.length) continue
		merged[table] = currentRows.map((row, index) => {
			const mergedRow = { ...row }
			for (const column of columns) {
				if (Object.hasOwn(computedRows[index] || {}, column)) {
					mergedRow[column] = computedRows[index][column]
				}
			}
			return mergedRow
		})
	}
	return merged
}

export function imagePayload(images) {
	return {
		placement_images: images.placement || [],
		product_trims_images: images.trims || [],
		trim_comb: images.combination || [],
		accessory_images: images.accessories || [],
	}
}

export function readableTextColour(hex) {
	const value = String(hex || "").replace("#", "")
	if (value.length < 6) return "#000"
	const [red, green, blue] = [0, 2, 4].map((start) => parseInt(value.slice(start, start + 2), 16))
	return (red * 299 + green * 587 + blue * 114) / 1000 >= 128 ? "#000" : "#fff"
}

export function moveItem(list, from, to) {
	const copy = [...list]
	if (from === to || from < 0 || to < 0 || from >= copy.length || to >= copy.length) return copy
	const [item] = copy.splice(from, 1)
	copy.splice(to, 0, item)
	return copy
}

export function renumberRows(rows) {
	return (rows || []).map((row, index) => ({ ...row, idx: index + 1 }))
}

export function cleanFileStem(filename, fallback = "Untitled") {
	const name = String(filename || "").split(/[\\/]/).pop() || ""
	const stem = name.replace(/\.[^.]+$/, "")
	const cleaned = stem.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim()
	return cleaned || fallback
}

const CHILD_IDENTITY_FIELDS = new Set([
	"creation", "docstatus", "doctype", "idx", "modified", "modified_by", "name", "owner",
	"parent", "parentfield", "parenttype",
])

function copyChildRows(rows) {
	return renumberRows((rows || []).map((row) => Object.fromEntries(
		Object.entries(row || {}).filter(([key]) => !CHILD_IDENTITY_FIELDS.has(key)),
	)))
}

export function copiedProductDraft(defaultRecord, sourceRecord) {
	const draft = { ...(defaultRecord || {}) }
	for (const fieldname of PRODUCT_COPY_FIELDS) {
		if (Object.hasOwn(sourceRecord || {}, fieldname)) draft[fieldname] = sourceRecord[fieldname]
	}
	for (const table of PRODUCT_COPY_TABLES) draft[table] = copyChildRows(sourceRecord?.[table])
	draft.style_no = ""
	return draft
}

export function copiedImageGroups(sourceImages) {
	return Object.fromEntries(
		["placement", "trims", "combination", "accessories"]
			.map((group) => [group, (sourceImages?.[group] || []).map((row) => ({ ...row }))]),
	)
}

export function addImage(
	list,
	item,
	{ allowDuplicates = false, isSetItem = false, withColours = false } = {},
) {
	if (!allowDuplicates && list.some((row) => row.image_name === item.image_name)) return list
	const row = { ...item }
	if (withColours || isSetItem) {
		Object.assign(row, { selected_colours: [], selected_part: isSetItem ? "Top" : "" })
	}
	return [...list, row]
}

export function colourOptionsFor(colours, part) {
	if (!colours?.is_set_item) return colours?.all || []
	return part === "Bottom" ? colours.bottom || [] : colours.top || []
}

function colourDetailsByName(workspaceColours) {
	const detailsByName = new Map()
	const groups = [workspaceColours?.all, workspaceColours?.top, workspaceColours?.bottom]
	for (const row of groups.flatMap((group) => group || [])) {
		if (!row?.colour) continue
		const current = detailsByName.get(row.colour) || {}
		detailsByName.set(row.colour, {
			colour_code: current.colour_code || row.colour_code || "",
			image: current.image || row.image || "",
		})
	}
	return detailsByName
}

function formColourOptions(rows, colourField, detailsByName) {
	const options = new Map()
	for (const row of rows || []) {
		const colour = row?.[colourField]
		if (!colour || options.has(colour)) continue
		const details = detailsByName.get(colour) || {}
		options.set(colour, {
			colour,
			colour_code: details.colour_code || row.colour_code || "",
			image: details.image || row.image || "",
		})
	}
	return [...options.values()]
}

export function appendProductColours(rows, options) {
	return renumberRows([
		...(rows || []),
		...(options || []).map((option) => ({
			product_colour: option.name || option.colour,
			colour_code: option.colour_code || "",
			image: option.image || "",
		})),
	])
}

export function newColourName(query, { searchSucceeded = false, exactNameExists = false } = {}) {
	const name = String(query || "").trim()
	return searchSucceeded && !exactNameExists ? name : ""
}

export function createDebouncedSearch(search, handlers, timers = {}) {
	const schedule = timers.schedule || setTimeout
	const cancelSchedule = timers.cancel || clearTimeout
	const delay = timers.delay ?? 250
	let sequence = 0
	let timer = null

	function invalidate() {
		sequence += 1
		if (timer !== null) cancelSchedule(timer)
		timer = null
		return sequence
	}

	async function run(query, requestSequence) {
		try {
			const result = await search(query)
			if (requestSequence === sequence) handlers.onResult(result)
		} catch (reason) {
			if (requestSequence === sequence) handlers.onError(reason)
		} finally {
			if (requestSequence === sequence) handlers.onSettled()
		}
	}

	function queue(query) {
		const requestSequence = invalidate()
		timer = schedule(() => {
			timer = null
			void run(query, requestSequence)
		}, delay)
	}

	function load(query) {
		return run(query, invalidate())
	}

	return { invalidate, load, queue }
}

export function mergeFilteredSelection(previous, next, visibleOptions) {
	const keyFor = (option) => option?.name ?? option?.colour ?? option
	const visibleKeys = new Set((visibleOptions || []).map(keyFor))
	const nextKeys = new Set()
	const uniqueNext = (next || []).filter((option) => {
		const key = keyFor(option)
		if (nextKeys.has(key)) return false
		nextKeys.add(key)
		return true
	})
	const preservedKeys = new Set()
	const preserved = (previous || []).filter((option) => {
		const key = keyFor(option)
		if (visibleKeys.has(key) || nextKeys.has(key) || preservedKeys.has(key)) return false
		preservedKeys.add(key)
		return true
	})
	return [...preserved, ...uniqueNext]
}

export function toggleAllColours(row, options) {
	const names = [...new Set((options || []).map((option) => option.colour).filter(Boolean))]
	const selected = new Set(row?.selected_colours || [])
	const hasAll = names.length > 0 && names.every((name) => selected.has(name))
	return { ...(row || {}), selected_colours: hasAll ? [] : names }
}

export function colourOptionsFromForm(form, workspaceColours) {
	const detailsByName = colourDetailsByName(workspaceColours)
	const isSetItem = Boolean(Number(form?.is_set_item))
	if (!isSetItem) {
		return {
			is_set_item: false,
			top: [],
			bottom: [],
			all: formColourOptions(form?.product_colours, "product_colour", detailsByName),
		}
	}
	return {
		is_set_item: true,
		top: formColourOptions(form?.product_set_colours, "top_colour", detailsByName),
		bottom: formColourOptions(form?.product_set_colours, "bottom_colour", detailsByName),
		all: [],
	}
}

export function rowsMissingTrimDetails(rows, isSetItem) {
	if (!isSetItem) return []
	return (rows || [])
		.filter((row) => !row.selected_part || !(row.selected_colours || []).length)
		.map((row) => row.image_title || "Untitled")
}

export function retainColoursForPart(row, colours) {
	const allowedColours = new Set(colourOptionsFor(colours, row.selected_part).map((colour) => colour.colour))
	return {
		...row,
		selected_colours: (row.selected_colours || []).filter((colour) => allowedColours.has(colour)),
	}
}

export function hasMinimumQuery(query) {
	return String(query || "").trim().length >= 2
}
