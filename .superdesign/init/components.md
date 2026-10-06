# Selected reusable components

These are the complete sources of the small, reusable interaction primitives used in the Bright Ledger shell and document workspaces. They preserve their existing props and events.

## frontend/src/components/DepartmentCard.vue

```vue
<template>
	<RouterLink class="department-card-link" :to="department.path">
		<Card class="department-card" :style="{ '--accent': department.accent }">
			<template #content>
				<div class="department-card__layout">
					<span class="department-card__mark" aria-hidden="true">{{ department.shortLabel }}</span>
					<span class="department-card__content">
						<strong>{{ department.label }}</strong>
					</span>
					<i class="pi pi-arrow-right department-card__arrow" aria-hidden="true"></i>
				</div>
			</template>
		</Card>
	</RouterLink>
</template>

<script setup>
import Card from "primevue/card"
import { RouterLink } from "vue-router"

defineProps({
	department: {
		type: Object,
		required: true,
	},
})
</script>
```

## frontend/src/components/common/WorkspaceLauncher.vue

```vue
<template>
	<section
		class="workspace-launcher erp-workspace erp-workspace-entry"
		:aria-labelledby="headingId"
		:aria-busy="loading"
	>
		<header class="erp-page-header workspace-launcher__header">
			<div>
				<p class="erp-page-header__eyebrow">Department workspace</p>
				<h1 :id="headingId">{{ title }}</h1>
			</div>
		</header>

		<div v-if="loading" class="workspace-launcher__grid" aria-label="Loading workspaces">
			<span class="workspace-launcher__loading-status" role="status">Loading workspaces</span>
			<Skeleton v-for="index in skeletonCount" :key="index" height="152px" border-radius="14px" />
		</div>
		<div v-else-if="items.length" class="workspace-launcher__grid">
			<RouterLink
				v-for="item in items"
				:key="item.key"
				class="workspace-launcher__card erp-card"
				:to="item.to"
			>
				<span class="workspace-launcher__icon"><i :class="item.icon" aria-hidden="true" /></span>
				<span class="workspace-launcher__body">
					<strong>{{ item.label }}</strong>
					<small>{{ item.description }}</small>
				</span>
				<i class="pi pi-arrow-right workspace-launcher__arrow" aria-hidden="true" />
			</RouterLink>
		</div>
		<div v-else class="workspace-launcher__empty erp-card">
			<i class="pi pi-lock" aria-hidden="true" />
			<strong>{{ emptyText }}</strong>
		</div>
	</section>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed } from "vue"
import { RouterLink } from "vue-router"

const props = defineProps({
	title: { type: String, required: true },
	items: { type: Array, default: () => [] },
	loading: { type: Boolean, default: false },
	emptyText: { type: String, default: "No permitted workspaces" },
	skeletonCount: { type: Number, default: 4 },
})

const headingId = computed(() => `${props.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-workspace-title`)
</script>

<style scoped>
.workspace-launcher {
	max-width: 1180px;
	margin: 0 auto;
	padding: clamp(24px, 4vw, 48px) 8px;
}

.workspace-launcher__header { margin-bottom: var(--erp-space-6); }

.workspace-launcher__header h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: clamp(1.8rem, 3vw, 2.5rem);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: -0.04em;
}

.workspace-launcher__grid {
	position: relative;
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: var(--erp-space-4);
}

.workspace-launcher__loading-status {
	position: absolute;
	width: 1px;
	height: 1px;
	padding: 0;
	overflow: hidden;
	clip: rect(0, 0, 0, 0);
	white-space: nowrap;
	border: 0;
}

.workspace-launcher__card {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	min-height: 152px;
	padding: 24px;
	align-items: center;
	box-shadow: var(--erp-shadow-xs);
	transition: border-color var(--erp-transition-base), box-shadow var(--erp-transition-base), transform var(--erp-transition-base);
}

.workspace-launcher__card:hover,
.workspace-launcher__card:focus-visible {
	border-color: color-mix(in srgb, var(--erp-accent) 38%, var(--erp-border));
	box-shadow: var(--erp-shadow-md);
	transform: translateY(-3px);
}

.workspace-launcher__card:focus-visible {
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 24%, transparent);
	outline-offset: 2px;
}

.workspace-launcher__card:active { transform: translateY(-1px) scale(0.995); }

.workspace-launcher__icon {
	display: grid;
	width: 52px;
	height: 52px;
	margin-right: 17px;
	color: var(--erp-accent);
	font-size: 1.2rem;
	background: var(--erp-accent-soft);
	border: 1px solid color-mix(in srgb, var(--erp-accent) 16%, var(--erp-border));
	border-radius: var(--erp-panel-radius);
	place-items: center;
}

.workspace-launcher__body {
	display: flex;
	min-width: 0;
	flex-direction: column;
}

.workspace-launcher__body strong {
	color: var(--erp-text);
	font-size: 1.15rem;
	font-weight: var(--erp-font-weight-semibold);
}

.workspace-launcher__body small {
	max-width: 370px;
	margin-top: 7px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	line-height: 1.5;
}

.workspace-launcher__arrow {
	margin-left: 14px;
	color: var(--erp-accent);
	font-size: 1rem;
	transition: transform var(--erp-transition-fast);
}

.workspace-launcher__card:hover .workspace-launcher__arrow,
.workspace-launcher__card:focus-visible .workspace-launcher__arrow {
	transform: translateX(3px);
}

.workspace-launcher__empty {
	display: grid;
	min-height: 140px;
	color: var(--erp-text-muted);
	place-items: center;
	align-content: center;
	gap: 9px;
}

.workspace-launcher__empty i { color: var(--erp-accent); font-size: 1.2rem; }
.workspace-launcher__empty strong { color: var(--erp-text); font-size: var(--erp-font-size-body); }

@media (max-width: 760px) {
	.workspace-launcher { padding: 24px 2px; }
	.workspace-launcher__grid { grid-template-columns: 1fr; }
	.workspace-launcher__card { min-height: 138px; padding: 18px; }
}

@media (min-width: 761px) and (max-width: 1040px) {
	.workspace-launcher__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
```

## frontend/src/components/documents/DocumentActionStrip.vue

```vue
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
```

## frontend/src/components/documents/DocumentConfirmationDialog.vue

```vue
<template>
	<Dialog :visible="visible" modal :header="title" :closable="!busy" :dismissable-mask="false" :style="{ width: 'min(440px, calc(100vw - 24px))' }" @update:visible="emit('update:visible', $event)">
		<div class="document-confirmation-dialog"><i :class="icon" /><p>{{ message }}</p></div>
		<template #footer><Button label="Keep Document" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" /><Button :label="confirmLabel" :icon="confirmIcon" :severity="severity" :loading="busy" @click="emit('confirm')" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"

defineProps({
	visible: { type: Boolean, default: false },
	title: { type: String, default: "Confirm action" },
	message: { type: String, default: "Continue with this action?" },
	confirmLabel: { type: String, default: "Continue" },
	confirmIcon: { type: String, default: "pi pi-check" },
	icon: { type: String, default: "pi pi-exclamation-triangle" },
	severity: { type: String, default: "danger" },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])
</script>

<style scoped>
.document-confirmation-dialog { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 14px; padding: 8px 0 4px; }
.document-confirmation-dialog > i { display: grid; width: 40px; height: 40px; place-items: center; color: var(--erp-warning); border: 1px solid color-mix(in srgb, var(--erp-warning) 24%, white); border-radius: var(--erp-control-radius); background: color-mix(in srgb, var(--erp-warning) 9%, white); }
.document-confirmation-dialog p { margin: 3px 0 0; color: var(--erp-text); font-size: 0.88rem; line-height: 1.55; }
</style>
```
