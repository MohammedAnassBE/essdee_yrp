<template>
	<div class="correction-section">
		<div v-if="!blocks.length" class="correction-empty">
			No correction items{{ editable ? " for this Work Order." : "." }}
		</div>
		<div
			v-for="(block, bi) in blocks"
			:key="block.work_order_correction || bi"
			class="correction-block"
		>
			<div class="correction-block-title">
				{{ block.title || block.work_order_correction }}
			</div>
			<StockItemGridEditor
				:ref="(el) => setBlockRef(bi, el)"
				grouped-field="correction_item_details"
				:value-fields="valueFields"
				:entry-fields="entryFields"
				:cell-fields="cellFields"
				:locked-items="true"
				:editable="editable"
				:show-secondary-toggle="showSecondaryToggle"
				:initial-data="block.item_details || []"
				@change="$emit('change')"
			/>
		</div>
	</div>
</template>

<script setup>
// Correction items for a stock voucher (Delivery Challan): the server's
// `correction_item_details` JSON is a list of BLOCKS — one per Work Order
// Correction ({ work_order_correction, title, item_details }) — displayed as
// one grouped table per correction (Desk CorrectionItemEditor parity). Rows
// derive from the corrections; the user only enters quantities, so every
// block's grid runs with lockedItems (no add/edit/remove). getItems() returns
// the same block shape back for the save payload; the server's
// ungroup_correction_items_from_ui stamps work_order_correction per row.
import { ref, watch } from "vue"
import StockItemGridEditor from "./StockItemGridEditor.vue"

const props = defineProps({
	editable: { type: Boolean, default: true },
	valueFields: { type: Array, default: () => [] },
	entryFields: { type: Array, default: () => [] },
	cellFields: { type: Array, default: () => [] },
	showSecondaryToggle: { type: Boolean, default: false },
	// Optional blocks to load on mount / change (read-only view use); edit and
	// create flows hydrate imperatively via loadData like the other grids.
	initialBlocks: { type: [Array, String], default: null },
})

defineEmits(["change"])

const blocks = ref([])
const blockRefs = {}

function setBlockRef(index, el) {
	if (el) blockRefs[index] = el
	else delete blockRefs[index]
}

function loadData(data) {
	let parsed = data
	if (typeof parsed === "string") {
		try {
			parsed = JSON.parse(parsed || "[]")
		} catch (_) {
			parsed = []
		}
	}
	blocks.value = Array.isArray(parsed) ? parsed : []
}

// Block shape preserved; each block's live grid state replaces its item_details.
function getItems() {
	return blocks.value.map((block, bi) => ({
		...block,
		item_details: blockRefs[bi]?.getItems ? blockRefs[bi].getItems() : block.item_details || [],
	}))
}

function hasItems() {
	return blocks.value.length > 0
}

watch(
	() => props.initialBlocks,
	(v) => {
		if (v != null) loadData(v)
	},
	{ immediate: true },
)

defineExpose({ loadData, getItems, hasItems })
</script>

<style scoped>
.correction-section {
	display: flex;
	flex-direction: column;
	gap: 1rem;
}
.correction-empty {
	color: var(--esd-muted);
	font-size: 0.875rem;
}
.correction-block-title {
	color: var(--esd-muted);
	font-size: 0.8125rem;
	font-weight: 600;
	margin-bottom: 0.375rem;
}
</style>
