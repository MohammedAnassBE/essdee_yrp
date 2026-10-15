<template>
	<Dialog
		class="bill-tracking-assign-dialog erp-dialog--sm"
		:visible="visible"
		modal
		:header="bulk ? 'Assign selected bills' : 'Assign bill'"
		:closable="!busy"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<div class="bill-tracking-assign-dialog__form">
			<LinkField
				ref="departmentField"
				v-model="assignedTo"
				doctype="Department"
				label="Department"
				:invalid="attempted && !assignedTo"
				:disabled="busy"
				:show-open-button="false"
				required
				show-clear
			/>
			<small v-if="attempted && !assignedTo" class="bill-tracking-assign-dialog__error" role="alert">
				Choose a Department.
			</small>
			<label for="bill-tracking-assignment-remarks">
				<span>Remarks</span>
				<Textarea
					id="bill-tracking-assignment-remarks"
					v-model="remarks"
					rows="3"
					auto-resize
					fluid
					:disabled="busy"
				/>
			</label>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="setVisible(false)" />
			<Button
				:label="bulk ? 'Assign Selected' : 'Assign'"
				icon="pi pi-send"
				:loading="busy"
				@click="submit"
			/>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Textarea from "primevue/textarea"
import { nextTick, ref, watch } from "vue"

import LinkField from "../../../components/common/LinkField.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
	bulk: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "assign"])
const departmentField = ref(null)
const assignedTo = ref("")
const remarks = ref("")
const attempted = ref(false)

watch(() => props.visible, (visible) => {
	if (!visible) return
	assignedTo.value = ""
	remarks.value = ""
	attempted.value = false
	nextTick(() => departmentField.value?.focus())
})

function setVisible(visible) {
	if (!props.busy) emit("update:visible", visible)
}

function submit() {
	attempted.value = true
	if (!assignedTo.value) {
		departmentField.value?.focus()
		return
	}
	emit("assign", { assignedTo: assignedTo.value, remarks: remarks.value.trim() })
}
</script>

<style scoped>
.bill-tracking-assign-dialog__form { display: grid; gap: 12px; padding-block: 4px; }
.bill-tracking-assign-dialog__form label { display: grid; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.bill-tracking-assign-dialog__error { margin-top: -8px; color: var(--erp-danger); font-size: var(--erp-font-size-min); }
</style>
