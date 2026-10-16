<template>
	<section class="workspace-placeholder" aria-live="polite">
		<div class="workspace-placeholder__icon" aria-hidden="true"><i :class="icon"></i></div>
		<p class="workspace-placeholder__eyebrow">Department workspace</p>
		<h1>{{ title }}</h1>
		<p class="workspace-placeholder__message">{{ description }}</p>
	</section>
</template>

<script setup>
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
	width: 46px;
	height: 46px;
	margin-bottom: 3px;
	place-items: center;
	color: var(--erp-accent-ink);
	font-size: var(--erp-font-size-hero);
	background: var(--erp-accent-soft);
	border-radius: 50%;
}
.workspace-placeholder__eyebrow {
	margin: 0;
	color: var(--erp-accent-strong);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: .06em;
	text-transform: uppercase;
}
.workspace-placeholder h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-title);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: -.01em;
}
.workspace-placeholder__message {
	max-width: 470px;
	margin: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-body);
	line-height: 1.55;
}
@media (max-width: 820px) {
	.workspace-placeholder { padding-inline: 0; }
}
@media (max-width: 520px) {
	.workspace-placeholder { min-height: 360px; padding: 28px 0; }
}
</style>
