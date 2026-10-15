<template>
	<div v-if="!readonly" class="lotwise-command-bar" aria-label="Costing commands">
		<div class="lotwise-command-bar__label">
			<span>Costing tools</span>
			<small>Ctrl+E recalculates the current values</small>
		</div>
		<DocumentActionStrip :actions="actions" />
	</div>

	<Dialog
		v-model:visible="rateDialogVisible"
		modal
		header="Calculate Rate"
		class="erp-dialog--sm"
		:dismissable-mask="false"
	>
		<div class="lotwise-command-bar__dialog">
			<label for="lotwise-markdown-percent">Markdown Percent</label>
			<InputNumber
				id="lotwise-markdown-percent"
				v-model="markdownPercent"
				mode="decimal"
				:min-fraction-digits="0"
				:max-fraction-digits="6"
				suffix="%"
				fluid
				@keydown.enter="submitRate"
			/>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text @click="rateDialogVisible = false" />
			<Button
				label="Calculate Rate"
				icon="pi pi-calculator"
				:disabled="!hasMarkdownPercent"
				@click="submitRate"
			/>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import { computed, nextTick, ref } from "vue"

import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"

const props = defineProps({
	readonly: { type: Boolean, default: false },
	lot: { type: String, default: "" },
	costingType: { type: String, default: "" },
	busy: { type: Boolean, default: false },
	activeCommand: { type: String, default: "" },
})

const emit = defineEmits(["command"])
const rateDialogVisible = ref(false)
const markdownPercent = ref(null)
const hasMarkdownPercent = computed(() => markdownPercent.value !== null
	&& markdownPercent.value !== ""
	&& Number.isFinite(Number(markdownPercent.value)))
const fetchDisabledReason = computed(() => {
	if (!props.lot) return "Select a Lot before fetching quantities."
	if (!props.costingType) return "Select a Lot Costing Type before fetching quantities."
	if (props.costingType === "Costing") return "Lot quantities are not used for the Costing type."
	return ""
})
const actions = computed(() => [
	{
		key: "recalculate",
		label: "Recalculate",
		icon: "pi pi-refresh",
		primary: true,
		loading: props.activeCommand === "recalculate",
		disabled: props.busy,
		command: () => emit("command", "recalculate", null),
	},
	{
		key: "calculate-rate",
		label: "Calculate Rate",
		icon: "pi pi-calculator",
		disabled: props.busy,
		command: openRateDialog,
	},
	{
		key: "fetch-lot-qty",
		label: "Fetch Lot Qty",
		icon: "pi pi-download",
		loading: props.activeCommand === "fetch_lot_qty",
		disabled: props.busy || Boolean(fetchDisabledReason.value),
		disabledReason: fetchDisabledReason.value,
		command: () => emit("command", "fetch_lot_qty", null),
	},
])

function openRateDialog() {
	markdownPercent.value = null
	rateDialogVisible.value = true
}

async function submitRate() {
	document.activeElement?.blur?.()
	await nextTick()
	if (!hasMarkdownPercent.value) return
	const percent = Number(markdownPercent.value)
	rateDialogVisible.value = false
	emit("command", "calculate_rate", { percent })
}
</script>

<style scoped>
.lotwise-command-bar {
	display: flex;
	min-width: 0;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
	padding: 10px 14px;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.lotwise-command-bar__label {
	display: grid;
	gap: 2px;
}

.lotwise-command-bar__label span,
.lotwise-command-bar__dialog label {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 740;
}

.lotwise-command-bar__label small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.lotwise-command-bar__dialog {
	display: grid;
	gap: 7px;
	padding: 4px 0 8px;
}

@media (max-width: 720px) {
	.lotwise-command-bar {
		align-items: stretch;
		flex-direction: column;
	}
}
</style>
