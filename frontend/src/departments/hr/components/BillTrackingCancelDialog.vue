<template>
	<Dialog
		class="bill-tracking-cancel-dialog erp-dialog--sm"
		:visible="visible"
		modal
		header="Cancel bill"
		:closable="!busy"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<div class="bill-tracking-cancel-dialog__form">
			<label for="bill-tracking-cancel-reason">
				<span>Cancellation reason <b aria-hidden="true">*</b></span>
				<Textarea
					ref="reasonField"
					id="bill-tracking-cancel-reason"
					v-model="reason"
					rows="4"
					auto-resize
					fluid
					required
					:invalid="attempted && !reason.trim()"
					:disabled="busy"
				/>
			</label>
			<small v-if="attempted && !reason.trim()" class="bill-tracking-cancel-dialog__error" role="alert">
				Enter a cancellation reason.
			</small>
		</div>
		<template #footer>
			<Button label="Keep Bill" severity="secondary" text :disabled="busy" @click="setVisible(false)" />
			<Button label="Cancel Bill" icon="pi pi-ban" severity="danger" :loading="busy" @click="submit" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Textarea from "primevue/textarea"
import { nextTick, ref, watch } from "vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])
const reasonField = ref(null)
const reason = ref("")
const attempted = ref(false)

watch(() => props.visible, (visible) => {
	if (!visible) return
	reason.value = ""
	attempted.value = false
	nextTick(() => reasonField.value?.$el?.focus?.())
})

function setVisible(visible) {
	if (!props.busy) emit("update:visible", visible)
}

function submit() {
	attempted.value = true
	if (!reason.value.trim()) {
		reasonField.value?.$el?.focus?.()
		return
	}
	emit("confirm", reason.value.trim())
}
</script>

<style scoped>
.bill-tracking-cancel-dialog__form { display: grid; gap: 7px; padding-block: 4px; }
.bill-tracking-cancel-dialog__form label { display: grid; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.bill-tracking-cancel-dialog__form b, .bill-tracking-cancel-dialog__error { color: var(--erp-danger); }
.bill-tracking-cancel-dialog__error { font-size: var(--erp-font-size-min); }
</style>
