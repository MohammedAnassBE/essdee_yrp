<template>
	<DepartmentPage
		title="Lotwise Item Profit"
		back-to="/pd/lotwise-item-profits"
		back-label="Lotwise Item Profit"
		:show-title="false"
		flat
		full-width
	>
		<section class="lotwise-workspace" aria-label="Lotwise Item Profit workspace">
			<div v-if="loading" class="lotwise-workspace__loading" aria-label="Loading costing sheet">
				<Skeleton height="5.5rem" />
				<Skeleton height="3.5rem" />
				<Skeleton height="28rem" />
			</div>
			<WorkspaceLoadError
				v-else-if="loadError"
				title="Lotwise Item Profit could not be loaded"
				:message="loadError"
				:loading="loading"
				@retry="load"
			/>
			<template v-else-if="hasWorkspace">
				<LotwiseWorkspaceHeader
					:name="form.name"
					:title="pageTitle"
					:product="form.product"
					:item="form.item"
					:actions="documentActions"
					:can-edit="canEdit"
					:saving="saving"
					:busy="pageBusy"
					@save="save"
				/>

				<LotwiseCommandBar
					:readonly="!canEdit"
					:lot="form.lot || ''"
					:costing-type="form.lot_costing_type || ''"
					:busy="pageBusy"
					:active-command="activeCommand"
					@command="runUserCommand"
				/>

				<LotwiseCostSections
					:form="form"
					:fields="parentFields"
					:metadata-by-name="metadataByName"
					:fields-disabled="fieldsDisabled"
					:can-edit="canEdit"
					:page-busy="pageBusy"
					:active-command="activeCommand"
					@update-field="updateField"
					@update-table="updateTable"
					@command="runUserCommand"
				/>
			</template>
		</section>

		<DocumentConfirmationDialog
			v-model:visible="deleteVisible"
			title="Delete Lotwise Item Profit?"
			:message="`Delete ${form.name || 'this costing sheet'}? This action cannot be undone.`"
			confirm-label="Delete Costing Sheet"
			confirm-icon="pi pi-trash"
			:busy="deleting"
			@confirm="confirmDelete"
		/>
		<DocumentErrorDialog
			:message="actionError"
			title="Lotwise Item Profit action could not be completed"
			:retry-label="hasStaleError ? 'Reload' : ''"
			@dismiss="actionError = ''"
			@retry="load"
		/>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import {
	deleteLotwiseItemProfit,
	getLotwiseWorkspace,
	runLotwiseCommand,
	saveLotwiseItemProfit,
} from "../../api/pd.js"
import { getMeta } from "../../api/frappe.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import LotwiseCommandBar from "./components/LotwiseCommandBar.vue"
import LotwiseCostSections from "./components/LotwiseCostSections.vue"
import LotwiseWorkspaceHeader from "./components/LotwiseWorkspaceHeader.vue"
import {
	LOTWISE_SECTIONS,
	LOTWISE_TABLE_COLUMNS,
	PD_ROUTES,
	lotwiseChildMeta,
	mergeComputedValues,
	pdRecordPath,
} from "./pdViews.js"

const LOTWISE_DOCTYPE = "SD YRP Lotwise Item Profit"
const INPUT_FIELDS = [...new Set(Object.values(LOTWISE_SECTIONS).flat())]
const TABLE_FIELDS = Object.keys(LOTWISE_TABLE_COLUMNS)

const props = defineProps({ profitId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const workspace = ref({})
const form = ref({})
const metadataByName = ref({})
const loading = ref(true)
const saving = ref(false)
const deleting = ref(false)
const activeCommand = ref("")
const loadError = ref("")
const actionError = ref("")
const deleteVisible = ref(false)
let previewTimer = null
let loadSequence = 0
let previewSequence = 0
let commandSequence = 0
let mutationSequence = 0
let isUnmounted = false

const isNew = computed(() => route.name === PD_ROUTES.lotwiseNew)
const permissions = computed(() => workspace.value.permissions || {})
const hasWorkspace = computed(() => Boolean(
	Object.keys(workspace.value).length && metadataByName.value[LOTWISE_DOCTYPE],
))
const canEdit = computed(() => isNew.value ? permissions.value.can_create : permissions.value.can_write)
const pageBusy = computed(() =>
	loading.value || saving.value || deleting.value || Boolean(activeCommand.value),
)
const fieldsDisabled = computed(() => !canEdit.value || pageBusy.value)
const pageTitle = computed(() =>
	form.value.product || form.value.item || form.value.name || "New Costing Sheet",
)
const hasStaleError = computed(() => /changed after you opened it/i.test(actionError.value))
const parentFields = computed(() => {
	const filters = workspace.value.link_filters || {}
	return Object.fromEntries((metadataByName.value[LOTWISE_DOCTYPE]?.fields || []).map((field) => [
		field.fieldname,
		filters[field.fieldname] ? { ...field, link_filters: filters[field.fieldname] } : field,
	]))
})
const documentActions = computed(() => !isNew.value && permissions.value.can_delete ? [{
	key: "delete",
	label: "Delete",
	icon: "pi pi-trash",
	disabled: pageBusy.value,
	command: () => { deleteVisible.value = true },
}] : [])

function clone(value) {
	if (value === undefined) return undefined
	return JSON.parse(JSON.stringify(value))
}

function indexMetadata(metadata) {
	const indexed = Object.fromEntries(metadata.filter((item) => item?.name).map((item) => [item.name, item]))
	const parent = indexed[LOTWISE_DOCTYPE]
	if (!parent) throw new Error(`Metadata for ${LOTWISE_DOCTYPE} was not returned.`)
	for (const fieldname of INPUT_FIELDS) {
		if (!parent.fields?.some((item) => item.fieldname === fieldname)) {
			throw new Error(`Metadata for ${fieldname} was not returned.`)
		}
	}
	for (const fieldname of TABLE_FIELDS) {
		const field = parent.fields?.find((item) => item.fieldname === fieldname)
		if (!field || !indexed[field.options]) throw new Error(`Metadata for ${fieldname} was not returned.`)
		lotwiseChildMeta(fieldname, indexed[field.options])
	}
	return indexed
}

function applyWorkspace(payload) {
	workspace.value = {
		...payload,
		modified: payload?.modified || "",
		permissions: payload?.permissions || {},
		link_filters: payload?.link_filters || {},
	}
	form.value = clone(payload?.record || {})
}

function commandValues() {
	return Object.fromEntries(INPUT_FIELDS
		.filter((fieldname) => Object.hasOwn(form.value, fieldname))
		.map((fieldname) => [fieldname, clone(form.value[fieldname])]))
}

function invalidatePreview() {
	if (previewTimer) window.clearTimeout(previewTimer)
	previewTimer = null
	previewSequence += 1
}

function invalidateCommands() {
	invalidatePreview()
	commandSequence += 1
	activeCommand.value = ""
}

async function load() {
	const sequence = ++loadSequence
	invalidateCommands()
	mutationSequence += 1
	loading.value = true
	saving.value = false
	deleting.value = false
	loadError.value = ""
	actionError.value = ""
	deleteVisible.value = false
	try {
		const request = getLotwiseWorkspace({
			name: isNew.value ? null : props.profitId,
			product: isNew.value ? String(route.query.product || "") || null : null,
		})
		const [payload, metadata] = await Promise.all([request, getMeta(LOTWISE_DOCTYPE)])
		if (isUnmounted || sequence !== loadSequence) return
		metadataByName.value = indexMetadata(metadata)
		applyWorkspace(payload || {})
	} catch (reason) {
		if (isUnmounted || sequence !== loadSequence) return
		workspace.value = {}
		form.value = {}
		metadataByName.value = {}
		loadError.value = reason?.message || "Unable to load the costing sheet."
	} finally {
		if (!isUnmounted && sequence === loadSequence) loading.value = false
	}
}

function updateField(fieldname, value) {
	if (!canEdit.value) return
	form.value = { ...form.value, [fieldname]: value }
	if (["product", "item"].includes(fieldname) && value) {
		runCommand(fieldname === "product" ? "load_product_sizes" : "load_item_sizes")
		return
	}
	scheduleRecalculation()
}

function updateTable(fieldname, rows) {
	if (!canEdit.value) return
	form.value = { ...form.value, [fieldname]: clone(rows || []) }
	scheduleRecalculation()
}

function scheduleRecalculation() {
	if (!canEdit.value || pageBusy.value) return
	if (previewTimer) window.clearTimeout(previewTimer)
	const sequence = ++previewSequence
	const command = commandSequence
	previewTimer = window.setTimeout(() => {
		previewTimer = null
		requestPreview(sequence, command)
	}, 400)
}

async function commitFocusedInput() {
	document.activeElement?.blur?.()
	await nextTick()
}

async function runUserCommand(command, payload = null) {
	if (!canEdit.value || pageBusy.value) return
	await commitFocusedInput()
	return runCommand(command, payload)
}

async function runCommand(command, payload = null) {
	if (!canEdit.value || pageBusy.value) return
	if (isUnmounted) return
	invalidatePreview()
	const sequence = ++commandSequence
	activeCommand.value = command
	actionError.value = ""
	try {
		const result = await runLotwiseCommand(
			commandValues(),
			command,
			payload,
			isNew.value ? null : form.value.name,
		)
		if (isUnmounted || sequence !== commandSequence) return
		form.value = clone(result?.record || {})
	} catch (reason) {
		if (!isUnmounted && sequence === commandSequence) {
			actionError.value = reason?.message || `Unable to ${command.replaceAll("_", " ")}.`
		}
	} finally {
		if (!isUnmounted && sequence === commandSequence) activeCommand.value = ""
	}
}

async function requestPreview(sequence, command) {
	actionError.value = ""
	try {
		const result = await runLotwiseCommand(
			commandValues(),
			"recalculate",
			null,
			isNew.value ? null : form.value.name,
		)
		if (isUnmounted || sequence !== previewSequence || command !== commandSequence) return
		form.value = mergeComputedValues(form.value, result?.record || {})
	} catch (reason) {
		if (!isUnmounted && sequence === previewSequence && command === commandSequence) {
			actionError.value = reason?.message || "Unable to recalculate."
		}
	}
}

function mutationContext() {
	return { load: loadSequence, mutation: ++mutationSequence }
}

function isCurrentMutation(context) {
	return !isUnmounted && context.load === loadSequence && context.mutation === mutationSequence
}

async function save() {
	if (!canEdit.value || pageBusy.value) return
	invalidateCommands()
	const context = mutationContext()
	saving.value = true
	actionError.value = ""
	try {
		const payload = await saveLotwiseItemProfit(commandValues(), {
			name: isNew.value ? null : form.value.name,
			expectedModified: isNew.value ? null : workspace.value.modified,
		})
		if (!isCurrentMutation(context)) return
		applyWorkspace(payload || {})
		if (isNew.value) await router.replace(pdRecordPath("lotwise", form.value.name).replace(/^\/web/, ""))
	} catch (reason) {
		if (isCurrentMutation(context)) actionError.value = reason?.message || "Unable to save the costing sheet."
	} finally {
		if (isCurrentMutation(context)) saving.value = false
	}
}

async function confirmDelete() {
	if (isNew.value || !permissions.value.can_delete || pageBusy.value) return
	invalidateCommands()
	const context = mutationContext()
	deleting.value = true
	actionError.value = ""
	try {
		await deleteLotwiseItemProfit(form.value.name, workspace.value.modified)
		if (!isCurrentMutation(context)) return
		deleteVisible.value = false
		await router.replace({ name: PD_ROUTES.lotwiseList })
	} catch (reason) {
		if (isCurrentMutation(context)) actionError.value = reason?.message || "Unable to delete the costing sheet."
	} finally {
		if (isCurrentMutation(context)) deleting.value = false
	}
}

function handleShortcut(event) {
	if (!event.ctrlKey || String(event.key).toLowerCase() !== "e" || !canEdit.value || pageBusy.value) return
	event.preventDefault()
	runUserCommand("recalculate")
}

watch(() => [route.name, props.profitId, String(route.query.product || "")], load, { immediate: true })
onMounted(() => window.addEventListener("keydown", handleShortcut))
onBeforeUnmount(() => {
	isUnmounted = true
	loadSequence += 1
	mutationSequence += 1
	invalidateCommands()
	window.removeEventListener("keydown", handleShortcut)
})
</script>

<style scoped>
.lotwise-workspace {
	display: grid;
	width: 100%;
	min-width: 0;
	gap: var(--erp-space-3);
}

.lotwise-workspace__loading {
	display: grid;
	min-width: 0;
	gap: var(--erp-space-3);
}

</style>
