<template>
	<div v-if="items.length" class="bulk-actions" role="group" aria-label="Bulk LaySheets actions">
		<Button
			class="bulk-actions-trigger"
			label="More Actions"
			icon="pi pi-chevron-down"
			icon-pos="right"
			severity="secondary"
			outlined
			:loading="Boolean(busy)"
			aria-haspopup="menu"
			aria-controls="bulk-laysheets-more-actions"
			:aria-expanded="menuOpen"
			@click="toggle"
		/>
		<Menu
			id="bulk-laysheets-more-actions"
			ref="menu"
			:model="items"
			popup
			:base-z-index="5000"
			class="bulk-actions-menu"
			@show="menuOpen = true"
			@hide="menuOpen = false"
		/>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Menu from "primevue/menu"
import { computed, ref } from "vue"

const props = defineProps({ actions: { type: Object, default: () => ({}) }, busy: { type: String, default: "" } })
const emit = defineEmits(["action"])
const menu = ref(null)
const menuOpen = ref(false)
const items = computed(() => [
	["create-laysheets", "Create LaySheets", "pi pi-plus", "success", false, props.actions.can_create_laysheets],
	["create-bulk-transfer", "Create Bulk Transfer", "pi pi-arrow-right-arrow-left", "secondary", true, props.actions.can_create_bulk_lot_transfer],
	["submit-bulk-transfer", "Submit Bulk Transfer", "pi pi-check", "success", false, props.actions.can_submit_bulk_lot_transfer],
	["create-bulk-dc", "Create Bulk DCs", "pi pi-truck", "secondary", true, props.actions.can_create_bulk_delivery_challans],
].filter((entry) => entry[5]).map(([key, label, icon]) => ({ label, icon, disabled: Boolean(props.busy), command: () => emit("action", key) })))
function toggle(event) { menu.value?.toggle(event) }
</script>

<style scoped>
.bulk-actions { display: flex; align-items: center; min-width: 0; }
.bulk-actions :deep(.bulk-actions-trigger.p-button:focus-visible) { outline: 2px solid color-mix(in srgb, var(--erp-accent) 45%, white); outline-offset: 2px; }
.bulk-actions :deep(.bulk-actions-trigger .p-button-label) { white-space: nowrap; }
:global(.bulk-actions-menu.p-menu) { width: 250px; padding: 6px; font-family: var(--erp-font-family); font-size: var(--erp-font-size-caption); background: var(--erp-surface); border: 1px solid var(--erp-border-strong); border-radius: var(--erp-panel-radius); box-shadow: var(--erp-shadow-dialog); }
:global(.bulk-actions-menu .p-menu-item-content) { border-radius: 7px; }
:global(.bulk-actions-menu .p-menu-item-link) { gap: 9px; padding: 9px 10px; color: var(--erp-text); }
:global(.bulk-actions-menu .p-menu-item-icon) { color: var(--erp-text-muted); font-size: .82rem; }
:global(.bulk-actions-menu .p-menu-item-content:hover) { background: var(--erp-accent-soft); }
</style>
