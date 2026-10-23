<template>
	<DepartmentPage
		title="Product"
		back-to="/pd/products"
		back-label="Products"
		:show-title="false"
		flat
		full-width
		activity-doctype="SD YRP Product"
		:activity-name="isNew ? '' : record.name || ''"
		:activity-record="workspace"
	>
		<ProductWorkspaceContent
			:workspace="workspace" :record="record" :form="form" :images="images"
			:meta-by-name="metaByName" :actions="documentActions" :visible-tabs="visibleTabs"
			:colour-tables="colourTables" :trim-colours="trimColours" :active-tab="activeTab"
			:mode="mode" :load-error="loadError" :loading="loading" :has-workspace="hasWorkspace"
			:is-new="isNew" :is-set-item="isSetItem" :busy="busy" :saving="saving"
			:copy-source="copySource"
			:can-save="canSave" :can-print="Boolean(permissions.can_print)" :fields-disabled="fieldsDisabled"
			:can-edit-images="canEditImages" :can-upload-images="canUploadImages"
			:can-create-costing="Boolean(permissions.can_write)" :media-busy="mediaBusy"
			@retry="load" @cancel="cancelEditing" @save="save" @update:active-tab="activeTab = $event"
			@update-field="updateField" @update-image-group="updateImageGroup"
			@edit-requested="startMediaEditing"
			@operation-started="startMediaOperation" @operation-finished="finishMediaOperation"
			@dismiss-copy="copySource = ''"
		/>

		<ProductActionDialogs
			v-model:release-visible="releaseVisible"
			v-model:delete-visible="deleteVisible"
			:discard-visible="discardVisible"
			:delete-target="deleteTarget"
			:acting="acting"
			:action-error="actionError"
			:has-stale-error="hasStaleError"
			@update:discard-visible="setDiscardVisible"
			@confirm-release="confirmRelease"
			@confirm-delete="confirmDelete"
			@discard-changes="discardChanges"
			@dismiss-error="actionError = ''"
			@reload="reloadAfterConflict"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"

import {
	deleteProduct,
	getNewProductDefaults,
	getProductWorkspace,
	getSizeRangeSizes,
	releaseTechPack,
	saveProduct,
} from "../../api/pd.js"
import { getMeta } from "../../api/frappe.js"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../utils/newDocumentDefaults.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ProductActionDialogs from "./components/ProductActionDialogs.vue"
import ProductWorkspaceContent from "./components/ProductWorkspaceContent.vue"
import {
	PD_ROUTES,
	PRODUCT_TABS,
	colourOptionsFromForm,
	copiedImageGroups,
	copiedProductDraft,
	editableValues,
	imagePayload,
	pdRecordPath,
	productActionItems,
} from "./pdViews.js"
import "./components/pd.css"

const props = defineProps({ productId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const workspace = ref({})
const form = ref({})
const images = ref(emptyImages())
const mode = ref("view")
const metaByName = ref({})
const activeTab = ref("basic")
const loading = ref(true)
const saving = ref(false)
const sizeRangeLoading = ref(false)
const mediaBusy = ref(false)
const acting = ref("")
const loadError = ref("")
const actionError = ref("")
const releaseVisible = ref(false)
const deleteVisible = ref(false)
const discardVisible = ref(false)
const copySource = ref("")
const releaseTarget = ref("")
const deleteTarget = ref(null)
const cleanSignature = ref("")
let pendingNavigation = null
let allowNavigation = false
let loadSequence = 0
let mutationSequence = 0
let sizeRangeSequence = 0
let isUnmounted = false

const isNew = computed(() => route.name === "pd-product-new")
const takenDefaults = takeNewDocumentDefaults("SD YRP Product")
let filterDefaults = isNew.value && !route.query.copy ? takenDefaults : {}
const record = computed(() => form.value || {})
const permissions = computed(() => workspace.value.permissions || {})
const hasWorkspace = computed(() => Boolean(Object.keys(workspace.value).length))
const isSetItem = computed(() => Boolean(Number(form.value.is_set_item)))
const visibleTabs = computed(() => PRODUCT_TABS.filter((tab) => !isNew.value || tab.key !== "costing"))
const colourTables = computed(() => isSetItem.value ? ["product_set_colours"] : ["product_colours"])
const documentBusy = computed(() => loading.value || saving.value || sizeRangeLoading.value || Boolean(acting.value))
const busy = computed(() => documentBusy.value || mediaBusy.value)
const canEditForm = computed(() => mode.value === "edit" && (isNew.value ? permissions.value.can_create : permissions.value.can_write))
const canSave = computed(() => canEditForm.value && !busy.value)
const fieldsDisabled = computed(() => !canEditForm.value || busy.value)
const canEditImages = computed(() => mode.value === "edit"
	&& (isNew.value ? permissions.value.can_create : permissions.value.can_write)
	&& !busy.value)
const canUploadImages = computed(() => !isNew.value
	&& permissions.value.can_write
	&& !documentBusy.value)
const trimColours = computed(() => colourOptionsFromForm(form.value, workspace.value.colours))
const currentSignature = computed(() => JSON.stringify({
	values: editableValues(form.value),
	images: imagePayload(images.value),
}))
const isDirty = computed(() => mode.value === "edit" && hasWorkspace.value && currentSignature.value !== cleanSignature.value)
const hasStaleError = computed(() => /changed after you opened it/i.test(actionError.value))
const documentActions = computed(() => productActionItems(permissions.value, {
	edit: openEditor,
	release: openReleaseConfirmation,
	duplicate: duplicateProduct,
	delete: openDeleteConfirmation,
}, { busy: busy.value, acting: acting.value }))

function emptyImages() {
	return { placement: [], trims: [], combination: [], accessories: [] }
}

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? {}))
}

function routePath(kind, name) {
	return pdRecordPath(kind, name).replace(/^\/web/, "")
}

function normaliseWorkspace(payload) {
	return {
		...payload,
		modified: payload?.modified || "",
		images: payload?.images || emptyImages(),
		size_labels: payload?.size_labels || {},
		measurement: payload?.measurement || { groups: {}, images: [] },
		colours: payload?.colours || { is_set_item: false, top: [], bottom: [], all: [] },
		costing: payload?.costing || [],
		releases: payload?.releases || [],
		print_formats: payload?.print_formats || [],
		link_filters: payload?.link_filters || {},
	}
}

function applyWorkspace(payload, source = null) {
	const nextWorkspace = normaliseWorkspace(payload || {})
	if (source) {
		nextWorkspace.colours = source.colours || nextWorkspace.colours
		nextWorkspace.size_labels = source.size_labels || nextWorkspace.size_labels
	}
	workspace.value = nextWorkspace
	form.value = source
		? copiedProductDraft(nextWorkspace.record, source.record)
		: clone(nextWorkspace.record || {})
	images.value = source ? copiedImageGroups(source.images) : clone(nextWorkspace.images)
	copySource.value = source?.record?.name || ""
	mode.value = requestedMode()
	cleanSignature.value = currentSignature.value
	resetHiddenActiveTab()
}

function resetHiddenActiveTab() {
	if (!visibleTabs.value.some((tab) => tab.key === activeTab.value)) activeTab.value = "basic"
}

function requestedMode() {
	if (isNew.value) return permissions.value.can_create ? "edit" : "view"
	if (route.name === "pd-product-edit" && permissions.value.can_write) return "edit"
	return "view"
}

function resetConfirmations() {
	releaseVisible.value = false
	deleteVisible.value = false
	releaseTarget.value = ""
	deleteTarget.value = null
}

function invalidateRecordContext() {
	++loadSequence
	++mutationSequence
	++sizeRangeSequence
	saving.value = false
	sizeRangeLoading.value = false
	mediaBusy.value = false
	acting.value = ""
	resetConfirmations()
}

function isCurrentLoad(sequence) {
	return !isUnmounted && sequence === loadSequence
}

async function load() {
	invalidateRecordContext()
	const sequence = loadSequence
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	copySource.value = ""
	try {
		const copyName = isNew.value ? String(route.query.copy || "").trim() : ""
		const payloadRequest = isNew.value ? getNewProductDefaults() : getProductWorkspace(props.productId)
		const [payload, metas, source] = await Promise.all([
			payloadRequest,
			getMeta("SD YRP Product"),
			copyName ? getProductWorkspace(copyName) : Promise.resolve(null),
		])
		if (!isCurrentLoad(sequence)) return
		metaByName.value = Object.fromEntries(metas.filter((meta) => meta?.name).map((meta) => [meta.name, meta]))
		applyWorkspace(payload, source)
		if (isNew.value && !source) applyFilterDefaults()
	} catch (reason) {
		if (!isCurrentLoad(sequence)) return
		workspace.value = {}
		form.value = {}
		images.value = emptyImages()
		copySource.value = ""
		loadError.value = reason?.message || "Unable to load the Product."
	} finally {
		if (isCurrentLoad(sequence)) {
			loading.value = false
			allowNavigation = false
		}
	}
}

function applyFilterDefaults() {
	const defaults = Object.fromEntries(Object.entries(filterDefaults).filter(([fieldname]) => fieldname in form.value))
	filterDefaults = {}
	const filled = withNewDocumentDefaults(form.value, defaults)
	for (const fieldname of Object.keys(defaults)) if (filled[fieldname] !== form.value[fieldname]) updateField(fieldname, filled[fieldname])
}

function updateField(fieldname, value) {
	form.value = { ...form.value, [fieldname]: value }
	if (fieldname === "size_range") updateSizes(value)
}

async function updateSizes(sizeRange) {
	const sequence = ++sizeRangeSequence
	if (!sizeRange) {
		form.value = { ...form.value, sizes: [] }
		sizeRangeLoading.value = false
		return
	}
	sizeRangeLoading.value = true
	try {
		const sizes = await getSizeRangeSizes(sizeRange)
		if (!isUnmounted && sequence === sizeRangeSequence && form.value.size_range === sizeRange) {
			form.value = { ...form.value, sizes: clone(sizes || []) }
		}
	} catch (reason) {
		if (!isUnmounted && sequence === sizeRangeSequence) {
			actionError.value = reason?.message || "Unable to load sizes for this range."
		}
	} finally {
		if (!isUnmounted && sequence === sizeRangeSequence) sizeRangeLoading.value = false
	}
}

function updateImageGroup(group, rows) {
	images.value = { ...images.value, [group]: clone(rows || []) }
}

function beginMutation() {
	return { loadSequence, mutationSequence: ++mutationSequence }
}

function isCurrentMutation(context) {
	return !isUnmounted
		&& context.loadSequence === loadSequence
		&& context.mutationSequence === mutationSequence
}

async function save() {
	if (!canSave.value) return
	const context = beginMutation()
	saving.value = true
	actionError.value = ""
	try {
		const payload = await saveProduct(editableValues(form.value), imagePayload(images.value), {
			name: isNew.value ? null : workspace.value.record?.name,
			expectedModified: isNew.value ? null : workspace.value.modified,
		})
		if (!isCurrentMutation(context)) return
		applyWorkspace(payload)
		const target = routePath("product", payload.record.name)
		allowNavigation = target !== route.path
		await router.push(target)
	} catch (reason) {
		if (isCurrentMutation(context)) actionError.value = reason?.message || "Unable to save the Product."
	} finally {
		if (isCurrentMutation(context)) saving.value = false
	}
}

function openEditor() {
	router.push(`${routePath("product", record.value.name)}/edit`)
}

function duplicateProduct() {
	router.push({ name: PD_ROUTES.productNew, query: { copy: record.value.name } })
}

function cancelEditing() {
	const target = isNew.value ? "/pd/products" : routePath("product", record.value.name)
	if (!isNew.value && route.name !== "pd-product-edit") {
		applyWorkspace(workspace.value)
		return
	}
	router.push(target)
}

function startMediaEditing() {
	if (!isNew.value && permissions.value.can_write) mode.value = "edit"
}

function openReleaseConfirmation() {
	releaseTarget.value = record.value.name
	releaseVisible.value = true
}

function openDeleteConfirmation() {
	deleteTarget.value = { name: record.value.name, modified: workspace.value.modified }
	deleteVisible.value = true
}

async function confirmRelease() {
	const targetName = releaseTarget.value
	if (!targetName) return
	const context = beginMutation()
	acting.value = "release"
	actionError.value = ""
	try {
		const releaseName = await releaseTechPack(targetName)
		if (!isCurrentMutation(context)) return
		releaseVisible.value = false
		releaseTarget.value = ""
		allowNavigation = true
		await router.push(routePath("release", releaseName))
	} catch (reason) {
		if (isCurrentMutation(context)) actionError.value = reason?.message || "Unable to release the Tech Pack."
	} finally {
		if (isCurrentMutation(context)) acting.value = ""
	}
}

async function confirmDelete() {
	const target = deleteTarget.value
	if (!target) return
	const context = beginMutation()
	acting.value = "delete"
	actionError.value = ""
	try {
		await deleteProduct(target.name, target.modified)
		if (!isCurrentMutation(context)) return
		deleteVisible.value = false
		deleteTarget.value = null
		allowNavigation = true
		await router.push("/pd/products")
	} catch (reason) {
		if (isCurrentMutation(context)) actionError.value = reason?.message || "Unable to delete the Product."
	} finally {
		if (isCurrentMutation(context)) acting.value = ""
	}
}

function startMediaOperation() {
	mediaBusy.value = true
}

function finishMediaOperation() {
	mediaBusy.value = false
}

async function reloadAfterConflict() {
	actionError.value = ""
	await load()
}

function setDiscardVisible(value) {
	if (value) {
		discardVisible.value = true
		return
	}
	keepEditing()
}

function keepEditing() {
	discardVisible.value = false
	pendingNavigation?.(false)
	pendingNavigation = null
}

function discardChanges() {
	discardVisible.value = false
	const next = pendingNavigation
	pendingNavigation = null
	continueNavigation(next)
}

function beforeUnload(event) {
	if (!isDirty.value && !mediaBusy.value) return
	event.preventDefault()
	event.returnValue = ""
}

function continueNavigation(next) {
	allowNavigation = false
	invalidateRecordContext()
	next?.()
}

function guardUnsavedChanges(_to, _from, next) {
	if (mediaBusy.value) return next(false)
	if (allowNavigation || !isDirty.value) return continueNavigation(next)
	pendingNavigation = next
	discardVisible.value = true
}

watch(visibleTabs, resetHiddenActiveTab)
watch(() => [route.name, props.productId, route.query.copy], load, { immediate: true })
onBeforeRouteLeave(guardUnsavedChanges)
onBeforeRouteUpdate(guardUnsavedChanges)
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => {
	isUnmounted = true
	++loadSequence
	++mutationSequence
	++sizeRangeSequence
	window.removeEventListener("beforeunload", beforeUnload)
})
</script>
