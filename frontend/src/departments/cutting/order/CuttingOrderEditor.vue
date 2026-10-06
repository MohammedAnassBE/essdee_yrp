<template>
	<section class="cutting-order-editor erp-card" aria-label="Cutting Order editor">
		<header class="order-editor-header">
			<div><span>{{ name || "New document" }}</span><h1>{{ name ? "Edit Cutting Order" : "New Cutting Order" }}</h1></div>
			<div class="order-editor-actions">
				<Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('cancel')" />
				<Button label="Save Draft" icon="pi pi-save" severity="secondary" outlined :loading="saving === 'draft'" :disabled="busy || !canSave" @click="save(false)" />
				<Button v-if="permissions.can_submit" label="Save & Submit" icon="pi pi-check" :loading="saving === 'submit'" :disabled="busy || !canSave" @click="save(true)" />
			</div>
		</header>

		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-if="loading" class="order-editor-loading"><Skeleton height="150px" /><Skeleton height="280px" /></div>
		<div v-else class="order-editor-body">
			<section class="order-editor-section">
				<header><h2>Order Details</h2></header>
				<div class="order-editor-fields">
					<div class="order-editor-field order-editor-field--detail">
						<label>Cutting Order Detail <span>*</span></label>
						<div class="detail-selector">
							<LinkField v-model="form.cutting_order_detail" doctype="SD YRP Cutting Order Detail" :show-open-button="false" :disabled="busy" show-clear @select="detailSelected" @clear="clearDetail" />
							<Button v-if="detailPermissions.can_create" label="Create Detail" icon="pi pi-plus" severity="secondary" outlined @click="openDetail('')" />
							<Button v-if="form.cutting_order_detail && detailPermissions.can_write" label="Edit Detail" icon="pi pi-pencil" severity="secondary" text @click="openDetail(form.cutting_order_detail)" />
						</div>
					</div>
					<div class="order-editor-field"><label>Item</label><InputText v-model="form.item" disabled fluid /></div>
					<div class="order-editor-field"><label>Cutting Location</label><Select v-model="form.cutting_location" :options="options.cutting_locations || []" :disabled="busy" show-clear fluid /></div>
					<div class="order-editor-field"><label>Maximum No of Plys <span>*</span></label><InputNumber v-model="form.maximum_no_of_plys" :min="1" :use-grouping="false" :disabled="busy" fluid /></div>
					<div class="order-editor-field"><label>Maximum Allow Percent</label><InputNumber v-model="form.maximum_allow_percent" suffix="%" :min="0" :max="100" :max-fraction-digits="2" :use-grouping="false" :disabled="busy" fluid /></div>
				</div>
			</section>

			<section class="order-editor-section order-editor-section--matrix">
				<CuttingQuantityMatrix :groups="groups" :disabled="busy" @update="updateQuantity" />
			</section>
		</div>

		<CuttingOrderDetailDialog v-model:visible="detailOpen" :name="selectedDetail" :item="form.item" @saved="detailSaved" />
		<Dialog v-model:visible="discardVisible" header="Discard unsaved changes?" modal :closable="false" :style="{ width: 'min(440px, calc(100vw - 32px))' }">
			<p class="discard-copy">Your unsaved Cutting Order changes will be lost.</p>
			<template #footer><Button label="Keep Editing" severity="secondary" text @click="keepEditing" /><Button label="Discard Changes" severity="danger" @click="discardChanges" /></template>
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave } from "vue-router"

import { getCuttingOrderDetail, getCuttingOrderEditor, saveCuttingOrder } from "../../../api/cuttingOrder.js"
import LinkField from "../../../components/common/LinkField.vue"
import CuttingQuantityMatrix from "../shared/CuttingQuantityMatrix.vue"
import CuttingOrderDetailDialog from "./CuttingOrderDetailDialog.vue"

const props = defineProps({ name: { type: String, default: "" }, initialPayload: { type: Object, default: null } })
const emit = defineEmits(["saved", "cancel", "loaded"])
const form = reactive({ cutting_order_detail: "", item: "", cutting_location: "", maximum_no_of_plys: null, maximum_allow_percent: null })
const groups = ref([])
const permissions = reactive({ can_create: false, can_write: false, can_submit: false })
const detailPermissions = reactive({ can_create: false, can_write: false })
const options = reactive({ cutting_locations: [] })
const modified = ref("")
const loading = ref(true)
const loadingDetail = ref(false)
const saving = ref("")
const error = ref("")
const cleanSignature = ref("")
const detailOpen = ref(false)
const selectedDetail = ref("")
const loadedDetail = ref("")
const discardVisible = ref(false)
let pendingNavigation = null
let allowNavigation = false

const busy = computed(() => loading.value || loadingDetail.value || Boolean(saving.value))
const canSave = computed(() => Boolean(form.cutting_order_detail && groups.value.length && form.maximum_no_of_plys) && (props.name ? permissions.can_write : permissions.can_create))
const signature = computed(() => JSON.stringify({ form, groups: groups.value }))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)

function clone(value) { return JSON.parse(JSON.stringify(value ?? null)) }

function applyPayload(payload, { preserveQuantities = false } = {}) {
	const previous = preserveQuantities ? quantityMap(groups.value) : new Map()
	const record = payload?.record || {}
	for (const key of Object.keys(form)) form[key] = record[key] ?? ""
	groups.value = clone(payload?.matrix?.groups || [])
	if (preserveQuantities) restoreQuantities(groups.value, previous)
	Object.assign(permissions, payload?.permissions || {})
	Object.assign(options, payload?.options || {})
	modified.value = record.modified || ""
	if (payload?.detail) Object.assign(detailPermissions, { can_create: false, can_write: true })
	loadedDetail.value = payload?.detail?.name || record.cutting_order_detail || ""
	emit("loaded", payload)
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = props.initialPayload || await getCuttingOrderEditor(props.name)
		applyPayload(payload)
		await loadDetailPermissions(payload?.record?.cutting_order_detail)
	} catch (reason) { error.value = reason?.message || "Unable to load the Cutting Order editor." }
	finally { loading.value = false; cleanSignature.value = signature.value }
}

async function loadDetailPermissions(name = "") {
	try {
		const payload = await getCuttingOrderDetail(name)
		Object.assign(detailPermissions, payload?.permissions || {})
	} catch { Object.assign(detailPermissions, { can_create: false, can_write: false }) }
}

async function detailSelected() {
	await loadDetail(form.cutting_order_detail, form.cutting_order_detail === loadedDetail.value)
}
async function clearDetail() { form.cutting_order_detail = ""; form.item = ""; groups.value = [] }

async function loadDetail(name, preserveQuantities) {
	if (!name) return clearDetail()
	loadingDetail.value = true
	error.value = ""
	try {
		const payload = await getCuttingOrderEditor(props.name, name)
		applyPayload(payload, { preserveQuantities: Boolean(preserveQuantities && name === loadedDetail.value) })
		form.cutting_order_detail = name
		form.item = payload?.detail?.item || form.item
		await loadDetailPermissions(name)
	}
	catch (reason) { error.value = reason?.message || "Unable to load the Cutting Order Detail." }
	finally { loadingDetail.value = false }
}

function openDetail(name) { selectedDetail.value = name; detailOpen.value = true }
async function detailSaved(payload) {
	const name = payload?.record?.name
	if (!name) return
	form.cutting_order_detail = name
	selectedDetail.value = name
	await loadDetail(name, name === loadedDetail.value)
}

function quantityMap(source) {
	return new Map(source.flatMap((group) => (group.items || []).flatMap((row) => Object.entries(row.values || {}).map(([size, value]) => [quantityKey(group, row, size), Number(value?.qty ?? value ?? 0)]))))
}

function restoreQuantities(target, values) {
	for (const group of target) for (const row of group.items || []) for (const size of Object.keys(row.values || {})) {
		const key = quantityKey(group, row, size)
		if (values.has(key)) row.values[size] = { qty: values.get(key) }
	}
}

function quantityKey(group, row, size) {
	const sorted = (value) => Object.fromEntries(Object.entries(value || {}).sort(([left], [right]) => left.localeCompare(right)))
	return JSON.stringify([
		row.name || "",
		sorted(row.attributes),
		sorted(row.item_keys),
		row.primary_attribute || group.primary_attribute || "",
		size,
	])
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
		const payload = await saveCuttingOrder({
			cutting_order_detail: form.cutting_order_detail,
			cutting_location: form.cutting_location || null,
			maximum_no_of_plys: form.maximum_no_of_plys,
			maximum_allow_percent: form.maximum_allow_percent,
			item_details: clone(groups.value),
		}, { name: props.name, submit, expectedModified: modified.value })
		applyPayload(payload)
		cleanSignature.value = signature.value
		emit("saved", payload?.record || {})
	} catch (reason) { error.value = reason?.message || "Unable to save the Cutting Order." }
	finally { saving.value = "" }
}

function beforeUnload(event) { if (dirty.value) { event.preventDefault(); event.returnValue = "" } }
function keepEditing() { discardVisible.value = false; pendingNavigation?.(false); pendingNavigation = null }
function discardChanges() { discardVisible.value = false; allowNavigation = true; const next = pendingNavigation; pendingNavigation = null; next?.() }
onBeforeRouteLeave((_to, _from, next) => { if (allowNavigation || !dirty.value) return next(); pendingNavigation = next; discardVisible.value = true })
onMounted(() => { window.addEventListener("beforeunload", beforeUnload); load() })
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
watch(() => props.name, load)
</script>

<style scoped>
.cutting-order-editor { display: flex; min-width: 0; min-height: calc(100dvh - 98px); padding: var(--erp-space-4); flex-direction: column; gap: var(--erp-space-3); }
.order-editor-header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding-bottom: var(--erp-space-3); border-bottom: 1px solid var(--erp-border); }
.order-editor-header > div:first-child { display: grid; gap: 3px; }
.order-editor-header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: 0.035em; text-transform: uppercase; }
.order-editor-header h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -0.025em; }
.order-editor-actions { display: flex; align-items: center; gap: 8px; }
.order-editor-loading, .order-editor-body { display: grid; gap: var(--erp-space-3); min-width: 0; }
.order-editor-section { display: grid; gap: var(--erp-space-3); padding: var(--erp-space-3); background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.order-editor-section > header { padding-bottom: 8px; border-bottom: 1px solid var(--erp-border); }
.order-editor-section h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.order-editor-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 20px; }
.order-editor-field { display: grid; align-content: start; gap: 6px; }
.order-editor-field--detail { grid-column: 1 / -1; }
.order-editor-field > label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.order-editor-field > label span { color: var(--p-red-500); }
.detail-selector { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: end; gap: 8px; }
.discard-copy { margin: 0; color: var(--erp-text-muted); }
@media (max-width: 760px) { .order-editor-header { align-items: stretch; flex-direction: column; } .order-editor-actions { flex-wrap: wrap; } .order-editor-fields { grid-template-columns: 1fr; } .detail-selector { grid-template-columns: 1fr; } }
</style>
