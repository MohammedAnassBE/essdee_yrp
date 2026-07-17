<!-- PreviewBanner — the §10 persistent preview strip (non-negotiable).

     Fixed bottom strip mounted by AppLayout in BOTH shells; renders only while
     store.previewing (SM-only path — no one else can enter preview, so parity
     holds: outside preview this renders nothing). Shows WHO/WHAT is being
     previewed, an honest fidelity note, resolver warnings when the previewed
     config carried any (preview is diagnostic — warned layouts render anyway),
     and two actions:
       Reload — re-calls get_ui_config_for for the same target (the sit-down
                iteration button: edit the layout JSON in Desk, click Reload,
                see the change in seconds; no page reload).
       Exit   — store.exitPreview() restores the stashed real config in memory,
                no page reload; the theme watch re-applies the SM's own theme.
     Deliberately NO Escape handler and no auto-dismiss: leaving preview is an
     explicit click only (a full page reload also naturally exits — the state
     is memory-only). -->
<template>
	<div v-if="ui.previewing" class="preview-banner" role="status">
		<i class="pi pi-eye banner-eye" aria-hidden="true" />
		<span class="banner-text">
			<template v-if="ui.previewLayout">
				Previewing layout <strong>{{ ui.previewLayout }}</strong>
			</template>
			<template v-else>
				Previewing UI as <strong>{{ ui.previewUser }}</strong>
			</template>
			<span
				class="banner-sub"
				title="Appearance, navigation and permission-gating are previewed. Data, drafts, queue counts and actions still run under YOUR session — true row-level fidelity needs the user's own login."
			>— appearance only. Data &amp; permissions are still yours.</span>
		</span>
		<span
			v-if="warnings.length"
			class="banner-warn"
			:title="warnings.join('\n')"
		>
			<i class="pi pi-exclamation-triangle" />
			{{ warnings.length }} warning{{ warnings.length > 1 ? "s" : "" }}
		</span>
		<span class="banner-actions">
			<button class="banner-btn" type="button" :disabled="busy" @click="reload">
				<i class="pi pi-refresh" :class="{ 'pi-spin': busy }" /> Reload
			</button>
			<button class="banner-btn banner-btn--exit" type="button" @click="exit">
				<i class="pi pi-times" /> Exit preview
			</button>
		</span>
	</div>
</template>

<script setup>
import { ref, computed } from "vue"
import { useToast } from "primevue/usetoast"
import { useUiConfigStore } from "@yrp/web-engine"

const ui = useUiConfigStore()
const toast = useToast()
const busy = ref(false)

const warnings = computed(() => ui.meta?.warnings || [])

async function reload() {
	if (busy.value) return
	const target = ui.previewLayout
		? { layout: ui.previewLayout }
		: { user: ui.previewUser }
	busy.value = true
	try {
		await ui.previewAs(target)
	} catch (err) {
		// Target vanished/disabled mid-preview: keep the current preview, tell the SM.
		toast.add({
			severity: "error",
			summary: "Preview reload failed",
			detail: err?.message || "Could not re-fetch the preview config",
			life: 6000,
		})
	} finally {
		busy.value = false
	}
}

function exit() {
	ui.exitPreview()
}
</script>

<style scoped>
.preview-banner {
	position: fixed;
	left: 50%;
	transform: translateX(-50%);
	bottom: 14px;
	z-index: 1000; /* above content + knobs FAB; below PrimeVue dialogs (1100+) */
	display: flex;
	align-items: center;
	gap: 10px;
	max-width: min(94vw, 780px);
	padding: 8px 14px;
	border-radius: 999px;
	/* Fixed dark pill on purpose: --esd-ink inverts to near-white in dark mode
	   (see AppTopbar's avatar note), which would hide the white text. A constant
	   dark surface reads correctly over BOTH light and dark themes. */
	background: #16222e;
	color: #fff;
	font-size: 12.5px;
	box-shadow: 0 6px 24px rgb(0 0 0 / 0.28);
	border: 1px solid rgb(255 255 255 / 0.14);
}
.banner-eye {
	font-size: 13px;
	color: #7dd3fc;
	flex: none;
}
.banner-text {
	min-width: 0;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}
.banner-text strong {
	font-weight: 750;
}
.banner-sub {
	color: rgb(255 255 255 / 0.72);
	margin-left: 4px;
}
.banner-warn {
	flex: none;
	display: inline-flex;
	align-items: center;
	gap: 5px;
	font-weight: 700;
	color: #fbbf24;
	cursor: help;
}
.banner-warn .pi {
	font-size: 12px;
}
.banner-actions {
	flex: none;
	display: inline-flex;
	gap: 6px;
	margin-left: 4px;
}
.banner-btn {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	background: rgb(255 255 255 / 0.12);
	border: 1px solid rgb(255 255 255 / 0.22);
	color: #fff;
	border-radius: 999px;
	padding: 4px 11px;
	font-size: 12px;
	font-weight: 650;
	font-family: inherit;
	cursor: pointer;
	white-space: nowrap;
}
.banner-btn:hover {
	background: rgb(255 255 255 / 0.2);
}
.banner-btn:disabled {
	opacity: 0.6;
	cursor: default;
}
.banner-btn .pi {
	font-size: 11px;
}
.banner-btn--exit {
	background: #fff;
	color: #16222e;
	border-color: #fff;
}
.banner-btn--exit:hover {
	background: rgb(255 255 255 / 0.88);
}

@media (max-width: 768px) {
	.preview-banner {
		bottom: 10px;
		flex-wrap: wrap;
		border-radius: 16px;
	}
	.banner-sub {
		display: none;
	}
}
</style>
