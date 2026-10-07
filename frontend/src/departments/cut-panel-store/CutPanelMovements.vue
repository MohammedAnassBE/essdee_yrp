<template>
	<div class="cut-panel-movements">
		<ListView
			ref="listView"
			doctype="SD YRP Cut Panel Movement"
			title="Cut Panel Movements"
			search-placeholder="Search Cut Panel Movements…"
			name-column-label="Movement"
			row-mark="CPM"
			min-table-width="1080px"
			:default-columns="defaultColumns"
			:column-labels="columnLabels"
			viewport-bounded
			clickable
			@row-click="openMovement"
		>
			<template #toolbar-actions><Button v-if="capability.can_create" label="Create Movement" icon="pi pi-plus" @click="createMovement" /></template>
		</ListView>
		<CutPanelMovementDialog v-model:visible="dialogVisible" :movement="selectedMovement" @changed="movementChanged" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { ref } from "vue"

import ListView from "../../components/common/ListView.vue"
import CutPanelMovementDialog from "./CutPanelMovementDialog.vue"

defineProps({ capability: { type: Object, required: true } })
const listView = ref(null)
const dialogVisible = ref(false)
const selectedMovement = ref("")
const defaultColumns = ["lot", "item", "from_warehouse", "against", "against_id", "movement_date"]
const columnLabels = { from_warehouse: "From Warehouse" }

function createMovement() { selectedMovement.value = ""; dialogVisible.value = true }
function openMovement(row) { if (!row?.name) return; selectedMovement.value = row.name; dialogVisible.value = true }
async function movementChanged() { await listView.value?.refresh?.() }
</script>

<style scoped>
.cut-panel-movements{min-width:0}
</style>
