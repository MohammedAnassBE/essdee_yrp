<template>
	<Dialog :visible="visible" modal header="Create Debit" class="erp-dialog--sm" :closable="!busy && !uploading" :dismissable-mask="false" @update:visible="close">
		<div class="inspection-debit">
			<FormField v-model="values.debit_value" :field="{ fieldname: 'debit_value', label: 'Debit Value', fieldtype: 'Currency' }" required :disabled="busy || uploading" />
			<FormField v-model="values.reason" :field="{ fieldname: 'reason', label: 'Reason', fieldtype: 'Small Text' }" required :disabled="busy || uploading" />
			<div>
				<p class="erp-field-label">Debit Document <span class="erp-required-mark">*</span></p>
				<InspectionImageUpload v-model="values.debit_document" accept-any doctype="" fieldname="debit_document" :disabled="busy" @uploading-change="uploading = $event" />
			</div>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy || uploading" @click="close(false)" />
			<Button label="Create Debit" icon="pi pi-plus" :loading="busy" :disabled="!valid || uploading" @click="confirm" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { computed, reactive, ref, watch } from "vue"
import FormField from "../../../components/common/FormField.vue"
import InspectionImageUpload from "./InspectionImageUpload.vue"

const props = defineProps({ visible: Boolean, busy: Boolean })
const emit = defineEmits(["update:visible", "confirm"])
const values = reactive({ debit_value: null, reason: "", debit_document: "" })
const uploading = ref(false)
const valid = computed(() => Number.isFinite(Number(values.debit_value)) && Number(values.debit_value) > 0
	&& Boolean(values.reason.trim()) && Boolean(values.debit_document))

watch(() => props.visible, (visible) => {
	if (visible) Object.assign(values, { debit_value: null, reason: "", debit_document: "" })
})
function close(visible) {
	if (!props.busy && !uploading.value) emit("update:visible", visible)
}
function confirm() {
	if (props.busy || uploading.value || !valid.value) return
	emit("confirm", { ...values, reason: values.reason.trim() })
}
</script>

<style scoped>
.inspection-debit { display: grid; min-width: 0; gap: var(--erp-space-4); }
.inspection-debit :deep(input), .inspection-debit :deep(textarea), .inspection-debit :deep(.p-button) { min-height: 44px; }
</style>
