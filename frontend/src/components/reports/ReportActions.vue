<template>
	<template v-if="visibleItems.length">
		<Button
			type="button"
			icon="pi pi-ellipsis-h"
			severity="secondary"
			outlined
			class="erp-action-button report-actions__trigger"
			aria-label="More report actions"
			title="More actions"
			aria-haspopup="menu"
			:aria-controls="menuId"
			:aria-expanded="open"
			@click="menu?.toggle($event)"
		/>
		<Menu :id="menuId" ref="menu" :model="visibleItems" popup :base-z-index="5000" class="report-actions-menu" @show="open = true" @hide="open = false" />
	</template>
</template>

<script setup>
import Button from "primevue/button"
import Menu from "primevue/menu"
import { computed, ref } from "vue"

/** "⋯" menu holding a report's secondary actions (PrimeVue Menu items: label, icon, disabled, visible, command). */
const props = defineProps({ items: { type: Array, default: () => [] } })
const menuId = `report-actions-${Math.random().toString(36).slice(2, 8)}`
const menu = ref(null)
const open = ref(false)
const visibleItems = computed(() => props.items.filter(item => item && item.visible !== false))
</script>

<style scoped>
.report-actions__trigger {
	flex: 0 0 auto;
	min-width: var(--erp-control-height);
}

:global(.report-actions-menu.p-menu) {
	min-width: 196px;
	padding: 6px;
	font-family: var(--erp-font-family);
	font-size: var(--erp-font-size-caption);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-dialog);
}

:global(.report-actions-menu .p-menu-item-content) {
	border-radius: 7px;
}

:global(.report-actions-menu .p-menu-item-link) {
	gap: 9px;
	padding: 9px 10px;
	color: var(--erp-text);
}

:global(.report-actions-menu .p-menu-item-icon) {
	color: var(--erp-text-muted);
	font-size: 0.82rem;
}

:global(.report-actions-menu .p-menu-item:not(.p-disabled) .p-menu-item-content:hover),
:global(.report-actions-menu .p-menu-item.p-focus .p-menu-item-content) {
	background: var(--erp-accent-soft);
}
</style>
