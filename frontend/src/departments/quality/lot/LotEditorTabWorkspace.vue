<template>
	<div class="lot-tab-stack">
		<Message v-if="error" severity="error" :closable="false">{{ error }} <Button label="Retry" severity="secondary" text size="small" @click="emit('retry')" /></Message>
		<LotEmptyState v-else-if="loading || !workspace" title="Loading…" :reason="`Loading the saved ${tabLabel}.`" />
		<template v-else>
			<Message severity="secondary" :closable="false">Read only while editing. Changes here need the saved Lot page.</Message>
			<LotBomPanel v-if="tab === 'bom'" :workspace="workspace" />
			<LotDiaConversionsTab v-else-if="tab === 'dia-conversions'" :fabrics="workspace.fabrics || []" :other-conversions="workspace.other_conversions || []" />
			<LotFabricTab v-else :fabrics="workspace.fabrics || []" />
		</template>
	</div>
</template>
<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import LotBomPanel from "./LotBomPanel.vue"
import LotEmptyState from "./LotEmptyState.vue"
import LotFabricTab from "./LotFabricTab.vue"
import LotDiaConversionsTab from "./LotDiaConversionsTab.vue"
import { LOT_TABS } from "./lotLayout.js"
import { computed } from "vue"
/** Read-only Cloth Program, Actual Dia Conversions or BOM of the saved Lot, shown inside the editor. */
const props = defineProps({ tab: { type: String, required: true }, workspace: { type: Object, default: null }, loading: Boolean, error: { type: String, default: "" } })
const emit = defineEmits(["retry"])
const tabLabel = computed(() => LOT_TABS.find((entry) => entry.key === props.tab)?.label || "Lot")
</script>
