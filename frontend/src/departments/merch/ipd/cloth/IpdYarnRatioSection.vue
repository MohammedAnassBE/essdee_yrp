<template>
	<IpdSection :section-key="sectionKey">
		<template v-if="!readonly" #actions>
			<Button label="Add yarn" icon="pi pi-plus" text severity="secondary" size="small" @click="ratios.add({ yarn_item: null, ratio: null })" />
		</template>
		<div class="ipd-cloth-stack">
			<EntryGrid
				v-if="ratios.rows.value.length"
				ref="ratioGrid" validation-field="yarn_ratio_details"
				:rows="ratios.keys.value"
				:columns="RATIO_COLUMNS"
				:model-value="ratios.model.value"
				:readonly="readonly"
				:errors="ratios.errors.value"
				title="Yarn Ratio"
				unit-hint="ratio %"
				meta="Must total 100%"
				aria-label="Yarns and ratios"
				row-header-label="#"
				totals="row"
				:toolbar="['fillDown', 'paste', 'clear']"
				:removable-rows="!readonly"
				@update:model-value="ratios.update"
				@remove-row="ratios.remove"
			/>
			<p v-else class="erp-empty-state erp-empty-state--compact ipd-cloth-empty">No yarns yet. Add the yarns this cloth is knitted from.</p>
			<p v-if="ratios.rows.value.length" class="ipd-cloth-strip" :class="totalOk ? 'ipd-cloth-strip--ok' : 'ipd-cloth-strip--error'" role="status">
				<i :class="totalOk ? 'pi pi-check-circle' : 'pi pi-exclamation-circle'" aria-hidden="true" />
				{{ totalOk ? "Ratios total 100%." : `Ratios total ${total}%. They must total 100%.` }}
			</p>
			<EntryGrid
				v-if="recipes.rows.value.length"
				ref="recipeGrid" validation-field="colour_yarn_recipes"
				:rows="recipes.keys.value"
				:columns="ipdLinkColumns(RECIPE_COLUMNS, editor, 'colour_yarn_recipes')"
				:model-value="recipes.model.value"
				readonly
				title="Colour-wise Yarn Recipes"
				meta="Built by the cloth program"
				aria-label="Colour-wise yarn recipes"
				row-header-label="#"
			/>
		</div>
	</IpdSection>
</template>

<script setup>
import { computed, ref } from "vue"
import Button from "primevue/button"

import { ipdLinkColumns } from "../ipdLinks.js"
import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { ratioTotal } from "./clothGrids.js"
import { useClothSection, useClothTable, useGridFocus } from "./useClothTable.js"
import "./cloth.css"

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})

const RATIO_FIELDS = ["yarn_item", "ratio"]
const RATIO_COLUMNS = [
	{ key: "yarn_item", label: "Yarn Item", type: "link", fieldtype: "Link", link_doctype: "Item", doctype: "Item", filters: { is_cloth_item: 0 } },
	{ key: "ratio", label: "Ratio (%)", type: "number", min: 0, precision: 3 },
]
const RECIPE_FIELDS = ["colour", "yarn_item", "yarn_colour", "ratio"]
const RECIPE_COLUMNS = [
	{ key: "colour", fieldtype: "Link", link_doctype: "YRP Item Attribute Value", label: "Fabric Colour", type: "text" },
	{ key: "yarn_item", fieldtype: "Link", link_doctype: "Item", label: "Yarn Item", type: "text" },
	{ key: "yarn_colour", fieldtype: "Link", link_doctype: "YRP Item Attribute Value", label: "Yarn Colour", type: "text" },
	{ key: "ratio", label: "Ratio (%)", type: "number" },
]

const { editor, readonly } = useClothSection(props)
const ratios = useClothTable(editor, "yarn_ratio_details", RATIO_FIELDS)
const recipes = useClothTable(editor, "colour_yarn_recipes", RECIPE_FIELDS)
const total = computed(() => ratioTotal(ratios.rows.value))
const totalOk = computed(() => total.value === 100)
const ratioGrid = ref(null)
const recipeGrid = ref(null)

useGridFocus(editor, props.sectionKey, {
	yarn_ratio_details: { grid: ratioGrid, firstRow: () => ratios.keys.value[0]?.key, firstColumn: "ratio" },
	colour_yarn_recipes: { grid: recipeGrid, firstRow: () => recipes.keys.value[0]?.key, firstColumn: "ratio" },
})
</script>
