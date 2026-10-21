<template>
	<section
		class="workspace-launcher erp-workspace erp-workspace-entry"
		:class="{ 'workspace-launcher--compact': compact }"
		:aria-labelledby="headingId"
		:aria-busy="loading"
	>
		<header class="erp-page-header workspace-launcher__header">
			<slot name="navigation">
				<InlinePageNavigation :title-target="headingId" />
			</slot>
			<div class="workspace-launcher__title">
				<p v-if="eyebrow" class="erp-page-header__eyebrow">{{ eyebrow }}</p>
				<h1 :id="headingId">{{ title }}</h1>
			</div>
			<div v-if="$slots.context" class="workspace-launcher__context"><slot name="context" /></div>
		</header>

		<div v-if="loading" class="workspace-launcher__grid" aria-label="Loading workspaces">
			<span class="workspace-launcher__loading-status" role="status">Loading workspaces</span>
			<div v-for="index in skeletonCount" :key="index" class="workspace-launcher__skeleton">
				<Skeleton height="124px" border-radius="14px" />
			</div>
		</div>
		<div v-else-if="visibleItems.length" class="workspace-launcher__grid">
			<RouterLink
				v-for="item in visibleItems"
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
import { isWorkspaceInLayout } from "../../router/departmentLock.js"
import { canOpenList } from "../../router/listPermission.js"
import InlinePageNavigation from "../navigation/InlinePageNavigation.vue"

const props = defineProps({
	title: { type: String, required: true },
	items: { type: Array, default: () => [] },
	loading: { type: Boolean, default: false },
	emptyText: { type: String, default: "No permitted workspaces" },
	skeletonCount: { type: Number, default: 4 },
	compact: { type: Boolean, default: false },
	eyebrow: { type: String, default: "Department workspace" },
})

const visibleItems = computed(() => props.items.filter((item) => isWorkspaceInLayout(item) && canOpenList(item.to)))
const headingId = computed(() => `${props.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-workspace-title`)
</script>

<style scoped>
.workspace-launcher.erp-workspace.erp-workspace-entry {
	box-sizing: border-box;
	width: 100%;
	max-width: calc(var(--erp-workspace-max-width) + 2 * var(--erp-page-gutter));
	margin-inline: auto;
	padding: 22px var(--erp-page-gutter) 60px;
}

.workspace-launcher__title {
	min-width: 0;
}

.workspace-launcher__context {
	width: min(380px, 40%);
	margin-left: auto;
}

.workspace-launcher__grid {
	position: relative;
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: var(--erp-density-gap);
}

.workspace-launcher__skeleton {
	overflow: hidden;
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface-muted);
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
	min-width: 0;
	min-height: 110px;
	padding: 16px 18px;
	align-items: center;
	transition: box-shadow var(--erp-transition-card), transform var(--erp-transition-card);
}

.workspace-launcher__card:focus-visible {
	outline: 2px solid var(--erp-accent);
	outline-offset: 2px;
}

.workspace-launcher__icon {
	display: grid;
	width: 36px;
	height: 36px;
	margin-right: var(--erp-space-3);
	color: var(--erp-accent-ink);
	font-size: var(--erp-font-size-section);
	background: var(--erp-accent-soft);
	border-radius: 8px;
	place-items: center;
}

.workspace-launcher__body {
	display: flex;
	min-width: 0;
	flex-direction: column;
	justify-content: center;
	overflow-wrap: anywhere;
}

.workspace-launcher__body strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-body);
	font-weight: var(--erp-font-weight-semibold);
}

.workspace-launcher__body small {
	display: -webkit-box;
	overflow: hidden;
	-webkit-box-orient: vertical;
	-webkit-line-clamp: 2;
	margin-top: var(--erp-space-1);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	line-height: var(--erp-line-height-body);
}

.workspace-launcher__arrow {
	margin-left: var(--erp-space-2);
	color: var(--erp-text-subtle);
	font-size: var(--erp-font-size-body);
	transition: color var(--erp-transition-fast), transform var(--erp-transition-fast);
}

@media (hover: hover) and (prefers-reduced-motion: no-preference) {
	.workspace-launcher__card:hover {
		box-shadow: var(--erp-shadow-pop);
		transform: translateY(-1px);
	}
	.workspace-launcher__card:hover .workspace-launcher__arrow {
		color: var(--erp-accent);
		transform: translateX(2px);
	}
}

.workspace-launcher__empty {
	display: grid;
	min-height: 140px;
	color: var(--erp-text-muted);
	place-items: center;
	align-content: center;
	gap: var(--erp-space-2);
}

.workspace-launcher__empty i {
	color: var(--erp-accent-ink);
	font-size: var(--erp-font-size-hero);
}

.workspace-launcher__empty strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-body);
}

@media (max-width: 760px) {
	.workspace-launcher--compact .workspace-launcher__header {
		flex-wrap: wrap;
	}
	.workspace-launcher--compact .workspace-launcher__context {
		width: 100%;
		padding-left: 46px;
	}
}

@media (max-width: 1024px) {
	.workspace-launcher__grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}

@media (max-width: 820px) {
	.workspace-launcher__card {
		padding: var(--erp-space-3);
	}
}

@media (max-width: 540px) {
	.workspace-launcher__grid {
		grid-template-columns: 1fr;
	}
	.workspace-launcher__card {
		min-height: 0;
		padding: 12px 14px;
	}
	.workspace-launcher__icon {
		width: 32px;
		height: 32px;
	}
}
</style>
