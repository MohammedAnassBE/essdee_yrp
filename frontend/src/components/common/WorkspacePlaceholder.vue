<template>
	<section class="workspace-placeholder" aria-live="polite">
		<div class="workspace-placeholder__icon" aria-hidden="true"><i :class="icon"></i></div>
		<p class="workspace-placeholder__eyebrow">Department workspace</p>
		<h1>{{ title }}</h1>
		<p class="workspace-placeholder__message">{{ description }}</p>
		<div class="workspace-placeholder__status"><span></span>Connected to Essdee YRP</div>
		<RouterLink v-slot="{ navigate }" custom to="/">
			<Button label="All workspaces" icon="pi pi-th-large" severity="secondary" outlined @click="navigate" />
		</RouterLink>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { RouterLink } from "vue-router"

defineProps({
	title: { type: String, required: true },
	description: {
		type: String,
		default: "No tools are available in this workspace yet. Department tools will appear here when they are enabled.",
	},
	icon: { type: String, default: "pi pi-briefcase" },
})
</script>

<style scoped>
.workspace-placeholder {
	display: grid;
	width: 100%;
	max-width: 680px;
	min-height: min(420px, calc(100dvh - var(--erp-shell-header-height) - 150px));
	margin: 0 auto;
	padding: 36px 24px;
	place-content: center;
	justify-items: center;
	gap: 9px;
	text-align: center;
}
.workspace-placeholder__icon {
	display: grid;
	width: 52px;
	height: 52px;
	margin-bottom: 3px;
	place-items: center;
	color: var(--erp-accent);
	font-size: 1.2rem;
	background: var(--erp-accent-soft);
	border: 1px solid var(--erp-accent-border);
	border-radius: 14px;
}
.workspace-placeholder__eyebrow {
	margin: 0;
	color: var(--erp-accent-strong);
	font-size: var(--erp-font-size-min);
	font-weight: 780;
	letter-spacing: .09em;
	text-transform: uppercase;
}
.workspace-placeholder h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: clamp(1.6rem, 3vw, 2.15rem);
	font-weight: 780;
	letter-spacing: -.035em;
}
.workspace-placeholder__message {
	max-width: 470px;
	margin: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-body);
	line-height: 1.55;
}
.workspace-placeholder__status {
	display: inline-flex;
	min-height: 30px;
	margin: 5px 0 7px;
	padding: 5px 10px;
	align-items: center;
	gap: 7px;
	color: var(--erp-text-subtle);
	font-size: var(--erp-font-size-caption);
	font-weight: 650;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: 999px;
}
.workspace-placeholder__status span {
	width: 7px;
	height: 7px;
	background: var(--erp-accent);
	border-radius: 50%;
	box-shadow: 0 0 0 3px var(--erp-accent-soft);
}
@media (max-width: 520px) {
	.workspace-placeholder { min-height: 360px; padding: 28px 16px; }
	.workspace-placeholder :deep(.p-button) { min-height: 44px; }
}
</style>
