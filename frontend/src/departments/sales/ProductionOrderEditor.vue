<template>
	<section class="ppo-editor erp-card erp-editor-shell" aria-label="Production Order editor">
		<header class="erp-editor-header ppo-editor__header"><div><span>{{ name || "New document" }}</span><h1 class="erp-doc-title">{{ name ? "Edit Production Order" : "New Production Order" }}</h1></div><div class="erp-editor-actions"><Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="busy" @click="emit('cancel')" /><DocumentSaveButton :saved="Boolean(record.name || name)" :dirty="dirty" :docstatus="Number(record.docstatus || 0)" :document-label="`Production Order ${record.name || name}`.trim()" :loading="Boolean(saving)" :disabled="busy || !canSave" show-submit submit-label="Request Approval" @save="save(false)" @submit="save(true)" /></div></header>
		<DocumentErrorDialog :message="loadFailed ? '' : error" title="Production Order could not be saved" @dismiss="error = ''" />
		<div v-if="loading" class="ppo-editor__loading"><Skeleton height="180px" /><Skeleton height="300px" /></div>
		<WorkspaceLoadError v-else-if="loadFailed" title="Production Order editor unavailable" :message="error" @retry="load" />
		<div v-else class="ppo-editor__body">
			<section class="ppo-editor__section"><header><span>ORDER</span><h2>Production & delivery</h2></header><div class="ppo-editor__fields">
				<div class="ppo-editor__field"><label class="erp-field-label">Series<span class="erp-required-mark">*</span></label><Select v-model="form.naming_series" :options="selectOptions('naming_series')" :disabled="Boolean(name)" fluid /></div>
				<LinkField v-model="form.item" label="Item *" doctype="Item" :filters="productionOrderItemFilters" :disabled="Boolean(name)" required @select="itemSelected" />
				<LinkField v-model="form.production_detail" label="Production Detail" doctype="YRP Item Production Detail" show-clear />
				<LinkField v-model="form.production_term" label="Production Term *" doctype="YRP Production Term" required />
				<label class="ppo-editor__field"><span class="erp-field-label">Delivery Date<span class="erp-required-mark">*</span></span><DateField v-model="form.delivery_date" fluid /></label>
				<label class="ppo-editor__field"><span class="erp-field-label">Don't Deliver After<span class="erp-required-mark">*</span></span><DateField v-model="form.dont_deliver_after" fluid /></label>
				<label class="ppo-editor__check"><Checkbox v-model="form.skip_box_sticker_print" binary input-id="skip-box-sticker" /><span>Skip Box Sticker Print</span></label>
				<label class="ppo-editor__field ppo-editor__field--wide"><span class="erp-field-label">Comments</span><Textarea v-model="form.comments" rows="2" fluid /></label>
			</div></section>
			<ProductionOrderMatrix v-if="matrixRows.length" :rows="matrixRows" :ordered="matrix.ordered || {}" editable @update="updateMatrix" />
			<div v-else class="erp-empty-state ppo-editor__empty"><span class="erp-empty-state__text">Select an Item to load its size matrix.</span></div>
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { computed, onMounted, reactive, ref, watch } from "vue"

import { getProductionOrderEditor, saveProductionOrder } from "../../api/sales.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import ProductionOrderMatrix from "./ProductionOrderMatrix.vue"
import { productionOrderItemFilters } from "./productionOrderOptions.js"

const props = defineProps({ name: { type: String, default: "" } })
const emit = defineEmits(["saved", "cancel"])
const form = reactive({ naming_series: "PPO-", item: "", production_detail: "", production_term: "", delivery_date: "", dont_deliver_after: "", comments: "", skip_box_sticker_print: false })
const schemas = ref([])
const matrix = ref({})
const loading = ref(true)
const loadingMatrix = ref(false)
const saving = ref("")
const error = ref("")
const loaded = ref(false)
const modified = ref("")
const record = ref({})
const cleanSignature = ref("")
const signature = computed(() => JSON.stringify({ form, matrix: matrix.value }))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)
const busy = computed(() => loading.value || loadingMatrix.value || Boolean(saving.value))
const loadFailed = computed(() => Boolean(error.value && !loaded.value))
const matrixRows = computed(() => (matrix.value.primary_values || []).map((size) => ({ size, quantity: number(matrix.value.items?.[size]?.qty), ratio: number(matrix.value.items?.[size]?.ratio), prices: { mrp: number(matrix.value.items?.[size]?.mrp), wholesale_price: number(matrix.value.items?.[size]?.wholesale), retail_price: number(matrix.value.items?.[size]?.retail) } })))
const canSave = computed(() => Boolean(form.item && form.production_term && form.delivery_date && form.dont_deliver_after && matrixRows.value.length && matrixRows.value.some((row) => row.quantity > 0)))

function number(value) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0 }
function selectOptions(fieldname) { return String(schemas.value.find((field) => field.fieldname === fieldname)?.options || "").split("\n").filter(Boolean) }
function apply(payload) {
	record.value = payload?.record || {}
	for (const field of payload?.fields || []) if (field.fieldname in form) form[field.fieldname] = field.fieldtype === "Check" ? Boolean(Number(field.value)) : field.value ?? ""
	schemas.value = payload?.fields || []
	matrix.value = JSON.parse(JSON.stringify(payload?.matrix || {}))
	modified.value = payload?.modified || ""
	loaded.value = true
	cleanSignature.value = signature.value
}
async function load() { loading.value = true; error.value = ""; try { apply(await getProductionOrderEditor(props.name || null) || {}) } catch (reason) { error.value = reason?.message || "Unable to load the Production Order editor." } finally { loading.value = false } }
async function itemSelected() { if (props.name || !form.item) return; loadingMatrix.value = true; error.value = ""; try { const payload = await getProductionOrderEditor(null, { item: form.item }); const retained = { ...form }; apply(payload || {}); Object.assign(form, retained, { item: retained.item }) } catch (reason) { error.value = reason?.message || "Unable to load the Item size matrix." } finally { loadingMatrix.value = false } }
function updateMatrix({ size, field, value }) { if (!matrix.value.items?.[size]) return; matrix.value.items[size][field === "quantity" ? "qty" : "ratio"] = value }
function itemDetails() { return [{ item: form.item, entries: matrixRows.value.map((row) => ({ attributes: { [matrix.value.primary_attribute || "Size"]: row.size }, qty: row.quantity, ratio: row.ratio, mrp: row.prices.mrp, wholesale: row.prices.wholesale_price, retail: row.prices.retail_price })) }] }
async function save(submit) { saving.value = submit ? "submit" : "save"; error.value = ""; try { const payload = await saveProductionOrder({ ...form, item_details: itemDetails() }, { name: record.value.name || props.name || null, submit, expectedModified: modified.value }); record.value = payload?.record || {}; modified.value = record.value.modified || modified.value; cleanSignature.value = signature.value; emit("saved", payload?.record || {}) } catch (reason) { error.value = reason?.message || "Unable to save this Production Order." } finally { saving.value = "" } }
onMounted(load)
watch(() => props.name, load)
</script>

<style scoped>
.ppo-editor { display: flex; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); flex-direction: column; gap: var(--erp-space-3); }
.ppo-editor__header > div:first-child span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: .04em;
	text-transform: uppercase;
}
.ppo-editor__header h1 { margin: 0; color: var(--erp-text); }
.ppo-editor__loading, .ppo-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.ppo-editor__section { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.ppo-editor__section > header {
	padding: 9px 13px;
	border-bottom: 1px solid var(--erp-border);
	background: transparent;
}
.ppo-editor__section > header span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
	letter-spacing: .05em;
}
.ppo-editor__section h2 {
	margin: 2px 0 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-md);
}
.ppo-editor__fields {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 16px 28px;
	padding: 13px;
}
.ppo-editor__field { display: grid; align-content: start; gap: 6px; }
.ppo-editor__field--wide { grid-column: 1 / -1; }
.ppo-editor__check {
	display: flex;
	align-items: center;
	gap: 8px;
	align-self: end;
	min-height: var(--erp-control-height);
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-medium);
}
@media (max-width: 900px) { .ppo-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .ppo-editor__fields { grid-template-columns: 1fr; } .ppo-editor__field--wide { grid-column: auto; } }
@media (max-width: 620px) {
	.ppo-editor__section > header,
	.ppo-editor__fields {
		padding-inline: var(--erp-space-3);
	}
}
.ppo-editor__empty {
	min-height: 120px;
}
</style>
