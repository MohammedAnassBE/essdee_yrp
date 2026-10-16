<template>
	<section class="item-table-card" :class="editable ? 'purchase-form-section' : 'item-table-card--view'">
		<header><h2>{{ label }}</h2><slot name="actions" /></header>
		<div class="item-table-content"><slot /></div>
	</section>
</template>

<script setup>
defineProps({ label: { type: String, required: true }, editable: Boolean })
</script>

<style scoped>
section { display: grid; min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.item-table-content { display: grid; min-width: 0; gap: var(--erp-space-3); padding: 13px; }
.item-table-card--view { gap: 14px; padding: 17px; box-shadow: var(--erp-shadow-xs); }
.item-table-card--view > header { padding: 0; border: 0; background: transparent; }
.item-table-card--view > header h2 { margin: 2px 0 0; }
.item-table-card--view > .item-table-content { padding: 0; }
.item-table-content :deep(.item-table-hint) { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.item-table-content :deep(.item-row-problem) { display: block; color: var(--erp-danger-text, #b91c1c); font-size: var(--erp-font-size-caption); }
@media (max-width: 620px) { .item-table-card--view { padding: var(--erp-space-3); } }
</style>
