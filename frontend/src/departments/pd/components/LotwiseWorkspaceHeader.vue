<template>
	<header class="lotwise-workspace__header">
		<div class="lotwise-workspace__identity">
			<span>Lotwise Item Profit · {{ name || "New" }}</span>
			<h1>{{ title }}</h1>
		</div>
		<div class="lotwise-workspace__header-actions">
			<DocumentActionStrip :actions="actions" />
			<DocumentSaveButton v-if="canEdit" :loading="saving" :disabled="busy" @save="emit('save')" />
		</div>
	</header>
</template>

<script setup>
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentSaveButton from "../../../components/documents/DocumentSaveButton.vue"

defineProps({
	name: { type: String, default: "" },
	title: { type: String, required: true },
	actions: { type: Array, required: true },
	canEdit: { type: Boolean, default: false },
	saving: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["save"])
</script>

<style scoped>
.lotwise-workspace__header { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: var(--erp-space-3) var(--erp-space-4); border-bottom: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-sm); }
.lotwise-workspace__identity { display: grid; min-width: 0; gap: 3px; }
.lotwise-workspace__identity span { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.04em; text-overflow: ellipsis; text-transform: uppercase; white-space: nowrap; }
.lotwise-workspace__identity h1 { margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-title); font-weight: 780; letter-spacing: -0.025em; text-overflow: ellipsis; white-space: nowrap; }
.lotwise-workspace__header-actions { display: flex; align-items: end; gap: 8px; flex-wrap: wrap; }
@media (max-width: 620px) { .lotwise-workspace__header { align-items: stretch; flex-direction: column; padding: var(--erp-space-3); } .lotwise-workspace__header-actions { align-items: stretch; flex-direction: column; } .lotwise-workspace__header-actions > * { width: 100%; } }
</style>
