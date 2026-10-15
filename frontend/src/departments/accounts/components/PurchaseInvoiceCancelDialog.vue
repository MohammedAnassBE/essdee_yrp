<template>
	<Dialog
		:visible="visible"
		modal
		header="Cancel Purchase Invoice?"
		class="erp-dialog--sm"
		:closable="!busy"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<div class="purchase-invoice-cancel-dialog">
			<span class="purchase-invoice-cancel-dialog__icon" aria-hidden="true">
				<i class="pi pi-exclamation-triangle" />
			</span>
			<p>Cancelling this Purchase Invoice applies the existing reversal checks and cannot be undone.</p>
			<label v-if="hasErpInvoice" for="purchase-invoice-keep-erp">
				<Checkbox
					input-id="purchase-invoice-keep-erp"
					v-model="keepErpInvoice"
					binary
					:disabled="busy"
				/>
				<span>Cancel without cancelling ERP invoice</span>
			</label>
		</div>
		<template #footer>
			<Button label="Keep Invoice" severity="secondary" text :disabled="busy" @click="setVisible(false)" />
			<Button
				label="Cancel Purchase Invoice"
				icon="pi pi-ban"
				severity="danger"
				:loading="busy"
				@click="confirm"
			/>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import { ref, watch } from "vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
	hasErpInvoice: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])
const keepErpInvoice = ref(false)

function setVisible(value) {
	if (!value && props.busy) return
	emit("update:visible", value)
}

function confirm() {
	emit("confirm", {
		cancel_without_cancelling_erp_inv: props.hasErpInvoice && keepErpInvoice.value ? 1 : 0,
	})
}

watch(() => props.visible, (visible, previous) => {
	if (visible && !previous) keepErpInvoice.value = false
})
</script>

<style scoped>
.purchase-invoice-cancel-dialog { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 13px; padding: 4px 1px 8px; }
.purchase-invoice-cancel-dialog__icon { display: grid; width: 40px; height: 40px; color: var(--erp-danger); border: 1px solid color-mix(in srgb, var(--erp-danger) 22%, white); border-radius: var(--erp-control-radius); background: var(--erp-danger-soft); place-items: center; }
.purchase-invoice-cancel-dialog p { margin: 2px 0 0; color: var(--erp-text); font-size: .88rem; line-height: 1.55; }
.purchase-invoice-cancel-dialog label { display: flex; align-items: center; grid-column: 1 / -1; gap: 9px; padding: 10px 11px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 670; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-soft); }
</style>
