<template>
	<div class="lot-tab-stack">
		<Message
			v-if="isLocked"
			severity="warn"
			:closable="false"
		>
			Locked: Time &amp; Action exists or the Lot was transferred.
		</Message>
		<template
			v-for="(group, index) in groups"
			:key="index"
		>
			<EntryGrid
				:rows="gridRows(group)"
				:columns="gridColumns(group)"
				:model-value="gridValues(group)"
				:readonly="isLocked || disabled"
				title="Lot Order Details · Order"
				row-header-label="Colour / Attributes"
				totals="both"
				@update:model-value="updateGroup(group, $event)"
			/>
		</template>
	</div>
</template>
<script setup>
import Message from "primevue/message"
import EntryGrid from "../../../components/common/EntryGrid.vue"
const props = defineProps({
	groups: { type: Array, required: true },
	colourAttribute: { type: String, default: "" },
	version: { type: String, default: "" },
	isLocked: Boolean,
	disabled: Boolean,
})
function sizes(group) {
	return group.primary_attribute ? group.primary_attribute_values : ["default"]
}
function gridRows(group) {
	return group.items.map((item, index) => ({
		key: String(index),
		label: Object.values(item.attributes).join(" / ") || `Row ${index + 1}`,
	}))
}
function gridColumns(group) {
	return sizes(group).map((size) => ({
		key: size,
		label: size === "default" ? "Order" : size,
		type: "number",
		min: 0,
	}))
}
function gridValues(group) {
	return Object.fromEntries(
		group.items.map((item, index) => [
			index,
			Object.fromEntries(sizes(group).map((size) => [size, item.values[size]?.qty || 0])),
		]),
	)
}
function updateGroup(group, values) {
	if (props.isLocked || props.disabled) return
	group.items.forEach((item, index) =>
		sizes(group).forEach((size) => {
			item.values[size].qty = values[index][size]
		}),
	)
}
</script>
