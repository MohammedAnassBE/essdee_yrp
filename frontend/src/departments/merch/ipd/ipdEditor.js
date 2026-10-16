import { tabLabel } from "./ipdTabs.js"

export const IPD_DOCTYPE = "YRP Item Production Detail"
export const KEY_SEPARATOR = "\u001f"

const ITEM = { key: "item", label: "Item Details", short: "Item" }
const ATTRIBUTES = { key: "attributes", label: "Item Details", short: "Attributes" }
const REVIEW = { key: "review", label: "Item Details", short: "Review" }

export const GARMENT_SECTIONS = [
	ITEM,
	ATTRIBUTES,
	{ key: "packing", label: "Packing", short: "Packing" },
	{ key: "set_item", label: "Set item", short: "Set item", optional: true },
	{ key: "stitching", label: "Stitching", short: "Stitching" },
	{ key: "cutting", label: "Cutting", short: "Cutting" },
	{ key: "accessories", label: "Cloth Accessory", short: "Accessories" },
	{ key: "processes", label: "Item Details", short: "Processes" },
	REVIEW,
]

export const CLOTH_SECTIONS = [
	ITEM,
	ATTRIBUTES,
	{ key: "yarn_ratio", label: "Yarn ratio", short: "Yarn" },
	{ key: "fabric_routes", label: "Fabric routes", short: "Routes" },
	{ key: "fabric_processes", label: "Fabric processes", short: "Processes" },
	{ key: "compacting", label: "Compacting", short: "Compacting" },
	REVIEW,
]

export const SECTION_LABELS = Object.fromEntries([...GARMENT_SECTIONS, ...CLOTH_SECTIONS].map((section) => [section.key, section.label]))

export function sectionsFor(isCloth) {
	return (isCloth ? CLOTH_SECTIONS : GARMENT_SECTIONS).map((section, index) => ({ ...section, number: index + 1 }))
}

const count = (rows) => (Array.isArray(rows) ? rows.length : 0)
const plural = (value, one, many = `${one}s`) => `${value} ${value === 1 ? one : many}`
const sum = (rows, field) => (rows || []).reduce((total, row) => total + (Number(row?.[field]) || 0), 0)

const SECTION_SUMMARIES = {
	item: (draft) => ({ filled: Boolean(draft.item), hint: draft.item ? "done" : "" }),
	attributes: (draft) => ({ filled: count(draft.item_attributes) > 0, hint: count(draft.item_attributes) ? String(count(draft.item_attributes)) : "" }),
	packing: (draft) => ({
		filled: Boolean(draft.packing_attribute) && (count(draft.packing_attribute_details) > 0 || count(draft.packing_size_details) > 0),
		hint: Number(draft.packing_combo) ? `${draft.packing_combo} / box` : "",
	}),
	set_item: (draft) => ({ filled: count(draft.set_item_detail?.values) > 0, hint: count(draft.set_item_detail?.attributes) ? plural(count(draft.set_item_detail.attributes), "part") : "" }),
	stitching: (draft) => ({ filled: count(draft.stiching_item_details) > 0, hint: count(draft.stiching_item_details) ? plural(count(draft.stiching_item_details), "panel") : "" }),
	cutting: (draft) => ({ filled: count(draft.cloth_detail) > 0, hint: count(draft.cloth_detail) ? plural(count(draft.cloth_detail), "cloth") : "" }),
	accessories: (draft) => ({ filled: count(draft.item_bom) > 0, hint: count(draft.item_bom) ? plural(count(draft.item_bom), "row") : "" }),
	processes: (draft) => ({ filled: count(draft.ipd_processes) > 0, hint: count(draft.ipd_processes) ? String(count(draft.ipd_processes)) : "" }),
	yarn_ratio: (draft) => ({ filled: count(draft.yarn_ratio_details) > 0, hint: count(draft.yarn_ratio_details) ? `${sum(draft.yarn_ratio_details, "ratio")}%` : "" }),
	fabric_routes: (draft) => ({ filled: count(draft.fabric_routes) > 0, hint: count(draft.fabric_routes) ? plural(count(draft.fabric_routes), "route") : "" }),
	fabric_processes: (draft) => ({ filled: count(draft.fabric_processes) > 0, hint: count(draft.fabric_processes) ? plural(count(draft.fabric_processes), "step") : "" }),
	compacting: (draft) => ({ filled: count(draft.compacting_reference_details) > 0, hint: count(draft.compacting_reference_details) ? plural(count(draft.compacting_reference_details), "row") : "" }),
}

function reviewSummary(draft, checks) {
	if (draft.approval_status === "Approved") return { filled: true, hint: "approved" }
	const ran = Boolean(checks?.problems)
	return { filled: ran && !checks.problems.length, hint: ran && !checks.problems.length ? "ready" : "" }
}

export function sectionStates(sections, draft = {}, checks = null, { isNew = false } = {}) {
	return Object.fromEntries(sections.map((section) => [section.key, sectionState(section, draft, checks, isNew)]))
}

function sectionState(section, draft, checks, isNew) {
	if (isNew && section.key !== "item") return { state: "locked", hint: "", issues: 0 }
	if (section.key === "set_item" && !Number(draft.is_set_item)) return { state: "off", hint: "off", issues: 0 }
	const issues = Number(checks?.section_counts?.[section.key] || 0)
	if (issues) return { state: "attention", hint: plural(issues, "issue"), issues }
	const summary = section.key === "review" ? reviewSummary(draft, checks) : (SECTION_SUMMARIES[section.key]?.(draft) || { filled: false, hint: "" })
	return { state: summary.filled ? "done" : "not_started", hint: summary.hint, issues: 0 }
}

export function sectionProgress(states) {
	const active = Object.values(states).filter((entry) => entry.state !== "off")
	return { complete: active.filter((entry) => entry.state === "done").length, active: active.length }
}

export function stableStringify(value) {
	if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`
	if (value && typeof value === "object") {
		return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`
	}
	return JSON.stringify(value === undefined ? null : value)
}

export function clone(value) {
	return value === undefined ? undefined : JSON.parse(JSON.stringify(value))
}

export const READ_ONLY_KEYS = new Set([
	"name", "modified", "version", "is_cloth_item", "copied_from", "approval_status", "approved_by",
	"original_process_rows", "colour_yarn_recipes", "dependent_attribute_mapping",
])
const VIRTUAL_KEYS = new Set(["set_item_detail", "stiching_item_detail"])
const SET_FIELDS = ["is_set_item", "set_item_attribute", "major_attribute_value"]
const SET_TRIGGERS = new Set(["packing_attribute_details", ...SET_FIELDS, "set_item_detail"])
const STITCH_TRIGGERS = new Set(["packing_attribute_details", ...SET_FIELDS, "set_item_detail", "stiching_item_details", "stiching_item_detail"])

export function changedKeys(draft = {}, clean = {}) {
	const keys = new Set([...Object.keys(draft), ...Object.keys(clean)])
	return [...keys].filter((key) => stableStringify(draft[key]) !== stableStringify(clean[key]))
}

export function dirtyPatch(draft = {}, clean = {}, { isNew = false } = {}) {
	const changed = changedKeys(draft, clean)
	const patch = {}
	for (const key of changed) {
		if (VIRTUAL_KEYS.has(key) || READ_ONLY_KEYS.has(key) || (key === "item" && !isNew) || isJsonWriteBlocked(draft, key)) continue
		patch[key] = clone(draft[key])
	}
	if (Number(draft.is_set_item) && changed.some((key) => SET_TRIGGERS.has(key))) patch.set_item_detail = clone(draft.set_item_detail)
	if (count(draft.stiching_item_detail?.values) && changed.some((key) => STITCH_TRIGGERS.has(key))) {
		patch.stiching_item_detail = clone(draft.stiching_item_detail)
	}
	return patch
}

const isPanelWise = (draft) => Boolean(Number(draft.enable_panel_wise_consumption_matrix))
const isAssortmentMode = (draft) => Boolean(Number(draft.based_on_other_attribute_mapping)) && !draft.packing_mode

export function isJsonWriteBlocked(draft = {}, key) {
	if (["cutting_items_json", "cutting_cloths_json"].includes(key)) return isPanelWise(draft)
	if (["panel_wise_consumption_matrix_json", "panel_wise_cloth_mapping_json"].includes(key)) return !isPanelWise(draft)
	if (key === "packing_assortment_json") return !isAssortmentMode(draft)
	return false
}

export const GRID_FIELDS = {
	set_combination: "set_item_detail",
	stitching_combination: "stiching_item_detail",
	cutting_items: "cutting_items_json",
	cutting_cloths: "cutting_cloths_json",
	cloth_accessory: "cloth_accessory_json",
	stiching_accessory: "stiching_accessory_json",
	packing_assortment: "packing_assortment_json",
	packing_sizes: "packing_size_details",
	panel_wise_consumption: "panel_wise_consumption_matrix_json",
	panel_wise_cloth_mapping: "panel_wise_cloth_mapping_json",
}

const PANEL = ["panel_wise_consumption", "panel_wise_cloth_mapping"]
export const CHOICES = "cutting_attribute_choices"
const PACKING_ROWS = ["set_combination", "stitching_combination", "cutting_items", "cutting_cloths", "cloth_accessory", "stiching_accessory", "packing_assortment", ...PANEL]
const SET_GRIDS = ["set_combination", "stitching_combination", "cutting_items", "cutting_cloths", "cloth_accessory", "stiching_accessory"]
const SIZE_GRIDS = ["packing_sizes", "packing_assortment", "panel_wise_consumption"]

export const GRID_DEPENDENCIES = {
	packing_attribute: PACKING_ROWS,
	packing_attribute_details: PACKING_ROWS,
	primary_item_attribute: SIZE_GRIDS,
	packing_mode: SIZE_GRIDS,
	based_on_other_attribute_mapping: SIZE_GRIDS,
	pack_out_stage: ["packing_assortment"],
	dependent_attribute: ["packing_assortment", CHOICES],
	stiching_attribute: ["stitching_combination", "cutting_items", CHOICES, ...PANEL],
	stiching_in_stage: [CHOICES, "cutting_items", ...PANEL],
	stiching_item_details: ["stitching_combination", "cutting_items", "cutting_cloths", ...PANEL],
	is_set_item: [...SET_GRIDS, CHOICES],
	set_item_attribute: [...SET_GRIDS, CHOICES],
	major_attribute_value: SET_GRIDS,
	stiching_major_attribute_value: ["stitching_combination"],
	is_same_packing_attribute: ["stitching_combination"],
	set_item_detail: ["stitching_combination", "cutting_items", "cutting_cloths", "cloth_accessory", "stiching_accessory", ...PANEL],
	stiching_item_detail: ["cutting_items", ...PANEL],
	cutting_attributes: ["cutting_items"],
	cloth_attributes: ["cutting_cloths", "panel_wise_cloth_mapping"],
	accessory_attributes: ["cloth_accessory", "stiching_accessory"],
	accessory_clothtype_json: ["cloth_accessory", "stiching_accessory"],
	cloth_detail: ["cutting_cloths", "stiching_accessory", "panel_wise_cloth_mapping"],
	enable_panel_wise_consumption_matrix: PANEL,
}

export const GRID_PHASES = [
	[CHOICES, "set_combination"],
	["stitching_combination"],
	["cutting_items", "cutting_cloths", "cloth_accessory", "stiching_accessory", "packing_assortment", "packing_sizes"],
	PANEL,
]

export function gridsForChange(fieldnames) {
	return [...new Set(fieldnames.flatMap((fieldname) => GRID_DEPENDENCIES[fieldname] || []))]
}

export function gridPhases(grids) {
	const wanted = new Set(grids)
	return GRID_PHASES.map((phase) => phase.filter((grid) => wanted.has(grid))).filter((phase) => phase.length)
}

export function gridsReadingAttribute(attribute, draft = {}) {
	const grids = new Set()
	if (attribute === draft.packing_attribute) gridsForChange(["packing_attribute"]).forEach((grid) => grids.add(grid))
	if (attribute === draft.primary_item_attribute) gridsForChange(["primary_item_attribute"]).forEach((grid) => grids.add(grid))
	if (attribute === draft.stiching_attribute) gridsForChange(["stiching_attribute"]).forEach((grid) => grids.add(grid))
	if (attribute === draft.set_item_attribute) gridsForChange(["set_item_attribute"]).forEach((grid) => grids.add(grid))
	for (const fieldname of ["cutting_attributes", "cloth_attributes", "accessory_attributes"]) {
		if ((draft[fieldname] || []).includes(attribute)) gridsForChange([fieldname]).forEach((grid) => grids.add(grid))
	}
	return [...grids]
}

const isBlank = (value) => value === null || value === undefined || value === ""
const isEmptyObject = (value) => !value || (typeof value === "object" && !Object.keys(value).length)

export const ITEM_GRID_SPECS = {
	cutting_items: { carry: ["Dia", "Weight", "Required GSM"], keepStoredSelectList: true },
	cutting_cloths: { carry: ["Cloth"] },
	cloth_accessory: { carry: ["Dia", "Weight"] },
}

function itemKeyColumns(grid, carry) {
	return (grid?.attributes || []).filter((attribute) => !carry.includes(attribute))
}

function rowKey(row, columns) {
	return columns.map((column) => row?.[column] ?? "").join(KEY_SEPARATOR)
}

export function mergeItems(skeleton, current, spec) {
	const carry = spec.carry
	const newColumns = itemKeyColumns(skeleton, carry)
	const oldColumns = itemKeyColumns(current, carry)
	const shared = newColumns.filter((column) => oldColumns.includes(column))
	const oldRows = current?.items || []
	const matched = new Set()
	const items = (skeleton?.items || []).map((row) => {
		const candidates = oldRows.filter((old) => shared.every((column) => (old[column] ?? "") === (row[column] ?? "")))
		candidates.forEach((old) => matched.add(old))
		return { ...row, ...agreedValues(candidates, carry) }
	})
	const dropped = oldRows.filter((row) => !matched.has(row) && carry.some((field) => !isBlank(row[field]))).length
	const selectList = spec.keepStoredSelectList && current && Object.hasOwn(current, "select_list") ? current.select_list : skeleton?.select_list
	const value = { ...skeleton, items }
	if (selectList !== undefined) value.select_list = selectList
	return { value, dropped }
}

function agreedValues(candidates, fields) {
	const values = {}
	for (const field of fields) {
		const seen = candidates.map((row) => row[field])
		if (seen.length && seen.every((value) => !isBlank(value) && stableStringify(value) === stableStringify(seen[0]))) values[field] = seen[0]
	}
	return values
}

export function mergeCombination(skeleton, current) {
	const cells = new Map()
	for (const row of current?.values || []) {
		for (const [part, value] of Object.entries(row.val || {})) cells.set(`${row.major_attribute}${KEY_SEPARATOR}${part}`, value)
	}
	const used = new Set()
	const values = (skeleton?.values || []).map((row) => ({
		major_attribute: row.major_attribute,
		val: Object.fromEntries((skeleton.attributes || []).map((part) => {
			const key = `${row.major_attribute}${KEY_SEPARATOR}${part}`
			used.add(key)
			const typed = cells.get(key)
			return [part, isBlank(typed) ? (row.val?.[part] ?? null) : typed]
		})),
	}))
	const dropped = [...cells].filter(([key, value]) => !used.has(key) && !isBlank(value)).length
	return { value: { ...skeleton, attributes: [...(skeleton?.attributes || [])], values }, dropped }
}

function stitchingAccessoryKey(row, setAttribute) {
	return [row.accessory, setAttribute ? row[setAttribute] ?? "" : "", row.major_colour].join(KEY_SEPARATOR)
}

export function mergeStitchingAccessory(skeleton, current) {
	const oldRows = new Map((current?.items || []).map((row) => [stitchingAccessoryKey(row, current.set_attr), row]))
	const used = new Set()
	const items = (skeleton?.items || []).map((row) => {
		const key = stitchingAccessoryKey(row, skeleton.set_attr)
		used.add(key)
		const old = oldRows.get(key)
		return { ...row, ...(old ? agreedValues([old], ["accessory_colour", "cloth_type"]) : {}) }
	})
	const dropped = [...oldRows].filter(([key, row]) => !used.has(key) && (!isBlank(row.accessory_colour) || !isBlank(row.cloth_type))).length
	return { value: { ...skeleton, items }, dropped }
}

function assortmentKey(box, row, attributes) {
	const pairs = [...attributes].sort().map((attribute) => `${attribute}=${row[attribute] ?? ""}`)
	return [box.separator_value, ...pairs].join(KEY_SEPARATOR)
}

export function mergeAssortment(skeleton, current) {
	const quantities = new Map()
	for (const box of current?.boxes || []) {
		for (const row of box.rows || []) quantities.set(assortmentKey(box, row, current.assortment_attributes || []), row.qty)
	}
	const used = new Set()
	const boxes = (skeleton?.boxes || []).map((box) => ({
		...box,
		rows: (box.rows || []).map((row) => {
			const key = assortmentKey(box, row, skeleton.assortment_attributes || [])
			used.add(key)
			const qty = quantities.get(key)
			return isBlank(qty) ? { ...row } : { ...row, qty }
		}),
	}))
	const dropped = [...quantities].filter(([key, qty]) => !used.has(key) && Number(qty)).length
	return { value: { ...skeleton, boxes }, dropped }
}

export function mergeRowsByValue(values, rows, field, makeRow) {
	const existing = new Map((rows || []).map((row) => [row[field], row]))
	const merged = (values || []).map((value) => existing.get(value) || makeRow(value))
	const kept = new Set(values || [])
	return { value: merged, dropped: (rows || []).filter((row) => !kept.has(row[field])).length }
}

export function mergeGrid(gridKey, skeleton, current) {
	if (ITEM_GRID_SPECS[gridKey]) return mergeItems(skeleton, isEmptyObject(current) ? null : current, ITEM_GRID_SPECS[gridKey])
	if (["set_combination", "stitching_combination"].includes(gridKey)) return mergeCombination(skeleton, current)
	if (gridKey === "stiching_accessory") return mergeStitchingAccessory(skeleton, isEmptyObject(current) ? null : current)
	if (gridKey === "packing_assortment") return mergeAssortment(skeleton, current)
	if (gridKey === "packing_sizes") return mergeRowsByValue(skeleton, current, "attribute_value", (value) => ({ attribute_value: value, quantity: 0 }))
	if (PANEL.includes(gridKey)) return { value: skeleton?.matrix ?? null, dropped: 0 }
	throw new Error(`Unknown IPD grid: ${gridKey}`)
}

function comparableGrid(gridKey, value) {
	if (ITEM_GRID_SPECS[gridKey] || gridKey === "stiching_accessory") return { attributes: value?.attributes || [], items: value?.items || [] }
	if (gridKey === "packing_sizes") return (value || []).map((row) => [row.attribute_value, Number(row.quantity) || 0])
	if (["set_combination", "stitching_combination"].includes(gridKey)) return { attributes: value?.attributes || [], values: value?.values || [] }
	if (gridKey === "packing_assortment") return value?.boxes || []
	return value ?? null
}

export function gridDiffers(gridKey, merged, current) {
	return stableStringify(comparableGrid(gridKey, merged)) !== stableStringify(comparableGrid(gridKey, current))
}

export function packingDerived(draft = {}) {
	const rows = draft.packing_attribute_details || []
	const result = { packing_attribute_no: rows.length }
	if (Number(draft.based_on_other_attribute_mapping) && draft.packing_mode === "Size Wise Packing") result.packing_combo = 1
	else if (Number(draft.based_on_other_attribute_mapping) && draft.packing_mode === "Size Ratio Packing") {
		const total = sum(draft.packing_size_details, "quantity")
		if (total > 0) result.packing_combo = total
	} else if (!Number(draft.auto_calculate)) result.packing_combo = sum(rows, "quantity")
	return result
}

export function parseValueList(text, existing = []) {
	const seen = new Set(existing.map((value) => String(value).toLowerCase()))
	const values = []
	let duplicates = 0
	for (const part of String(text ?? "").split(/[,\n\r\t]+/)) {
		const value = part.trim()
		if (!value) continue
		if (seen.has(value.toLowerCase())) { duplicates += 1; continue }
		seen.add(value.toLowerCase())
		values.push(value)
	}
	return { values, added: values.length, duplicates }
}

export function valueListMessage({ added, duplicates }) {
	return [added ? `${added} added` : "", duplicates ? `${duplicates} already present` : ""].filter(Boolean).join(" · ")
}

export function usageMessage(usage = []) {
	return usage.map((entry) => `${entry.section}: ${entry.label}${Number(entry.count) > 1 ? ` (${entry.count})` : ""}`).join(" · ")
}

function action(key, label, icon, extra = {}) {
	return { key, label, icon, ...extra }
}

function approveAction(capabilities, { dirty, problemCount, busy, acting }) {
	const reason = dirty ? "Save changes before approving"
		: problemCount ? `Fix ${plural(problemCount, "problem")} before approving` : ""
	return action("approve", capabilities.approve.label || "Approve", "pi pi-check", {
		disabled: busy || Boolean(reason), disabledReason: reason, loading: acting === "approve",
	})
}

export function editorActions({ isNew, capabilities = {}, dirty = false, acting = "", problemCount = 0, hasItem = false, copiedFrom = "" }) {
	const busy = Boolean(acting)
	const actions = [action("save", isNew ? "Create IPD" : "Save", "pi pi-save", {
		primary: true, loading: acting === "save", disabled: busy || (isNew ? !hasItem : !dirty),
	})]
	if (!isNew && capabilities.run_checks?.allowed) actions.push(action("run_checks", "Run checks", "pi pi-check-circle", { disabled: busy, loading: acting === "checks" }))
	if (!isNew && capabilities.approve?.allowed) actions.push(approveAction(capabilities, { dirty, problemCount, busy, acting }))
	if (!isNew && capabilities.regenerate_process_matrix?.allowed) actions.push(action("regenerate_process_matrix", "Regenerate Process Matrix", "pi pi-sync", { menuOnly: true, disabled: busy || dirty, disabledReason: dirty ? "Save changes first" : "", loading: acting === "regenerate_process_matrix" }))
	if (isNew) actions.push(action("copy_from", "Copy from…", "pi pi-copy", { menuOnly: true, disabled: busy }))
	else if (capabilities.new_version?.allowed) actions.push(action("new_version", "New version from this", "pi pi-copy", { menuOnly: true, disabled: busy }))
	if (copiedFrom) actions.push(action("show_changes", "Show changes", "pi pi-eye", { menuOnly: true, disabled: busy }))
	actions.push(action("cancel", "Cancel", "pi pi-times", { menuOnly: true, disabled: busy }))
	return actions
}

export function recordActions({ approved = false, capabilities = {}, acting = "", problemCount = 0 }) {
	const busy = Boolean(acting)
	const allowed = (key) => Boolean(capabilities[key]?.allowed)
	const label = (key, fallback) => capabilities[key]?.label || fallback
	const actions = []
	if (approved) {
		if (allowed("new_version")) actions.push(action("new_version", label("new_version", "New version from this"), "pi pi-copy", { primary: true, disabled: busy }))
		if (allowed("revert_approval")) actions.push(action("revert_approval", label("revert_approval", "Revert Approval"), "pi pi-undo", { severity: "warn", disabled: busy, loading: acting === "revert_approval" }))
	} else {
		if (allowed("edit")) actions.push(action("edit", label("edit", "Edit"), "pi pi-pencil", { primary: true, disabled: busy }))
		if (allowed("approve")) actions.push(approveAction(capabilities, { dirty: false, problemCount, busy, acting }))
		if (allowed("run_checks")) actions.push(action("run_checks", "Run checks", "pi pi-check-circle", { disabled: busy, loading: acting === "checks" }))
		if (allowed("new_version")) actions.push(action("new_version", label("new_version", "New version from this"), "pi pi-copy", { menuOnly: true, disabled: busy }))
	}
	if (allowed("regenerate_process_matrix")) {
		actions.push(action("regenerate_process_matrix", label("regenerate_process_matrix", "Regenerate Process Matrix"), "pi pi-sync", { menuOnly: true, disabled: busy, loading: acting === "regenerate_process_matrix" }))
	}
	return actions
}

export function copyDefaults(sections = []) {
	return copyClosure(sections.filter((section) => section.default || section.locked).map((section) => section.key), sections)
}

export function copyClosure(selected, sections = []) {
	const chosen = new Set([...selected, ...sections.filter((section) => section.locked).map((section) => section.key)])
	let changed = true
	while (changed) {
		changed = false
		for (const section of sections) {
			if (!chosen.has(section.key) || section.locked) continue
			if ((section.requires || []).some((key) => !chosen.has(key))) { chosen.delete(section.key); changed = true }
		}
	}
	return sections.map((section) => section.key).filter((key) => chosen.has(key))
}

export function toggleCopySection(selected, key, checked, sections = []) {
	const chosen = new Set(selected)
	const byKey = new Map(sections.map((section) => [section.key, section]))
	if (byKey.get(key)?.locked) return copyClosure([...chosen], sections)
	if (checked) addWithRequires(chosen, key, byKey)
	else chosen.delete(key)
	return copyClosure([...chosen], sections)
}

function addWithRequires(chosen, key, byKey) {
	if (chosen.has(key)) return
	chosen.add(key)
	for (const required of byKey.get(key)?.requires || []) addWithRequires(chosen, required, byKey)
}

function replaceLabels(list, renames) {
	return Array.isArray(list) ? list.map((value) => (renames.has(value) ? renames.get(value) : value)) : list
}

export function renameClothLabel(draft = {}, oldLabel, newLabel) {
	return renameClothLabels(draft, new Map([[oldLabel, newLabel]]))
}

export function renameClothLabels(draft = {}, renames = new Map()) {
	renames = new Map([...renames].filter(([oldLabel, newLabel]) => oldLabel && oldLabel !== newLabel))
	if (!renames.size) return {}
	const rename = (value) => (renames.has(value) ? renames.get(value) : value)
	const patch = {}
	const cloths = draft.cutting_cloths_json
	if (!isEmptyObject(cloths)) {
		patch.cutting_cloths_json = { ...cloths, select_list: replaceLabels(cloths.select_list, renames),
			items: (cloths.items || []).map((row) => (renames.has(row.Cloth) ? { ...row, Cloth: rename(row.Cloth) } : row)) }
	}
	const accessories = draft.stiching_accessory_json
	if (!isEmptyObject(accessories)) {
		patch.stiching_accessory_json = { ...accessories, select_list: replaceLabels(accessories.select_list, renames),
			items: (accessories.items || []).map((row) => (renames.has(row.cloth_type) ? { ...row, cloth_type: rename(row.cloth_type) } : row)) }
	}
	const mapping = draft.panel_wise_cloth_mapping_json
	if (!isEmptyObject(mapping)) patch.panel_wise_cloth_mapping_json = renamePanelCloth(mapping, renames, rename)
	return Object.fromEntries(Object.entries(patch).filter(([key, value]) => stableStringify(value) !== stableStringify(draft[key])))
}

function renamePanelCloth(mapping, renames, rename) {
	const renameCell = (cell) => (renames.has(cell?.cloth) ? { ...cell, cloth: rename(cell.cloth) } : cell)
	return {
		...mapping,
		cloth_options: replaceLabels(mapping.cloth_options, renames),
		panels: (mapping.panels || []).map((panel) => ({
			...panel,
			rows: (panel.rows || []).map((row) => ({
				...row, values: Object.fromEntries(Object.entries(row.values || {}).map(([key, cell]) => [key, renameCell(cell)])),
			})),
		})),
	}
}

export function problemsFor(checks, sectionKey) {
	return (checks?.problems || []).filter((problem) => problem.section === sectionKey)
}

export function gridErrors(checks, field) {
	const errors = {}
	for (const problem of checks?.problems || []) {
		if (problem.field !== field || isBlank(problem.row_key)) continue
		const column = problem.column ?? ""
		errors[problem.row_key] = { ...(errors[problem.row_key] || {}), [column]: problem.message }
	}
	return errors
}

export function problemTitle(problem, sections = []) {
	const label = tabLabel(problem)
	const newRow = /^new:(\d+)$/.exec(String(problem.row_key || ""))
	const row = problem.row_label || (newRow ? `New row ${Number(newRow[1]) + 1}` : problem.row_key ? String(problem.row_key).split(KEY_SEPARATOR).filter(Boolean).join(" · ") : problem.label)
	return [label, row || ""].filter(Boolean).join(" · ")
}

export function checksBadge(checks, running = false) {
	if (running) return { tone: "running", label: "Checking…" }
	if (!checks?.problems) return { tone: "idle", label: "Not run" }
	if (checks.problems.length) return { tone: "danger", label: plural(checks.problems.length, "problem") }
	if (checks.warnings?.length) return { tone: "warning", label: plural(checks.warnings.length, "warning") }
	return { tone: "success", label: "All clear" }
}

export function invalidCellMessage(count) {
	return `${plural(count, "grid cell")} ${count === 1 ? "holds a value that was" : "hold values that were"} not accepted. Correct or clear the highlighted ${count === 1 ? "cell" : "cells"} before saving.`
}

export function isStaleWriteError(message) {
	return /changed after you opened it/i.test(String(message || ""))
}
