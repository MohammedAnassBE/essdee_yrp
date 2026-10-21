<template>
	<dl class="quality-stat-tiles" aria-label="Inspection quantities and defects">
		<div v-for="tile in tiles" :key="tile.key" class="quality-stat-tile" :class="`quality-stat-tile--${tile.tone}`">
			<dt>{{ tile.label }}</dt><dd>{{ tile.value }}</dd><small v-if="tile.hint">{{ tile.hint }}</small>
		</div>
	</dl>
</template>

<script setup>
import { computed } from "vue"
import { inspectionStatTiles } from "../qualityViews.js"
const props = defineProps({ record: { type: Object, default: () => ({}) }, only: { type: Array, default: () => [] } })
const tiles = computed(() => inspectionStatTiles(props.record).filter((tile) => !props.only.length || props.only.includes(tile.key)))
</script>
