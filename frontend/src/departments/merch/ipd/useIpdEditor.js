import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, reactive, readonly, ref, shallowRef } from "vue"
import { useRoute, useRouter } from "vue-router"

import {
	checkIpd,
	executeIpdCommand,
	getAttributeValueUsage,
	getIpdEditor,
	getIpdGrids,
	saveIpd,
	saveIpdAttributeValues,
	saveIpdBomMapping,
} from "../../../api/merch.js"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import { MERCH_ROUTES, ipdEditRoute, ipdRoute } from "../merchViews.js"
import {
	CHOICES,
	GRID_FIELDS,
	clone,
	dirtyPatch,
	editorActions,
	gridDiffers,
	gridErrors,
	gridPhases,
	gridsForChange,
	gridsReadingAttribute,
	invalidCellMessage,
	isStaleWriteError,
	mergeGrid,
	problemsFor,
	sectionStates,
	sectionsFor,
	stableStringify,
} from "./ipdEditor.js"

import { createFocusRegistry } from "./ipdFocus.js"
import { problemTab, tabLabel } from "./ipdTabs.js"

export const IPD_EDITOR_KEY = Symbol("ipd-editor")
const GRID_DEBOUNCE_MS = 400
const CHECK_IDLE_MS = 1200

export function useIpdEditor(initialName) {
	const route = useRoute()
	const router = useRouter()
	const toast = useToast()
	const payload = shallowRef(null)
	const draft = reactive({})
	const cleanValues = shallowRef({})
	const cleanStrings = new Map()
	const dirtyKeys = ref(new Set())
	const context = ref({})
	const grids = ref({})
	const gridDrift = ref({})
	const checks = ref(null)
	const checksRunning = ref(false)
	const loading = ref(true)
	const acting = ref("")
	const loadError = ref("")
	const actionError = ref("")
	const savedAt = ref(null)
	const navigatingInternally = ref(false)
	const { registerFocus, focusProblem } = createFocusRegistry()
	const invalidGridCells = reactive(new Map())
	const invalidCellCount = computed(() => [...invalidGridCells.values()].reduce((total, entry) => total + entry.count, 0))
	const firstInvalidCell = computed(() => invalidGridCells.values().next().value?.cells[0] || null)
	const pendingGrids = new Set()
	let gridTimer = null
	let checkTimer = null
	let gridSequence = 0
	let checkSequence = 0
	let loadSequence = 0
	let isUnmounted = false

	const record = computed(() => payload.value?.record || {})
	const name = computed(() => record.value.name || "")
	const isNew = computed(() => !name.value)
	const capabilities = computed(() => payload.value?.capabilities || {})
	const fields = computed(() => payload.value?.fields || {})
	const isDirty = computed(() => dirtyKeys.value.size > 0)
	const sections = computed(() => sectionsFor(Boolean(record.value.is_cloth_item)))
	const states = computed(() => sectionStates(sections.value, draft, checks.value, { isNew: isNew.value }))
	const problemCount = computed(() => checks.value?.problems?.length || 0)
	const hasStaleError = computed(() => isStaleWriteError(actionError.value))
	const shellWorkspace = computed(() => payload.value ? { ...payload.value, record: { ...record.value, doctype: "YRP Item Production Detail" } } : {})

	function isCurrent(sequence, current) { return !isUnmounted && sequence === current }
	function patch() { return dirtyPatch(draft, cleanValues.value, { isNew: isNew.value }) }

	function resetDraft(values) {
		for (const key of Object.keys(draft)) delete draft[key]
		Object.assign(draft, clone(values || {}))
		cleanValues.value = clone(values || {})
		cleanStrings.clear()
		for (const [key, value] of Object.entries(values || {})) cleanStrings.set(key, stableStringify(value))
		dirtyKeys.value = new Set()
	}
	function applyPayload(result) {
		payload.value = result
		context.value = clone(result.context || {})
		grids.value = clone(result.grids || {})
		resetDraft(result.values)
		const errors = result.grid_errors || {}
		gridDrift.value = Object.fromEntries(Object.entries(grids.value).map(([gridKey, skeleton]) => [gridKey, storedDrift(gridKey, skeleton, errors[gridKey])]))
		showMessages(result.messages)
	}
	function storedDrift(gridKey, skeleton, error = "") {
		if (!skeleton || !GRID_FIELDS[gridKey]) return { differs: false, dropped: 0, error: error || "" }
		const current = draft[GRID_FIELDS[gridKey]]
		const merged = mergeGrid(gridKey, skeleton, current)
		return { differs: gridDiffers(gridKey, merged.value, current), dropped: merged.dropped, error: "" }
	}
	function showMessages(messages) {
		for (const message of messages || []) {
			toast.add({ severity: message.indicator === "red" ? "error" : "warn", summary: message.title || "Item Production Detail", detail: message.message, life: 6000 })
		}
	}

	async function load(target = initialName) {
		const sequence = ++loadSequence
		loading.value = true
		loadError.value = ""
		actionError.value = ""
		checks.value = null
		try {
			const result = await getIpdEditor(target || null)
			if (!isCurrent(sequence, loadSequence)) return
			if (redirectIfReadOnly(result)) return
			applyPayload(result)
			if (!isNew.value) runChecks()
		} catch (reason) {
			if (isCurrent(sequence, loadSequence)) loadError.value = reason?.message || "Unable to load this IPD."
		} finally {
			if (isCurrent(sequence, loadSequence)) loading.value = false
		}
	}
	function redirectIfReadOnly(result) {
		const recordName = result?.record?.name
		if (!recordName || result.capabilities?.edit?.allowed) return false
		router.replace(recordLocation(recordName, result.record.modified))
		return true
	}

	function setValue(fieldname, value, { skipGrids = null } = {}) {
		draft[fieldname] = clone(value)
		markDirty(fieldname)
		const grids = gridsForChange([fieldname]).filter((grid) => !skipGrids?.has(grid))
		if (grids.length) queueGrids(grids)
		scheduleChecks()
	}
	function setValues(values) {
		for (const [fieldname, value] of Object.entries(values || {})) setValue(fieldname, value)
	}
	function markDirty(fieldname) {
		const next = new Set(dirtyKeys.value)
		if (stableStringify(draft[fieldname]) === (cleanStrings.get(fieldname) ?? stableStringify(undefined))) next.delete(fieldname)
		else next.add(fieldname)
		dirtyKeys.value = next
	}

	function queueGrids(gridKeys) {
		if (isNew.value) return
		gridKeys.forEach((grid) => pendingGrids.add(grid))
		clearTimeout(gridTimer)
		gridTimer = setTimeout(flushGrids, GRID_DEBOUNCE_MS)
	}
	async function flushGrids() {
		const wanted = new Set(pendingGrids)
		pendingGrids.clear()
		const sequence = ++gridSequence
		try {
			for (const phase of gridPhases([...wanted])) {
				const snapshot = Object.fromEntries(phase.map((grid) => [grid, stableStringify(draft[GRID_FIELDS[grid]])]))
				const result = await getIpdGrids(name.value, patch(), phase)
				if (!isCurrent(sequence, gridSequence)) return
				const errors = result?.grid_errors || {}
				for (const [gridKey, skeleton] of Object.entries(result?.grids || {})) applySkeleton(gridKey, skeleton, snapshot[gridKey], wanted, errors[gridKey])
			}
		} catch (reason) {
			if (isCurrent(sequence, gridSequence)) actionError.value = reason?.message || "Unable to refresh the grids."
		}
	}
	function applySkeleton(gridKey, skeleton, snapshot, wanted, error = "") {
		if (gridKey === CHOICES) { if (Array.isArray(skeleton)) context.value = { ...context.value, cutting_attribute_choices: skeleton }; return }
		grids.value = { ...grids.value, [gridKey]: skeleton }
		const field = GRID_FIELDS[gridKey]
		if (!field) return
		if (!skeleton) { gridDrift.value = { ...gridDrift.value, [gridKey]: { differs: false, dropped: 0, error: error || "" } }; return }
		if (snapshot !== undefined && snapshot !== stableStringify(draft[field])) { queueGrids([gridKey]); return }
		const merged = mergeGrid(gridKey, skeleton, draft[field])
		if (gridDiffers(gridKey, merged.value, draft[field])) setValue(field, merged.value, { skipGrids: wanted })
		gridDrift.value = { ...gridDrift.value, [gridKey]: { differs: false, dropped: merged.dropped, error: "" } }
	}
	function applyGrid(gridKey) {
		const skeleton = grids.value[gridKey]
		if (!skeleton || !GRID_FIELDS[gridKey]) return
		applySkeleton(gridKey, skeleton, undefined, new Set())
	}
	function refreshGrids(gridKeys) { queueGrids(gridKeys) }

	function scheduleChecks() {
		clearTimeout(checkTimer)
		checkSequence += 1
		checksRunning.value = false
		if (!isNew.value && isDirty.value) checkTimer = setTimeout(runChecks, CHECK_IDLE_MS)
	}
	async function runChecks() {
		if (isNew.value) return null
		clearTimeout(checkTimer)
		const sequence = ++checkSequence
		checksRunning.value = true
		try {
			const result = await checkIpd(name.value, patch())
			if (isCurrent(sequence, checkSequence)) checks.value = result
			return result
		} catch (reason) {
			if (isCurrent(sequence, checkSequence)) actionError.value = reason?.message || "Unable to run the checks."
			return null
		} finally {
			if (isCurrent(sequence, checkSequence)) checksRunning.value = false
		}
	}

	function reportInvalidCells(gridId, count, location = {}) {
		if (count) invalidGridCells.set(gridId, {
			count, cells: (location.cells || []).map((cell) => ({
				field: location.field, tab: problemTab(location),
				row_key: cell.rowKey, column: cell.colKey, focusCell: location.focusCell,
			})),
		})
		else invalidGridCells.delete(gridId)
	}
	function hasInvalidCells() {
		if (!invalidCellCount.value) return false
		actionError.value = `${tabLabel(firstInvalidCell.value)}: ${invalidCellMessage(invalidCellCount.value)}`
		return true
	}
	async function save() {
		if (isNew.value) return createDraft()
		if (acting.value || !isDirty.value || hasInvalidCells()) return
		await persist("save", () => saveIpd(patch(), { name: name.value, expectedModified: record.value.modified }))
		if (!actionError.value) toast.add({ severity: "success", summary: "IPD saved", detail: name.value, life: 3500 })
	}
	async function createDraft() {
		if (!isNew.value || acting.value || !draft.item || hasInvalidCells()) return
		const created = await persist("save", () => saveIpd(patch(), {}))
		if (!created) return
		navigatingInternally.value = true
		try {
			await router.replace(ipdEditRoute(created, { hash: route.hash, state: preserveListNavigationState(created, record.value.modified) }))
		} finally {
			navigatingInternally.value = false
		}
	}
	async function persist(kind, request) {
		const sent = new Map(Object.keys(draft).map((key) => [key, stableStringify(draft[key])]))
		const edits = {}
		acting.value = kind
		actionError.value = ""
		try {
			const result = await request()
			for (const [key, value] of Object.entries(draft)) if (stableStringify(value) !== sent.get(key)) edits[key] = clone(value)
			applyPayload(result)
			setValues(edits)
			savedAt.value = new Date()
			runChecks()
			return result.record?.name || null
		} catch (reason) {
			actionError.value = reason?.message || "Unable to save this IPD."
			return null
		} finally {
			acting.value = ""
		}
	}

	async function approve() {
		if (acting.value || isDirty.value) return
		acting.value = "approve"
		actionError.value = ""
		try {
			const result = await executeIpdCommand(name.value, "approve", { expectedModified: record.value.modified })
			toast.add({ severity: "success", summary: "IPD approved", detail: name.value, life: 3500 })
			await router.push(recordLocation(name.value, result?.record?.modified))
		} catch (reason) {
			actionError.value = reason?.message || "Unable to approve this IPD."
		} finally {
			acting.value = ""
		}
	}

	async function regenerate() {
		if (acting.value || isDirty.value) return
		acting.value = "regenerate_process_matrix"
		actionError.value = ""
		try {
			await executeIpdCommand(name.value, "regenerate_process_matrix", { expectedModified: record.value.modified })
			await load(name.value)
			toast.add({ severity: "success", summary: "Process matrix regenerated", detail: name.value, life: 3500 })
		} catch (reason) {
			actionError.value = reason?.message || "Unable to regenerate the process matrix."
		} finally {
			acting.value = ""
		}
	}

	async function saveAttributeValues(attribute, values) {
		const entry = (context.value.attributes || []).find((candidate) => candidate.attribute === attribute)
		if (!entry) throw new Error(`${attribute} is not an attribute of this IPD.`)
		const result = await saveIpdAttributeValues(name.value, attribute, values, entry.mapping_modified)
		const { grids_stale: stale = null, ...updated } = result || {}
		context.value = { ...context.value, attributes: context.value.attributes.map((candidate) => candidate.attribute === attribute ? { ...candidate, ...updated } : candidate) }
		queueGrids(stale || gridsReadingAttribute(attribute, draft))
		return updated
	}
	async function valueUsage(attribute, values) {
		const result = await getAttributeValueUsage(name.value, attribute, values, patch())
		return result?.usage || {}
	}
	async function saveBomMapping(bomRow, rows) {
		const current = context.value.bom_mappings?.[bomRow]
		if (!current) throw new Error("This BOM row has no attribute mapping yet. Save the IPD to create it.")
		const result = await saveIpdBomMapping(name.value, bomRow, rows, current.mapping_modified)
		context.value = { ...context.value, bom_mappings: { ...(context.value.bom_mappings || {}), ...(result?.bom_mappings || {}) } }
		return result
	}

	function fieldSchema(fieldname) {
		return { fieldname, label: fieldname, fieldtype: "Data", ...(fields.value[fieldname] || {}) }
	}

	const actions = computed(() => editorActions({
		isNew: isNew.value, capabilities: capabilities.value, dirty: isDirty.value, acting: acting.value,
		problemCount: problemCount.value, hasItem: Boolean(draft.item), copiedFrom: record.value.copied_from || "",
	}))
	const api = reactive({
		draft: readonly(draft), context, grids, gridDrift, fields, record, checks, isNew, sections, states,
		capabilities, isDirty, acting, readonly: false, approve,
		problemsFor: (sectionKey) => problemsFor(checks.value, sectionKey),
		cellError: (field, rowKey, column) => gridErrors(checks.value, field)?.[rowKey]?.[column ?? ""] || "",
		gridErrors: (field) => gridErrors(checks.value, field),
		setValue, setRows: setValue, setJson: setValue, setValues,
		refreshGrids, applyGrid, saveAttributeValues, valueUsage, saveBomMapping, registerFocus, fieldSchema,
	})
	const invalidRegistry = { report: reportInvalidCells }

	function recordLocation(recordName = name.value, modified = record.value.modified) {
		return ipdRoute(recordName, { hash: route.hash, state: preserveListNavigationState(recordName, modified) })
	}
	function cancel() {
		return isNew.value ? router.push({ name: MERCH_ROUTES.ipds }) : router.push(recordLocation())
	}
	function followName(nextName) {
		if ((nextName || "") === name.value) return
		load(nextName)
	}

	onBeforeUnmount(() => {
		isUnmounted = true
		clearTimeout(gridTimer)
		clearTimeout(checkTimer)
	})
	load()
	return {
		api, invalidRegistry, payload, draft, record, name, isNew, capabilities, context, grids, sections, states, checks, checksRunning,
		loading, acting, loadError, actionError, savedAt, isDirty, hasStaleError, navigatingInternally, shellWorkspace, actions,
		load, save, createDraft, runChecks, approve, regenerate, cancel, followName, focusProblem, firstInvalidCell,
	}
}
