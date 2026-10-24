<template>
	<div class="work-order-action-panel__fields debit-entry-fields">
		<label><span>Debit No *</span><InputText :model-value="debitNo" fluid @update:model-value="emit('update:debitNo', $event)" /></label>
		<label><span>Debit Value *</span><InputNumber :model-value="debitValue" :min="0" :min-fraction-digits="0" :max-fraction-digits="2" fluid @update:model-value="emit('update:debitValue', $event)" /></label>
		<label class="work-order-action-panel__wide"><span>Reason *</span><Textarea :model-value="reason" rows="3" auto-resize fluid @update:model-value="emit('update:reason', $event)" /></label>
		<label class="work-order-action-panel__wide">
			<span>Debit Document</span>
			<input ref="fileInput" type="file" hidden :disabled="busy" @change="pickFile" />
			<div class="work-order-action-panel__check">
				<Button :label="debitDocument ? 'Replace' : 'Attach'" size="small" severity="secondary" outlined :loading="uploading" :disabled="busy" @click.prevent="fileInput?.click()" />
				<span v-if="debitDocument">{{ documentName }}</span>
				<Button v-if="debitDocument" label="Clear" size="small" severity="secondary" text :disabled="busy" @click.prevent="emit('update:debitDocument', '')" />
			</div>
		</label>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Textarea from "primevue/textarea"
import { computed, ref } from "vue"

const props = defineProps({
	debitNo: { type: String, default: "" },
	debitValue: { type: Number, default: null },
	reason: { type: String, default: "" },
	debitDocument: { type: String, default: "" },
	busy: { type: Boolean, default: false },
	uploading: { type: Boolean, default: false },
})
const emit = defineEmits(["update:debitNo", "update:debitValue", "update:reason", "update:debitDocument", "attach"])
const fileInput = ref(null)
const documentName = computed(() => String(props.debitDocument || "").split("/").pop())

function pickFile(event) {
	const file = event.target.files?.[0]
	event.target.value = ""
	if (file) emit("attach", file)
}
</script>

<style scoped>
.debit-entry-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.debit-entry-fields > label { display: grid; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.debit-entry-fields .work-order-action-panel__wide { grid-column: 1 / -1; }
.debit-entry-fields .work-order-action-panel__check { display: flex; align-items: center; gap: var(--erp-space-2); }
@media (max-width: 700px) { .debit-entry-fields { grid-template-columns: 1fr; } .debit-entry-fields .work-order-action-panel__wide { grid-column: auto; } }
@media (max-width: 1024px), (pointer: coarse) { .debit-entry-fields :deep(.p-button) { min-height: 44px; } }
</style>
