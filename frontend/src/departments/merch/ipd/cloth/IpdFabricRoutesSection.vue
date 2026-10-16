<template>
	<IpdSection :section-key="sectionKey">
		<template v-if="!readonly" #actions>
			<Button label="Add route" icon="pi pi-plus" text severity="secondary" size="small" @click="routes.add(newRoute())" />
		</template>
		<div class="ipd-cloth-stack">
			<EntryGrid
				v-if="routes.rows.value.length"
				ref="routeGrid"
				:rows="routes.keys.value"
				:columns="columns"
				:model-value="routes.model.value"
				:readonly="readonly"
				:errors="routes.errors.value"
				title="Fabric routes"
				meta="Finished colour and dia from the knitted colour and dia"
				aria-label="Fabric routes"
				row-header-label="#"
				:toolbar="['fillRight', 'fillDown', 'paste', 'clear']"
				:removable-rows="!readonly"
				@update:model-value="routes.update"
				@remove-row="routes.remove"
			/>
			<p v-else class="erp-empty-state erp-empty-state--compact ipd-cloth-empty">No fabric routes. Lots then use the fabric processes as they are.</p>
		</div>
	</IpdSection>
</template>

<script setup>
import { computed, ref } from "vue"
import Button from "primevue/button"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { withStoredOptions } from "./clothGrids.js"
import { useClothSection, useClothTable, useGridFocus } from "./useClothTable.js"
import "./cloth.css"

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})

const FIELDS = ["finished_colour", "finished_dia", "knitting_output_colour", "knitting_output_dia", "use_dyed_yarn"]
const COLOUR_FIELDS = ["finished_colour", "knitting_output_colour"]
const DIA_FIELDS = ["finished_dia", "knitting_output_dia"]

const { editor, readonly, cloth } = useClothSection(props)
const routes = useClothTable(editor, "fabric_routes", FIELDS)
const colours = computed(() => withStoredOptions(cloth.value.colour_values || [], routes.rows.value, COLOUR_FIELDS))
const dias = computed(() => withStoredOptions(cloth.value.dia_values || [], routes.rows.value, DIA_FIELDS))
const columns = computed(() => [
	{ key: "finished_colour", label: "Finished colour", type: "value", options: colours.value },
	{ key: "finished_dia", label: "Finished dia", type: "value", options: dias.value },
	{ key: "knitting_output_colour", label: "Knitting colour", type: "value", options: colours.value },
	{ key: "knitting_output_dia", label: "Knitting dia", type: "value", options: dias.value },
	{ key: "use_dyed_yarn", label: "Dyed yarn", type: "check" },
])
const routeGrid = ref(null)

function newRoute() {
	const last = routes.rows.value.at(-1)
	return { finished_colour: last?.finished_colour || null, finished_dia: null, knitting_output_colour: last?.knitting_output_colour || null, knitting_output_dia: null, use_dyed_yarn: 0 }
}

useGridFocus(editor, props.sectionKey, {
	fabric_routes: { grid: routeGrid, firstRow: () => routes.keys.value[0]?.key, firstColumn: "finished_colour" },
})
</script>
