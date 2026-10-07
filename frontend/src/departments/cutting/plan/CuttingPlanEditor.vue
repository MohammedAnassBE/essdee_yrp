<template>
	<section class="cutting-plan-editor erp-card erp-editor-shell" aria-label="Cutting Plan editor">
		<header class="cutting-plan-editor__header erp-editor-header">
			<div>
				<span class="cutting-plan-editor__eyebrow">{{ name ? name : "New document" }}</span>
				<h1>{{ name ? "Edit Cutting Plan" : "New Cutting Plan" }}</h1>
			</div>
			<div class="cutting-plan-editor__actions erp-editor-actions">
				<Button label="Cancel" severity="secondary" text :disabled="saving" @click="emit('cancel')" />
				<Button label="Save Draft" icon="pi pi-save" severity="secondary" outlined :loading="saving === 'draft'" :disabled="busy || !canSave" @click="save(false)" />
				<Button v-if="permissions.can_submit" label="Save & Submit" icon="pi pi-check" :loading="saving === 'submit'" :disabled="busy || !canSave" @click="save(true)" />
			</div>
		</header>

		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-if="loading" class="cutting-plan-editor__loading">
			<Skeleton height="160px" />
			<Skeleton height="280px" />
		</div>

		<div v-else class="cutting-plan-editor__body">
			<section class="cutting-plan-editor__section">
				<header><h2>Plan Details</h2></header>
				<div class="cutting-plan-editor__fields">
					<label class="cutting-plan-editor__check">
						<Checkbox v-model="form.is_manual_entry" binary :true-value="1" :false-value="0" input-id="cp-manual-entry" :disabled="busy" />
						<span>Is Manual Entry</span>
					</label>
					<div class="cutting-plan-editor__field cutting-plan-editor__field--wide">
						<label>Lot <span>*</span></label>
						<LinkField v-model="form.lot" doctype="SD YRP Lot" :show-open-button="false" :disabled="busy" show-clear @select="loadLot" @clear="clearLot" />
					</div>
					<div class="cutting-plan-editor__field">
						<label for="cp-item">Item</label>
						<InputText id="cp-item" v-model="form.item" disabled fluid />
					</div>
					<div class="cutting-plan-editor__field">
						<label for="cp-max-plies">Maximum No of Plys <span>*</span></label>
						<InputNumber v-model="form.maximum_no_of_plys" input-id="cp-max-plies" :min="1" :use-grouping="false" :disabled="busy" fluid />
					</div>
					<div class="cutting-plan-editor__field">
						<label for="cp-allowance">Maximum Allow Percent</label>
						<InputNumber v-model="form.maximum_allow_percent" input-id="cp-allowance" suffix="%" :min="0" :max="100" :max-fraction-digits="2" :use-grouping="false" :disabled="busy" fluid />
					</div>
					<div class="cutting-plan-editor__field">
						<label for="cp-location">Cutting Location</label>
						<Select v-model="form.cutting_location" input-id="cp-location" :options="options.cutting_locations || []" :disabled="busy" show-clear fluid />
					</div>
					<div v-if="fields.show_work_order" class="cutting-plan-editor__field">
						<label>Work Order</label>
						<LinkField v-model="form.work_order" doctype="YRP Work Order" :filters="workOrderFilters" :show-open-button="false" :disabled="busy || !form.lot || !fields.can_edit_work_order" show-clear />
					</div>
				</div>
			</section>

			<section class="cutting-plan-editor__section cutting-plan-editor__section--matrix">
				<CuttingQuantityMatrix :groups="groups" :disabled="busy" @update="updateQuantity" />
			</section>
		</div>

		<Dialog v-model:visible="discardVisible" header="Discard unsaved changes?" modal :closable="false" :style="{ width: 'min(440px, calc(100vw - 32px))' }">
			<p class="cutting-plan-editor__discard-copy">Your unsaved Cutting Plan changes will be lost.</p>
			<template #footer>
				<Button label="Keep Editing" severity="secondary" text @click="keepEditing" />
				<Button label="Discard Changes" severity="danger" @click="discardChanges" />
			</template>
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave } from "vue-router"

import { getCuttingPlanEditor, loadCuttingPlanLot, saveCuttingPlan } from "../../../api/cuttingPlanEditor.js"
import LinkField from "../../../components/common/LinkField.vue"
import CuttingQuantityMatrix from "../shared/CuttingQuantityMatrix.vue"

const props = defineProps({
	name: { type: String, default: "" },
	initialPayload: { type: Object, default: null },
	initialSource: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["saved", "cancel", "loaded"])
const form = reactive({ is_manual_entry: 0, lot: "", item: "", production_detail: "", maximum_no_of_plys: null, maximum_allow_percent: null, cutting_location: "", work_order: "" })
const groups = ref([])
const permissions = reactive({ can_create: false, can_write: false, can_submit: false })
const fields = reactive({ show_work_order: false, can_edit_work_order: false })
const options = reactive({ cutting_locations: [] })
const modified = ref("")
const loading = ref(true)
const loadingLot = ref(false)
const saving = ref("")
const error = ref("")
const cleanSignature = ref("")
const discardVisible = ref(false)
let pendingNavigation = null
let allowNavigation = false

const busy = computed(() => loading.value || loadingLot.value || Boolean(saving.value))
const canSave = computed(() => Boolean(form.lot && groups.value.length && form.maximum_no_of_plys) && (props.name ? permissions.can_write : permissions.can_create))
const workOrderFilters = computed(() => ({ lot: form.lot || "", docstatus: 1 }))
const signature = computed(() => JSON.stringify({
	form: {
		is_manual_entry: form.is_manual_entry,
		lot: form.lot,
		maximum_no_of_plys: form.maximum_no_of_plys,
		maximum_allow_percent: form.maximum_allow_percent,
		cutting_location: form.cutting_location,
		work_order: form.work_order,
	},
	groups: groups.value,
}))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? null))
}

function applyPayload(payload) {
	const record = payload?.record || {}
	for (const key of Object.keys(form)) form[key] = record[key] ?? (key === "is_manual_entry" ? 0 : "")
	groups.value = clone(payload?.matrix?.groups || [])
	Object.assign(permissions, payload?.permissions || {})
	Object.assign(fields, payload?.fields || {})
	Object.assign(options, payload?.options || {})
	modified.value = record.modified || ""
	cleanSignature.value = signature.value
	emit("loaded", payload)
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = clone(props.initialPayload || await getCuttingPlanEditor(props.name, props.name ? "" : props.initialSource.lot || ""))
		if (!props.name && props.initialSource.work_order && payload?.fields?.can_edit_work_order) {
			payload.record = { ...(payload.record || {}), work_order: props.initialSource.work_order }
		}
		applyPayload(payload)
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Cutting Plan editor."
	} finally {
		loading.value = false
		cleanSignature.value = signature.value
	}
}

async function loadLot() {
	if (!form.lot) return clearLot()
	loadingLot.value = true
	error.value = ""
	try {
		const payload = await loadCuttingPlanLot(form.lot)
		form.item = payload?.item || ""
		form.production_detail = payload?.production_detail || ""
		groups.value = clone(payload?.groups || [])
		if (form.work_order) form.work_order = ""
	} catch (reason) {
		error.value = reason?.message || "Unable to load Lot quantities."
		clearLot(false)
	} finally {
		loadingLot.value = false
	}
}

function clearLot(clearName = true) {
	if (clearName) form.lot = ""
	form.item = ""
	form.production_detail = ""
	form.work_order = ""
	groups.value = []
}

function updateQuantity({ rowKey, size, quantity }) {
	for (const group of groups.value) {
		const row = (group.items || []).find((entry) => entry._row_key === rowKey)
		if (!row) continue
		row.values[size] = { qty: quantity }
		return
	}
}

async function save(submit) {
	saving.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const values = {
			is_manual_entry: form.is_manual_entry,
			lot: form.lot,
			maximum_no_of_plys: form.maximum_no_of_plys,
			maximum_allow_percent: form.maximum_allow_percent,
			cutting_location: form.cutting_location,
			item_details: clone(groups.value),
		}
		if (fields.can_edit_work_order) values.work_order = form.work_order || null
		const payload = await saveCuttingPlan(
			values,
			{ name: props.name, submit, expectedModified: modified.value },
		)
		applyPayload(payload)
		cleanSignature.value = signature.value
		emit("saved", payload?.record || {})
	} catch (reason) {
		error.value = reason?.message || "Unable to save the Cutting Plan."
	} finally {
		saving.value = ""
	}
}

function beforeUnload(event) {
	if (!dirty.value) return
	event.preventDefault()
	event.returnValue = ""
}

function keepEditing() {
	discardVisible.value = false
	pendingNavigation?.(false)
	pendingNavigation = null
}

function discardChanges() {
	discardVisible.value = false
	allowNavigation = true
	const next = pendingNavigation
	pendingNavigation = null
	next?.()
}

onBeforeRouteLeave((_to, _from, next) => {
	if (allowNavigation || !dirty.value) return next()
	pendingNavigation = next
	discardVisible.value = true
})

onMounted(() => {
	window.addEventListener("beforeunload", beforeUnload)
	load()
})
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
watch(() => props.name, () => load())
</script>

<style scoped>
.cutting-plan-editor {
	display: flex;
	min-width: 0;
	min-height: calc(100dvh - var(--erp-shell-header-height) - 98px);
	flex-direction: column;
	gap: var(--erp-space-3);
}

.cutting-plan-editor__eyebrow { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.04em; text-transform: uppercase; }
.cutting-plan-editor__header h1 { margin: 3px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-title); font-weight: 780; letter-spacing: -0.025em; }
.cutting-plan-editor__body { display: grid; gap: var(--erp-space-3); min-width: 0; }
.cutting-plan-editor__loading { display: grid; gap: var(--erp-space-3); }
.cutting-plan-editor__section { padding: var(--erp-space-4); background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.cutting-plan-editor__section > header h2 { margin: 0 0 var(--erp-space-3); color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 760; }
.cutting-plan-editor__section--matrix { min-width: 0; }
.cutting-plan-editor__fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3) var(--erp-space-4); align-items: end; }
.cutting-plan-editor__field { display: grid; min-width: 0; gap: 6px; }
.cutting-plan-editor__field--wide { grid-column: span 2; }
.cutting-plan-editor__field > label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.cutting-plan-editor__field > label span { color: #c24145; }
.cutting-plan-editor__check { display: inline-flex; min-height: var(--erp-control-height); align-items: center; gap: 8px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.cutting-plan-editor__discard-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.55; }

@media (max-width: 900px) {
	.cutting-plan-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 600px) {
	.cutting-plan-editor__section { padding: var(--erp-space-3); }
	.cutting-plan-editor__fields { grid-template-columns: 1fr; }
	.cutting-plan-editor__field--wide { grid-column: auto; }
}
</style>
