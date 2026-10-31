<template>
	<div class="lot-tab-stack">
		<Message v-if="error" severity="error" :closable="false">{{ error }} <Button label="Retry" severity="secondary" text size="small" @click="emit('retry')" /></Message>
		<LotEmptyState v-else-if="loading || !workspace" title="Loading…" :reason="`Loading the saved ${tab === 'bom' ? 'BOM' : 'Cloth Program'}.`" />
		<template v-else>
			<Message severity="secondary" :closable="false">Read only while editing. Changes here need the saved Lot page.</Message>
			<LotBomPanel v-if="tab === 'bom'" :workspace="workspace" />
			<LotFabricTab v-else :fabrics="workspace.fabrics || []" :other-conversions="workspace.other_conversions || []" />
		</template>
	</div>
</template>
<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import LotBomPanel from "./LotBomPanel.vue"
import LotEmptyState from "./LotEmptyState.vue"
import LotFabricTab from "./LotFabricTab.vue"
/** Read-only Cloth Program or BOM of the saved Lot, shown inside the editor. */
defineProps({ tab: { type: String, required: true }, workspace: { type: Object, default: null }, loading: Boolean, error: { type: String, default: "" } })
const emit = defineEmits(["retry"])
</script>
