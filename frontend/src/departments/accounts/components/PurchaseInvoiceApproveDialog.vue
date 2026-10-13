<template>
	<Dialog
		:visible="visible"
		modal
		header="Approve Invoice"
		class="erp-dialog--sm"
		:closable="!busy"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<label class="purchase-invoice-approve-dialog" for="purchase-invoice-approval-comments">
			<span>Comments</span>
			<Textarea
				id="purchase-invoice-approval-comments"
				v-model="comments"
				rows="4"
				auto-resize
				fluid
				:disabled="busy"
			/>
		</label>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="setVisible(false)" />
			<Button label="Approve" icon="pi pi-check-circle" :loading="busy" @click="approve" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Textarea from "primevue/textarea"
import { ref, watch } from "vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "approve"])
const comments = ref("")

function setVisible(value) {
	if (!value && props.busy) return
	emit("update:visible", value)
}

function approve() {
	emit("approve", comments.value.trim())
}

watch(() => props.visible, (visible, previous) => {
	if (visible && !previous) comments.value = ""
})
</script>

<style scoped>
.purchase-invoice-approve-dialog { display: grid; gap: 7px; padding: 4px 1px 8px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
</style>
