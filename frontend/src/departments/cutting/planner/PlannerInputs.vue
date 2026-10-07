<template>
	<section class="planner-inputs">
		<div class="planner-inputs__grid">
			<div class="planner-inputs__context">
				<label class="planner-field planner-field--description"><span>Description *</span><Textarea v-model="form.description" input-id="planner-description" aria-label="Description *" rows="1" :disabled="!editable" fluid /></label>
				<LinkField v-model="form.lot" label="Lot" doctype="SD YRP Lot" :disabled="!editable" :show-open-button="false" show-clear />
				<LinkField v-model="form.item" label="Item" doctype="Item" :disabled="!editable" :show-open-button="false" show-clear />
			</div>
			<div class="planner-inputs__constraints">
				<label class="planner-field"><span>Maximum Plies *</span><InputNumber v-model="form.max_plies" input-id="planner-max-plies" aria-label="Maximum Plies *" :min="1" :use-grouping="false" :disabled="!editable" fluid /></label>
				<label class="planner-field"><span>Maximum Pieces Per Marker *</span><InputNumber v-model="form.max_pieces" input-id="planner-max-pieces" aria-label="Maximum Pieces Per Marker *" :min="1" :use-grouping="false" :disabled="!editable" fluid /></label>
				<label class="planner-field"><span>Tolerance % *</span><InputNumber v-model="form.tolerance_pct" input-id="planner-tolerance" :min="0" :max="100" :max-fraction-digits="2" suffix="%" :disabled="!editable" fluid /></label>
				<label class="planner-field"><span>Maximum Lays *</span><InputNumber v-model="form.max_lays" input-id="planner-max-lays" :min="1" :use-grouping="false" :disabled="!editable" fluid /></label>
				<label class="planner-check"><Checkbox v-model="form.tubular" binary :true-value="1" :false-value="0" input-id="planner-tubular" :disabled="!editable" /><span><strong>Tubular Fabric</strong><small>Force every ply count to an even number.</small></span></label>
			</div>
		</div>
		<PlannerOrderMatrix :rows="form.order_details" :editable="editable" @update:rows="form.order_details = $event" />
		<div v-if="editable && isNew" class="planner-inputs__footer"><Button label="Save Draft" icon="pi pi-save" :loading="saving" :disabled="!canSave" @click="emitSave" /></div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import InputNumber from "primevue/inputnumber"
import Textarea from "primevue/textarea"
import { computed, reactive, watch } from "vue"

import LinkField from "../../../components/common/LinkField.vue"
import PlannerOrderMatrix from "./PlannerOrderMatrix.vue"

const props = defineProps({ record: { type: Object, default: () => ({}) }, editable: Boolean, saving: Boolean, isNew: Boolean })
const emit = defineEmits(["save"])
const form = reactive({ lot: "", item: "", description: "", max_plies: null, max_pieces: null, tolerance_pct: 3, max_lays: 8, tubular: 0, order_details: [] })
const canSave = computed(() => Boolean(form.description.trim() && form.max_plies > 0 && form.max_pieces > 0 && form.max_lays > 0 && form.order_details.length && form.order_details.every((row) => String(row.size || "").trim() && Number(row.qty) >= 0) && form.order_details.some((row) => Number(row.qty) > 0)))

function clone(value) { return JSON.parse(JSON.stringify(value ?? [])) }
watch(() => props.record, (record) => {
	for (const key of ["lot", "item", "description", "max_plies", "max_pieces", "tolerance_pct", "max_lays", "tubular"]) form[key] = record?.[key] ?? ({ tolerance_pct: 3, max_lays: 8, tubular: 0 }[key] ?? "")
	form.order_details = clone(record?.order_details || [])
}, { immediate: true, deep: true })
function emitSave() {
	emit("save", {
		lot: form.lot || null, item: form.item || null, description: form.description.trim(), max_plies: form.max_plies,
		max_pieces: form.max_pieces, tolerance_pct: form.tolerance_pct, max_lays: form.max_lays, tubular: form.tubular,
		order_details: form.order_details.map(({ _row_key, ...row }) => ({ ...row, name: row.name || undefined, size: String(row.size || "").trim(), qty: Number(row.qty || 0) })),
	})
}
defineExpose({ canSave, save: emitSave })
</script>

<style scoped>
.planner-inputs { display: grid; min-width: 0; padding: var(--erp-space-3) var(--erp-space-4); gap: var(--erp-space-3); }
.planner-inputs__grid { display: grid; min-width: 0; gap: 10px; }
.planner-inputs__context { display: grid; grid-template-columns: minmax(320px, 1.7fr) minmax(220px, .8fr) minmax(280px, 1fr); min-width: 0; align-items: end; gap: var(--erp-space-3); }
.planner-inputs__constraints { display: grid; grid-template-columns: minmax(150px, 180px) minmax(200px, 220px) repeat(2, minmax(150px, 180px)) minmax(250px, max-content); min-width: 0; align-items: end; justify-content: start; gap: var(--erp-space-3); }
.planner-field { display: grid; min-width: 0; gap: 6px; }
.planner-field > span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.planner-field--description :deep(textarea) { min-height: var(--erp-control-height); resize: vertical; }
.planner-check { display: flex; min-height: var(--erp-control-height); align-items: center; gap: 9px; }
.planner-check > span { display: grid; gap: 1px; color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.planner-check small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 500; }
.planner-inputs__footer { display: flex; justify-content: flex-end; }
@media (max-width: 1180px) {
	.planner-inputs__context { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.planner-field--description { grid-column: 1 / -1; }
	.planner-inputs__constraints { grid-template-columns: repeat(4, minmax(0, 1fr)); }
	.planner-check { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
	.planner-inputs__context, .planner-inputs__constraints { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.planner-field--description, .planner-check { grid-column: 1 / -1; }
}
@media (max-width: 620px) {
	.planner-inputs { padding: var(--erp-space-3); }
	.planner-inputs__context { grid-template-columns: 1fr; }
	.planner-inputs__constraints { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.planner-field--description, .planner-check { grid-column: auto; }
	.planner-check { grid-column: 1 / -1; }
}
</style>
