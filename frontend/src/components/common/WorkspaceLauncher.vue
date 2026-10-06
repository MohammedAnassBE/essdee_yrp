<template>
	<section class="workspace-launcher erp-workspace erp-workspace-entry" :aria-labelledby="headingId">
		<header class="erp-page-header workspace-launcher__header">
			<h1 :id="headingId">{{ title }}</h1>
		</header>

		<div v-if="loading" class="workspace-launcher__grid" aria-label="Loading workspaces">
			<Skeleton v-for="index in skeletonCount" :key="index" height="144px" border-radius="12px" />
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
	max-width: 1120px;
	margin: 0 auto;
	padding: 24px 8px;
}

.workspace-launcher__header h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: clamp(1.7rem, 2vw, 2rem);
	font-weight: 780;
	letter-spacing: -0.035em;
}

.workspace-launcher__grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 16px;
}

.workspace-launcher__card {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	min-height: 144px;
	padding: 22px;
	align-items: center;
	transition: border-color var(--erp-transition-fast), box-shadow var(--erp-transition-fast), transform var(--erp-transition-fast);
}

.workspace-launcher__card:hover,
.workspace-launcher__card:focus-visible {
	border-color: color-mix(in srgb, var(--erp-accent) 38%, var(--erp-border));
	box-shadow: 0 14px 34px rgb(30 64 48 / 11%);
	transform: translateY(-2px);
}

.workspace-launcher__card:active { transform: translateY(0); }

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
	font-weight: 720;
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
	.workspace-launcher { padding: 16px 2px; }
	.workspace-launcher__grid { grid-template-columns: 1fr; }
	.workspace-launcher__card { min-height: 138px; padding: 18px; }
}

@media (min-width: 761px) and (max-width: 1040px) {
	.workspace-launcher__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
