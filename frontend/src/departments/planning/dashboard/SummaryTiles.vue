<template>
	<div class="pd-tiles" :style="{ '--pd-tile-count': tiles.length }" :aria-label="label">
		<component
			:is="clickable ? 'button' : 'div'"
			v-for="tile in tiles"
			:key="tile.key"
			:type="clickable ? 'button' : undefined"
			class="pd-tile"
			:class="{ 'pd-tile--alert': tile.alert, 'pd-tile--clickable': clickable }"
			:title="tile.title || undefined"
			:data-stat="tile.key"
			@click="clickable && emit('select', tile.key)"
		>
			<span class="pd-tile__label">{{ tile.label }}</span>
			<span class="pd-tile__value"><b>{{ tile.value }}</b><small v-if="tile.unit">{{ tile.unit }}</small></span>
			<span class="pd-tile__foot">{{ tile.foot }}</span>
		</component>
	</div>
</template>

<script setup>
/** KPI tiles: label, big figure, faint foot; buttons when `clickable`. */
defineProps({
	tiles: { type: Array, required: true },
	label: { type: String, default: "Summary" },
	clickable: Boolean,
})
const emit = defineEmits(["select"])
</script>
