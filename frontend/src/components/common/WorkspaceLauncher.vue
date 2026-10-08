<template>
	<section
		class="workspace-launcher erp-workspace erp-workspace-entry"
		:aria-labelledby="headingId"
		:aria-busy="loading"
	>
		<header class="erp-page-header workspace-launcher__header">
			<InlinePageNavigation :title-target="headingId" />
			<div class="workspace-launcher__title">
				<p class="erp-page-header__eyebrow">Department workspace</p>
				<h1 :id="headingId">{{ title }}</h1>
			</div>
		</header>

		<div v-if="loading" class="workspace-launcher__grid" aria-label="Loading workspaces">
			<span class="workspace-launcher__loading-status" role="status">Loading workspaces</span>
			<Skeleton v-for="index in skeletonCount" :key="index" height="124px" border-radius="14px" />
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
import InlinePageNavigation from "../navigation/InlinePageNavigation.vue"

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
	max-width: 1320px;
	margin: 0 auto;
	padding: clamp(24px, 4vw, 48px) 8px;
}

.workspace-launcher__header { display: flex; align-items: center; gap: 10px; margin-bottom: var(--erp-space-6); }
.workspace-launcher__title { min-width: 0; }

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
	min-height: 124px;
	padding: 20px;
	align-items: center;
	box-shadow: var(--erp-shadow-xs);
	transition: border-color var(--erp-transition-base), box-shadow var(--erp-transition-base), transform var(--erp-transition-base);
}

.workspace-launcher__card:focus-visible {
	border-color: color-mix(in srgb, var(--erp-accent) 38%, var(--erp-border));
	box-shadow: var(--erp-shadow-md);
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 24%, transparent);
	outline-offset: 2px;
}

.workspace-launcher__card:active { transform: translateY(-1px) scale(0.995); }

.workspace-launcher__icon {
	display: grid;
	width: 44px;
	height: 44px;
	margin-right: 15px;
	color: var(--erp-accent);
	font-size: 1.2rem;
	background: var(--erp-accent-soft);
	border: 1px solid color-mix(in srgb, var(--erp-accent) 16%, var(--erp-border));
	border-radius: var(--erp-panel-radius);
	place-items: center;
}

.workspace-launcher__body {
	display: flex;
	min-height: 69px;
	min-width: 0;
	flex-direction: column;
	justify-content: center;
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

.workspace-launcher__card:focus-visible .workspace-launcher__arrow {
	transform: translateX(3px);
}

@media (hover: hover) {
	.workspace-launcher__card:hover {
		border-color: color-mix(in srgb, var(--erp-accent) 38%, var(--erp-border));
		box-shadow: var(--erp-shadow-md);
		transform: translateY(-2px);
	}

	.workspace-launcher__card:hover .workspace-launcher__arrow {
		transform: translateX(3px);
	}
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
	.workspace-launcher__card { min-height: 108px; padding: 14px; }
	.workspace-launcher__body small {
		display: -webkit-box;
		overflow: hidden;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
	}
}

@media (max-width: 600px) {
	.workspace-launcher__header { margin-bottom: var(--erp-space-4); }
	.workspace-launcher__grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
	}
	.workspace-launcher__card {
		grid-template-columns: minmax(0, 1fr) auto;
		grid-template-rows: auto 1fr;
		min-height: 104px;
		padding: 12px;
		align-items: start;
		row-gap: 8px;
	}
	.workspace-launcher__icon {
		margin-right: 0;
	}
	.workspace-launcher__body {
		grid-column: 1 / -1;
		grid-row: 2;
		min-height: 0;
		align-self: end;
		justify-content: flex-end;
	}
	.workspace-launcher__body strong {
		font-size: 14px;
		line-height: 1.25;
	}
	.workspace-launcher__body small { display: none; }
	.workspace-launcher__arrow {
		grid-column: 2;
		grid-row: 1;
		align-self: center;
		margin-left: 0;
	}
}

@media (min-width: 761px) and (max-width: 1040px) {
	.workspace-launcher__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
