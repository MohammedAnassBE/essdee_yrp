<template>
	<section ref="reportRoot" class="report-shell erp-card" :aria-label="title" :aria-busy="loading">
		<header v-if="showInlineHeading" class="report-shell__heading">
			<InlinePageNavigation :title-target="headingId" />
			<h1 :id="headingId">{{ title }}</h1>
		</header>
		<form class="report-shell__filters" @submit.prevent="$emit('generate')">
			<div class="report-filter-grid"><slot name="filters" /></div>
			<div class="report-shell__commands erp-command-bar" :class="{ 'report-shell__commands--with-copy': copyable }">
				<Button
					type="submit"
					label="Generate"
					icon="pi pi-play"
					class="erp-action-button erp-action-button--primary"
					:loading="loading"
					:disabled="generateDisabled"
				/>
				<Button
					type="button"
					label="Reset"
					icon="pi pi-refresh"
					severity="secondary"
					outlined
					class="erp-action-button"
					:disabled="loading"
					@click="$emit('reset')"
				/>
				<slot name="actions" />
				<Button
					v-if="copyable"
					type="button"
					:label="copying ? 'Copying' : 'Copy Report'"
					icon="pi pi-copy"
					severity="secondary"
					outlined
					class="erp-action-button report-shell__copy-button"
					:loading="copying"
					:disabled="loading || copying || !generated || !hasResults"
					@click="copyReport"
				/>
			</div>
		</form>
		<div
			v-if="copyNotice"
			class="report-shell__copy-notice"
			:class="{ 'report-shell__copy-notice--error': copyNoticeIsError }"
			role="status"
			aria-live="polite"
		>
			<i :class="copyNoticeIsError ? 'pi pi-exclamation-circle' : 'pi pi-check-circle'" />
			{{ copyNotice }}
		</div>

		<Message v-if="error" severity="error" :closable="false" class="report-shell__message">
			{{ error }}
		</Message>
		<div v-if="$slots.status" class="report-shell__status"><slot name="status" /></div>

		<template v-if="!statusOnly">
			<p v-if="loading && keepResultsWhileLoading && generated" class="report-shell__refreshing" role="status">Refreshing report. Previously generated values remain visible.</p>
			<div v-if="loading && !(keepResultsWhileLoading && generated)" class="report-shell__loading" aria-live="polite">
				<Skeleton width="100%" height="62px" border-radius="10px" />
				<Skeleton width="100%" height="210px" border-radius="10px" />
			</div>
			<div v-else-if="!generated" class="erp-empty-state report-shell__empty">
				<div>
					<i class="pi pi-sliders-h" aria-hidden="true" />
					<strong>Set the report filters</strong>
					<span>No report data is requested until you choose Generate.</span>
				</div>
			</div>
			<div v-else-if="!hasResults" class="erp-empty-state report-shell__empty">
				<div>
					<i class="pi pi-inbox" aria-hidden="true" />
					<strong>{{ emptyTitle }}</strong>
					<span v-if="emptyDescription">{{ emptyDescription }}</span>
				</div>
			</div>
			<div v-else class="report-shell__results">
				<div v-if="$slots.metrics" class="report-metrics"><slot name="metrics" /></div>
				<slot />
			</div>
		</template>
	</section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from "vue"
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"

import { copyElementAsImage } from "./copyElementAsImage.js"
import InlinePageNavigation from "../navigation/InlinePageNavigation.vue"
import { usePageNavigation } from "../navigation/pageNavigationContext.js"

const props = defineProps({
	title: { type: String, required: true },
	generated: { type: Boolean, default: false },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
	hasResults: { type: Boolean, default: false },
	copyable: { type: Boolean, default: false },
	keepResultsWhileLoading: { type: Boolean, default: false },
	generateDisabled: { type: Boolean, default: false },
	statusOnly: { type: Boolean, default: false },
	emptyTitle: { type: String, default: "No matching records" },
	emptyDescription: { type: String, default: "Try a different date, location, item, lot, or status." },
})

const headingId = computed(() => `${props.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-report-title`)
const pageNavigation = usePageNavigation()
const showInlineHeading = computed(() => Boolean(pageNavigation?.inline?.value))

defineEmits(["generate", "reset"])

const reportRoot = ref(null)
const copying = ref(false)
const copyNotice = ref("")
const copyNoticeIsError = ref(false)
let noticeTimer

function showCopyNotice(message, isError = false) {
	copyNotice.value = message
	copyNoticeIsError.value = isError
	window.clearTimeout(noticeTimer)
	noticeTimer = window.setTimeout(() => { copyNotice.value = "" }, 3200)
}

async function copyReport() {
	if (copying.value) return
	copying.value = true
	copyNotice.value = ""
	try {
		await copyElementAsImage(reportRoot.value)
		showCopyNotice("Report copied to clipboard")
	} catch (exception) {
		showCopyNotice(exception?.message || "Could not copy the report.", true)
	} finally {
		copying.value = false
	}
}

onBeforeUnmount(() => window.clearTimeout(noticeTimer))
</script>

<style scoped>
.report-shell {
	min-width: 0;
	overflow: hidden;
}

.report-shell__heading {
	display: flex;
	min-height: 48px;
	align-items: center;
	gap: 10px;
	padding: 5px var(--erp-space-4);
	border-bottom: 1px solid var(--erp-border);
}

.report-shell__heading h1 {
	margin: 0;
	color: var(--erp-text);
	font-size: 18px;
	letter-spacing: -.018em;
}

.report-shell__filters {
	display: flex;
	align-items: flex-end;
	gap: var(--erp-space-3);
	padding: var(--erp-space-3) var(--erp-space-4);
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.report-filter-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
	gap: var(--erp-space-2) var(--erp-space-3);
	min-width: 0;
	flex: 1;
}

.report-filter-grid :deep(label) {
	min-width: 0;
}

.report-filter-grid :deep(select),
.report-filter-grid :deep(.p-inputtext) {
	width: 100%;
	min-height: var(--erp-control-height);
	font-size: 13px;
}

.report-filter-grid :deep(select) {
	padding: 0 10px;
	color: var(--erp-text);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-control-radius);
}

.report-shell__commands {
	flex: 0 0 auto;
	padding-bottom: 1px;
}

.report-shell__copy-button {
	min-width: 108px;
}

.report-shell__copy-notice {
	display: flex;
	align-items: center;
	gap: 6px;
	padding: var(--erp-space-2) var(--erp-space-4);
	color: #087654;
	font-size: var(--erp-font-size-caption);
	font-weight: 750;
	background: #edf9f3;
	border-bottom: 1px solid #d1ebde;
}

.report-shell__copy-notice--error {
	color: #a92f3b;
	background: #fff3f4;
	border-bottom-color: #f2d3d7;
}

.report-shell__message {
	margin: var(--erp-space-3) var(--erp-space-4) 0;
}

.report-shell__status {
	padding: var(--erp-space-4);
}

.report-shell__status:empty {
	display: none;
}

.report-shell__loading {
	display: grid;
	gap: var(--erp-space-3);
	padding: var(--erp-space-5);
}

.report-shell__refreshing {
	margin: 0;
	padding: var(--erp-space-3) var(--erp-space-4) 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.report-shell__empty {
	min-height: 260px;
}

.report-shell__empty div {
	display: grid;
	justify-items: center;
	gap: 7px;
}

.report-shell__empty i {
	color: #8ca39a;
	font-size: 26px;
}

.report-shell__empty strong {
	color: #3c5148;
	font-size: 14px;
}

.report-shell__empty span {
	font-size: var(--erp-font-size-caption);
}

.report-shell__results {
	display: grid;
	gap: var(--erp-space-3);
	padding: var(--erp-space-4) var(--erp-space-4) var(--erp-space-5);
}

.report-metrics {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
	gap: var(--erp-space-2);
}

.report-metrics :deep(.report-metric) {
	display: flex;
	align-items: center;
	gap: var(--erp-space-2);
	min-height: 54px;
	padding: 9px 11px;
	background: var(--erp-surface-soft);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
}

.report-metrics :deep(.report-metric i) {
	color: var(--erp-accent);
	font-size: 15px;
}

.report-metrics :deep(.report-metric span) {
	display: block;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: 0.025em;
	text-transform: uppercase;
}

.report-metrics :deep(.report-metric strong) {
	display: block;
	margin-top: 2px;
	font-size: 15px;
	font-variant-numeric: tabular-nums;
}

.report-shell :deep(.erp-table-wrap),
.report-shell :deep(.production-table-wrap) {
	scrollbar-gutter: stable;
}

@media (max-width: 800px) {
	.report-shell__filters {
		align-items: stretch;
		flex-direction: column;
	}

	.report-filter-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.report-shell__commands {
		width: 100%;
	}

	.report-shell__commands :deep(.p-button) {
		flex: 1;
	}
}

@media (max-width: 360px) {
	.report-filter-grid {
		grid-template-columns: minmax(0, 1fr);
	}

	.report-shell__commands {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.report-shell__commands :deep(.p-button) {
		width: 100%;
		min-width: 0;
		min-height: 44px;
	}

	.report-shell__commands--with-copy :deep(.p-button:first-child) {
		grid-column: 1 / -1;
	}

	.report-shell__copy-button {
		min-width: 0;
	}
}

@media (min-width: 361px) and (max-width: 430px) {
	.report-shell__commands { gap: 6px; }
	.report-shell__commands :deep(.p-button) { padding-inline: 8px; font-size: 12px; }
	.report-shell__commands :deep(.p-button-label) { white-space: nowrap; }
	.report-shell__copy-button { min-width: 0; }
}
</style>
