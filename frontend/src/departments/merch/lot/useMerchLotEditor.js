import { computed, onBeforeUnmount, reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useToast } from "primevue/usetoast"
import { getMeta } from "../../../api/frappe.js"
import { getLotProductionDetailContext, getLotProductionOrderItem } from "../../../api/purchase.js"
import { getMerchLotEditor as getLotForm, saveMerchLot as saveLot } from "../../../api/merch.js"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import { MERCH_ROUTES } from "../merchViews.js"
import {
	clearedLotContext,
	clone,
	lotEditorCleanSignature,
	lotEditorTabs,
	lotSavePayload,
} from "../../purchase/lot/lotEditor.js"
import { boxGridErrors } from "./merchLotViews.js"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../../utils/newDocumentDefaults.js"
import { withSavedHandoff } from "../../../utils/documentLiveState.js"

export function useMerchLotEditor(lotId) {
	const route = useRoute()
	const router = useRouter()
	const toast = useToast()
	const form = reactive({ lot_fabric_details: [] })
	const derived = reactive({})
	const record = ref(null)
	const fields = ref([])
	const locks = ref({})
	const colourAttribute = ref("")
	const itemDetails = ref(null)
	const orderItemDetails = ref([])
	const readOnlyWorkspace = ref({})
	const invalidGridCells = reactive(new Map())
	const invalidRegistry = {
		report: (key, count) =>
			count ? invalidGridCells.set(key, count) : invalidGridCells.delete(key),
		remove: (key) => invalidGridCells.delete(key),
	}
	const fabricMeta = ref(null)
	const loading = ref(true)
	const acting = ref("")
	const loadError = ref("")
	const actionError = ref("")
	const cleanSignature = ref("")
	const attemptedSave = ref(false)
	const composerOpen = ref(!lotId)
	const reloadItemsVisible = ref(false)
	let pendingField = null
	let loadSequence = 0
	let eventSequence = 0
	let mutationSequence = 0
	let isUnmounted = false
	const isNew = !lotId
	const takenDefaults = takeNewDocumentDefaults("SD YRP Lot")
	let filterDefaults = isNew && !route.query.duplicate_from ? takenDefaults : {}
	const signature = computed(() =>
		JSON.stringify({
			form,
			itemDetails: itemDetails.value,
			orderItemDetails: orderItemDetails.value,
		}),
	)
	const isDirty = computed(
		() => Boolean(record.value) && signature.value !== cleanSignature.value,
	)
	const canSave = computed(
		() => (isNew || isDirty.value) && (isNew || Boolean(record.value?.modified)),
	)
	const hasStaleError = computed(() => /changed after you opened it/i.test(actionError.value))
	const shellWorkspace = computed(() =>
		record.value
			? { record: { ...record.value, status: form.status, doctype: "SD YRP Lot" } }
			: {},
	)
	const tabs = computed(() => [
		...lotEditorTabs(form, orderItemDetails.value, isNew),
		...(!isNew
			? [
					{
						key: "fabric",
						label: "Cloth Program",
						count: readOnlyWorkspace.value.fabrics?.length || 0,
					},
				]
			: []),
	])
	const activeTab = computed({
		get: () =>
			tabs.value.some((tab) => tab.key === route.query.tab) ? route.query.tab : "details",
		set: (tab) =>
			router.replace({
				query: { ...route.query, tab },
				hash: route.hash,
				state: preserveListNavigationState(),
			}),
	})
	const editorActions = computed(() => [
		{
			key: "cancel",
			label: "Cancel",
			icon: "pi pi-times",
			command: cancel,
			disabled: Boolean(acting.value),
		},
		{
			key: "save",
			label: isNew ? "Create Lot" : "Save",
			icon: "pi pi-save",
			primary: true,
			shortcut: "save",
			loading: acting.value === "save",
			disabled: !canSave.value || Boolean(acting.value),
			command: save,
		},
	])

	function isCurrentLoad(sequence) {
		return !isUnmounted && sequence === loadSequence
	}
	function isCurrentEvent(sequence) {
		return !isUnmounted && sequence === eventSequence
	}
	function isCurrentMutation(sequence, load) {
		return !isUnmounted && sequence === mutationSequence && load === loadSequence
	}
	function showMessages(messages) {
		for (const message of messages || [])
			toast.add({
				severity: "warn",
				summary: message.title,
				detail: message.message,
				life: 6000,
			})
	}
	function applyForm(payload, metadata) {
		record.value = payload.record
		Object.assign(form, clone(payload.values))
		Object.assign(derived, payload.derived)
		fields.value = payload.fields
		locks.value = { ...payload.locks, box_locked: payload.box_locked }
		colourAttribute.value = payload.colour_attribute
		itemDetails.value = clone(payload.item_details)
		orderItemDetails.value = clone(payload.order_item_details)
		readOnlyWorkspace.value = payload.workspace || {}
		fabricMeta.value = metadata.find((document) => document.name === "SD YRP Lot Fabric Detail")
		if (!fabricMeta.value) throw new Error("Fabric Details metadata is missing.")
		composerOpen.value = isNew
		cleanSignature.value = lotEditorCleanSignature(payload, signature.value)
		attemptedSave.value = false
		showMessages(payload.messages)
	}
	function applyFilterDefaults() {
		const defaults = Object.fromEntries(Object.entries(filterDefaults).filter(([fieldname]) => fieldname in form))
		filterDefaults = {}
		const filled = withNewDocumentDefaults(form, defaults)
		const changed = Object.keys(defaults).filter((fieldname) => filled[fieldname] !== form[fieldname])
		for (const fieldname of changed) form[fieldname] = filled[fieldname]
		const cascade = ["production_order", "production_detail"].find((fieldname) => changed.includes(fieldname))
		if (cascade) applyField(cascade, form[cascade])
	}
	async function load() {
		const sequence = ++loadSequence
		++eventSequence
		++mutationSequence
		loading.value = true
		record.value = null
		loadError.value = ""
		actionError.value = ""
		try {
			const [payload, metadata] = await Promise.all([
				getLotForm(lotId || null, lotId ? null : route.query.duplicate_from || null),
				getMeta("SD YRP Lot"),
			])
			if (isCurrentLoad(sequence)) {
				applyForm(payload, metadata)
				applyFilterDefaults()
			}
		} catch (reason) {
			if (isCurrentLoad(sequence)) {
				record.value = null
				loadError.value = reason.message
			}
		} finally {
			if (isCurrentLoad(sequence)) {
				loading.value = false
				acting.value = ""
			}
		}
	}
	/** Live update: refetches the saved Lot in place (no skeleton); returns false when the response is stale. */
	async function refresh({ discard = false } = {}) {
		const sequence = ++loadSequence
		const [events, mutations, draftAtStart] = [eventSequence, mutationSequence, signature.value]
		const [payload, metadata] = await Promise.all([getLotForm(lotId), getMeta("SD YRP Lot")])
		if (!isCurrentLoad(sequence)) return true
		// An edit, field cascade or save that started meanwhile keeps the draft; the live bar explains.
		if (events !== eventSequence || mutations !== mutationSequence || acting.value || signature.value !== draftAtStart || (!discard && isDirty.value)) return false
		++eventSequence
		++mutationSequence
		applyForm(payload, metadata)
	}
	async function reload() {
		if (!isDirty.value) return load()
		const target = {
			name: MERCH_ROUTES.lotEdit,
			params: { lotId },
			query: { tab: activeTab.value },
			state: preserveListNavigationState(lotId, record.value.modified),
		}
		const failure = await router.push(viewTarget(record.value.name, record.value.modified))
		if (!failure) await router.replace(target)
	}
	function clearContext(fieldname) {
		const context = clearedLotContext(fieldname, form, derived)
		Object.assign(form, context.form)
		Object.assign(derived, context.derived)
		itemDetails.value = context.itemDetails
	}
	function setField(fieldname, value) {
		if (form[fieldname] === value) return
		const isCascade = ["production_order", "production_detail", "item"].includes(fieldname)
		if (isCascade) ++eventSequence
		if (
			["production_order", "production_detail"].includes(fieldname) &&
			itemDetails.value?.items.length
		) {
			acting.value = ""
			pendingField = { fieldname, value }
			reloadItemsVisible.value = true
			return
		}
		applyField(fieldname, value)
	}
	function confirmReloadItems() {
		reloadItemsVisible.value = false
		const change = pendingField
		pendingField = null
		if (change) applyField(change.fieldname, change.value)
	}
	async function applyField(fieldname, value) {
		form[fieldname] = value
		if (!["production_order", "production_detail", "item"].includes(fieldname)) return
		const sequence = ++eventSequence
		actionError.value = ""
		if (!value) {
			clearContext(fieldname)
			acting.value = ""
			return
		}
		acting.value = "context"
		try {
			if (fieldname === "production_order") await updateProductionOrder(sequence)
			if (fieldname === "production_detail") await updateProductionDetail(sequence)
		} catch (reason) {
			if (isCurrentEvent(sequence)) actionError.value = reason.message
		} finally {
			if (isCurrentEvent(sequence)) acting.value = ""
		}
	}
	async function updateProductionOrder(sequence) {
		const result = await getLotProductionOrderItem(form.production_order)
		if (!isCurrentEvent(sequence)) return
		form.item = result.item
		if (form.production_detail) await updateProductionDetail(sequence)
	}
	async function updateProductionDetail(sequence) {
		const result = await getLotProductionDetailContext(
			form.production_detail,
			form.item,
			form.production_order || null,
		)
		if (!isCurrentEvent(sequence)) return
		Object.assign(derived, result.derived)
		itemDetails.value = result.item_details
		composerOpen.value = true
		showMessages(result.messages)
	}
	function viewTarget(name, modified) {
		return {
			name: MERCH_ROUTES.lot,
			params: { lotId: name },
			query: { tab: activeTab.value },
			state: preserveListNavigationState(name, modified),
		}
	}
	function cancel() {
		return lotId
			? router.push(viewTarget(lotId, record.value?.modified))
			: router.push({ name: MERCH_ROUTES.lots })
	}
	function hasMissingRequiredFields() {
		return (
			fields.value.some((field) => field.reqd && !form[field.fieldname]) ||
			form.lot_fabric_details.some((row) => !row.cloth_item)
		)
	}
	function isSaveValid() {
		if (!canSave.value || acting.value) return
		if (Object.keys(boxGridErrors(itemDetails.value)).length) {
			activeTab.value = "order-items"
			actionError.value = "Fix Order Items: Qty, Ratio and MRP cannot be negative."
			return
		}
		if (hasMissingRequiredFields()) {
			activeTab.value = "details"
			return
		}
		if (invalidGridCells.size) {
			actionError.value = "Fix the invalid grid cells before saving."
			return
		}
		return true
	}
	async function save() {
		attemptedSave.value = true
		if (!isSaveValid()) return
		const sequence = ++mutationSequence
		const load = loadSequence
		acting.value = "save"
		actionError.value = ""
		try {
			const result = await saveLot(
				lotSavePayload(form, itemDetails.value, orderItemDetails.value),
				{ name: record.value.name || null, expectedModified: record.value.modified },
			)
			if (!isCurrentMutation(sequence, load)) return
			await finishSave(result)
		} catch (reason) {
			if (isCurrentMutation(sequence, load)) actionError.value = reason.message
		} finally {
			if (isCurrentMutation(sequence, load)) acting.value = ""
		}
	}
	async function finishSave(result) {
		cleanSignature.value = signature.value
		toast.add({
			severity: "success",
			summary: isNew ? "Lot created" : "Lot saved",
			detail: result.name,
			life: 3500,
		})
		await router.replace(withSavedHandoff(viewTarget(result.name, result.modified)))
	}
	onBeforeUnmount(() => {
		isUnmounted = true
		++eventSequence
		++mutationSequence
		++loadSequence
	})
	load()
	return {
		form,
		derived,
		record,
		fields,
		locks,
		colourAttribute,
		itemDetails,
		orderItemDetails,
		readOnlyWorkspace,
		invalidRegistry,
		fabricMeta,
		loading,
		acting,
		loadError,
		actionError,
		attemptedSave,
		composerOpen,
		reloadItemsVisible,
		isDirty,
		hasStaleError,
		shellWorkspace,
		tabs,
		activeTab,
		editorActions,
		setField,
		confirmReloadItems,
		reload,
		refresh,
		load,
	}
}
