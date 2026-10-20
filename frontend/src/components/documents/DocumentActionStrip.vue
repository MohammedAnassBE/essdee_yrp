<template>
	<div v-if="actions.length" class="document-action-strip" :class="{ 'document-action-strip--with-reason': reasonNotice }" role="group" aria-label="Available document actions">
		<Button
			v-if="primaryAction"
			class="document-action-strip__primary"
			:label="primaryAction.label"
			:icon="primaryAction.icon"
			:severity="primaryAction.severity"
			:loading="Boolean(primaryAction.loading)"
			:disabled="nativeDisabled(primaryAction)"
			:aria-disabled="Boolean(primaryAction.disabled)"
			:aria-label="actionAriaLabel(primaryAction)"
			:aria-describedby="disabledReasonId(primaryAction)"
			:class="{ 'document-action-strip__reason-disabled': primaryAction.disabled && primaryAction.disabledReason }"
			:title="primaryAction.disabledReason || primaryAction.label"
			@focus="showDisabledReason(primaryAction)"
			@click="run(primaryAction)"
		/>
		<Button
			v-for="(action, index) in visibleActions"
			:key="action.key"
			class="document-action-strip__secondary"
			:class="[`document-action-strip__secondary--${index + 1}`, { 'document-action-strip__reason-disabled': action.disabled && action.disabledReason }]"
			:label="action.label"
			:icon="action.icon"
			:severity="action.severity || 'secondary'"
			text
			:loading="Boolean(action.loading)"
			:disabled="nativeDisabled(action)"
			:aria-disabled="Boolean(action.disabled)"
			:aria-label="actionAriaLabel(action)"
			:aria-describedby="disabledReasonId(action)"
			:title="action.disabledReason || action.label"
			@focus="showDisabledReason(action)"
			@click="run(action)"
		/>
		<Button
			v-if="desktopOverflowActions.length"
			class="document-action-strip__more document-action-strip__more--desktop"
			label="More"
			icon="pi pi-ellipsis-v"
			severity="secondary"
			text
			aria-haspopup="menu"
			:aria-expanded="menuOpen"
			@focus="clearDisabledReason"
			@click="toggleMenu($event, desktopOverflowActions)"
		/>
		<Button
			v-if="secondaryActions.length"
			class="document-action-strip__more document-action-strip__more--mobile"
			label="More"
			icon="pi pi-ellipsis-v"
			severity="secondary"
			text
			aria-haspopup="menu"
			:aria-expanded="menuOpen"
			@focus="clearDisabledReason"
			@click="toggleMenu($event, secondaryActions)"
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
		<span v-if="reasonNotice" id="document-action-disabled-reason" class="document-action-strip__reason" role="status">{{ reasonNotice }}</span>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Menu from "primevue/menu"
import { computed, ref } from "vue"

const props = defineProps({
	actions: { type: Array, default: () => [] },
})

const menu = ref(null)
const menuOpen = ref(false)
const activeOverflowActions = ref([])
const reasonNotice = ref("")
const primaryAction = computed(() => props.actions.find((action) => action.primary) || null)
const secondaryActions = computed(() => props.actions.filter((action) => action !== primaryAction.value))
const visibleActions = computed(() => secondaryActions.value.filter((action) => !action.menuOnly).slice(0, 2))
const visibleActionKeys = computed(() => new Set(visibleActions.value.map((action) => action.key)))
const desktopOverflowActions = computed(() => secondaryActions.value.filter((action) => action.menuOnly || !visibleActionKeys.value.has(action.key)))
const menuItems = computed(() => activeOverflowActions.value.map((action) => ({
	label: action.disabled && action.disabledReason ? `${action.label} — ${action.disabledReason}` : action.label,
	icon: action.icon,
	class: action.severity === "danger" ? "document-action-menu__item--danger" : undefined,
	disabled: Boolean(action.disabled),
	command: () => run(action),
})))

function run(action) {
	if (!action) return
	if (action.disabled || action.loading) { showDisabledReason(action); return }
	clearDisabledReason()
	action.command?.()
}

function nativeDisabled(action) { return Boolean(action?.disabled && !action?.disabledReason) }
function actionAriaLabel(action) { return action?.disabledReason ? `${action.label}. Unavailable: ${action.disabledReason}` : action?.label }
function disabledReasonId(action) { return action?.disabled && action?.disabledReason ? "document-action-disabled-reason" : undefined }
function showDisabledReason(action) { reasonNotice.value = action?.disabled && action?.disabledReason ? action.disabledReason : "" }
function clearDisabledReason() { reasonNotice.value = "" }

function toggleMenu(event, actions) {
	activeOverflowActions.value = actions
	menu.value?.toggle(event)
}
</script>

<style scoped>
.document-action-strip { position: relative; display: flex; min-width: 0; align-items: center; gap: 4px; flex-wrap: nowrap; }
.document-action-strip :deep(.p-button) { min-height: var(--erp-control-height); flex: 0 0 auto; white-space: nowrap; border-radius: var(--erp-control-radius); }
.document-action-strip__primary {
	margin-right: 2px;
}
.document-action-strip__secondary :deep(.p-button-label),
.document-action-strip__more :deep(.p-button-label) {
	font-weight: var(--erp-font-weight-semibold);
}
.document-action-strip__more--mobile { display: none; }
.document-action-strip__reason {
	position: absolute;
	z-index: var(--erp-layer-dropdown);
	top: calc(100% + 7px);
	left: 0;
	width: max-content;
	max-width: min(360px, 82vw);
	padding: 7px 10px;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	line-height: 1.35;
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-md);
}
@media (max-width: 899px) { .document-action-strip__secondary, .document-action-strip__more--desktop { display: none; } .document-action-strip__more--mobile { display: inline-flex; } }
@media (max-width: 620px) { .document-action-strip { width: 100%; } .document-action-strip--with-reason { flex-wrap: wrap; } .document-action-strip__primary { min-width: 0; flex: 1 1 auto !important; } .document-action-strip__more { flex: 0 0 auto; } .document-action-strip__reason { position: static; width: 100%; max-width: none; flex: 1 0 100%; box-shadow: none; } }
</style>

<style>
.document-action-menu .document-action-menu__item--danger .p-menu-item-icon,
.document-action-menu .document-action-menu__item--danger .p-menu-item-label { color: var(--erp-danger); }
</style>
