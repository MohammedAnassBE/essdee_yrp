<template>
	<div v-if="actions.length" class="document-action-strip" role="group" aria-label="Available document actions">
		<Button
			v-if="primaryAction"
			class="document-action-strip__primary"
			:label="primaryAction.label"
			:icon="primaryAction.icon"
			:loading="Boolean(primaryAction.loading)"
			:disabled="Boolean(primaryAction.disabled)"
			:title="primaryAction.disabledReason || primaryAction.label"
			@click="run(primaryAction)"
		/>
		<Button
			v-for="(action, index) in visibleActions"
			:key="action.key"
			class="document-action-strip__secondary"
			:class="`document-action-strip__secondary--${index + 1}`"
			:label="action.label"
			:icon="action.icon"
			severity="secondary"
			text
			:loading="Boolean(action.loading)"
			:disabled="Boolean(action.disabled)"
			:title="action.disabledReason || action.label"
			@click="run(action)"
		/>
		<Button
			v-if="overflowActions.length"
			class="document-action-strip__more"
			label="More"
			icon="pi pi-ellipsis-v"
			severity="secondary"
			text
			aria-haspopup="menu"
			:aria-expanded="menuOpen"
			@click="toggleMenu"
		/>
		<Menu
			ref="menu"
			:model="menuItems"
			popup
			:base-z-index="5000"
			class="document-action-menu"
			@show="menuOpen = true"
			@hide="menuOpen = false"
		/>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Menu from "primevue/menu"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

const props = defineProps({
	actions: { type: Array, default: () => [] },
})

const menu = ref(null)
const menuOpen = ref(false)
const compact = ref(false)
let compactQuery
const primaryAction = computed(() => props.actions.find((action) => action.primary) || null)
const secondaryActions = computed(() => props.actions.filter((action) => action !== primaryAction.value))
const visibleActions = computed(() => secondaryActions.value.filter((action) => !action.menuOnly).slice(0, 2))
const visibleActionKeys = computed(() => new Set(visibleActions.value.map((action) => action.key)))
const overflowActions = computed(() => compact.value
	? secondaryActions.value
	: secondaryActions.value.filter((action) => action.menuOnly || !visibleActionKeys.value.has(action.key)))
const menuItems = computed(() => overflowActions.value.map((action) => ({
	label: action.label,
	icon: action.icon,
	disabled: Boolean(action.disabled),
	command: () => run(action),
})))

function run(action) {
	if (!action || action.disabled || action.loading) return
	action.command?.()
}

function toggleMenu(event) {
	menu.value?.toggle(event)
}

function updateCompact(event) { compact.value = event.matches }
onMounted(() => {
	compactQuery = window.matchMedia("(max-width: 899px)")
	compact.value = compactQuery.matches
	compactQuery.addEventListener("change", updateCompact)
})
onBeforeUnmount(() => compactQuery?.removeEventListener("change", updateCompact))
</script>

<style scoped>
.document-action-strip { display: flex; min-width: 0; align-items: center; gap: 4px; flex-wrap: nowrap; }
.document-action-strip :deep(.p-button) { min-height: var(--erp-control-height); flex: 0 0 auto; white-space: nowrap; border-radius: var(--erp-control-radius); }
.document-action-strip :deep(.p-button:not(:disabled):active) { transform: translateY(1px); }
.document-action-strip :deep(.p-button:focus-visible) { outline: 3px solid color-mix(in srgb, var(--erp-accent) 16%, transparent); outline-offset: 1px; }
.document-action-strip__primary { margin-right: 2px; box-shadow: 0 3px 10px color-mix(in srgb, var(--erp-accent) 18%, transparent); }
.document-action-strip__secondary :deep(.p-button-label),
.document-action-strip__more :deep(.p-button-label) { font-weight: 650; }
@media (max-width: 899px) { .document-action-strip__secondary { display: none; } }
@media (max-width: 620px) { .document-action-strip { width: 100%; } .document-action-strip__primary { min-width: 0; flex: 1 1 auto !important; } .document-action-strip__more { flex: 0 0 auto; } }
</style>
