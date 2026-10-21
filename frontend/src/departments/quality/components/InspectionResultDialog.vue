<template>
	<Dialog :visible="visible" modal header="Update Status" class="erp-dialog--sm" :closable="!busy" :dismissable-mask="false" @update:visible="emit('update:visible', $event)">
		<FormField v-model="result" :field="{ fieldname: 'result', label: 'Result', fieldtype: 'Select', options: 'Pass\nFail' }" required :disabled="busy" />
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
			<Button label="Update Status" icon="pi pi-check" :loading="busy" :disabled="!['Pass', 'Fail'].includes(result)" @click="confirm" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { ref, watch } from "vue"
import FormField from "../../../components/common/FormField.vue"

const props = defineProps({ visible: Boolean, busy: Boolean })
const emit = defineEmits(["update:visible", "confirm"])
const result = ref("")
watch(() => props.visible, (visible) => { if (visible) result.value = "" })
function confirm() {
	if (!props.busy && ["Pass", "Fail"].includes(result.value)) emit("confirm", result.value)
}
</script>
