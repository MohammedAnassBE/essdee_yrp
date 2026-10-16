<template>
	<div class="lot-tab-stack">
		<Message
			v-if="isLocked"
			severity="warn"
			:closable="false"
		>
			Locked: Time &amp; Action exists or the Lot was transferred.
		</Message>
		<Message
			v-else-if="productionOrder && hasOrderDetails"
			severity="secondary"
			:closable="false"
		>
			Box quantities are recalculated from Lot Order Details when you save.
		</Message>
		<template v-if="itemDetails">
			<EntryGrid
				class="merch-box-grid"
				:rows="grid.rows"
				:columns="grid.columns"
				:model-value="grid.values"
				:errors="errors"
				:readonly="disabled || locked"
				title="Box quantity"
				row-header-label="Attributes"
				@update:model-value="updateGrid"
			/>
			<MerchBoxRowComposer
				v-if="!locked"
				:item-details="itemDetails"
				:composer-open="composerOpen"
				:disabled="disabled"
				@update:item-details="emit('update:itemDetails', $event)"
				@update:composer-open="emit('update:composerOpen', $event)"
			/>
		</template>
	</div>
</template>
<script setup>
import Message from "primevue/message"
import { computed } from "vue"
import EntryGrid from "../../../components/common/EntryGrid.vue"
import MerchBoxRowComposer from "./MerchBoxRowComposer.vue"
import { applyBoxGrid, boxGrid, boxGridErrors, isBoxLocked } from "./merchLotViews.js"
const props = defineProps({
	itemDetails: { type: Object, default: null },
	composerOpen: Boolean,
	productionOrder: { type: String, default: "" },
	hasOrderDetails: Boolean,
	isLocked: Boolean,
	boxLocked: Boolean,
	disabled: Boolean,
})
const emit = defineEmits(["update:itemDetails", "update:composerOpen"])
const grid = computed(() =>
	props.itemDetails ? boxGrid(props.itemDetails) : { rows: [], columns: [], values: {} },
)
const errors = computed(() => boxGridErrors(props.itemDetails))
const locked = computed(
	() =>
		props.boxLocked ||
		isBoxLocked(
			{ order_details: props.isLocked },
			props.productionOrder,
			props.hasOrderDetails,
		),
)
function updateGrid(values) {
	emit("update:itemDetails", applyBoxGrid(props.itemDetails, values))
}
</script>
<style scoped>
.merch-box-grid :deep(.entry-grid__box.is-error) {
	height: auto;
	min-height: var(--erp-control-height-compact);
	flex-direction: column;
	align-items: stretch;
	white-space: normal;
}
.merch-box-grid :deep(.entry-grid__box.is-error::after) {
	content: attr(title);
	display: block;
	color: var(--erp-danger);
	font-size: var(--erp-font-size-caption);
	text-align: left;
}
</style>
