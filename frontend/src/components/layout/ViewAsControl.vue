<!-- ViewAsControl — the §10 "View as…" chrome control (SM-only).

     Mounted in BOTH header shells (AppTopbar and ChromeBar) so the control sits
     in the chrome regardless of which header the active layout renders. Hidden
     for everyone who is not Administrator / System Manager — the gate is the
     server-computed roles list the boot payload carries (frappe.boot.user.roles
     via usePermissions, the same `isAdmin || hasRole("System Manager")` gate as
     the sidebar's Desk link and installEngine's isManager). Belt-and-braces:
     the endpoint itself is frappe.only_for("System Manager") server-side, so
     even a hand-crafted call cannot preview without the role.

     Opens a small dialog to preview EITHER a user (their resolved layers, perm
     hints computed as them) OR a bare layout (sandbox mode — no overrides,
     hints = the SM's own). Exactly one may be picked, mirroring the endpoint's
     mutually-exclusive params. On confirm: store.previewAs → the whole app
     re-renders reactively off the store; the URL stays /web (locked decision).
     A previewed layout with soft warnings still renders (preview is
     diagnostic) — a warn toast surfaces the count; PreviewBanner carries the
     details. Escape only closes THIS dialog (PrimeVue default) — it never
     touches an active preview. -->
<template>
	<template v-if="isManager">
		<!-- chrome variant matches ChromeBar's .chrome-btn look; topbar variant
		     matches AppTopbar's outlined-control language. Same behaviour. -->
		<button
			class="viewas-btn"
			:class="chrome ? 'viewas-btn--chrome' : 'viewas-btn--topbar'"
			type="button"
			title="Preview the UI as another user or layout (System Manager)"
			aria-label="View as another user or layout"
			@click="openDialog"
		>
			<i class="pi pi-eye" />
			<span class="viewas-btn__label">View as</span>
		</button>

		<Dialog
			v-model:visible="open"
			modal
			header="View as…"
			class="viewas-dialog"
			:style="{ width: '26rem', maxWidth: '94vw' }"
		>
			<p class="viewas-hint">
				Preview how the UI renders for a user or a layout. Appearance only —
				data, drafts and permissions stay yours.
			</p>

			<div class="viewas-field">
				<label for="viewas-user">User</label>
				<LinkField
					id="viewas-user"
					v-model="pickedUser"
					target-doctype="User"
					placeholder="Search users…"
					:filters="{ enabled: 1, user_type: 'System User' }"
					:dropdown="false"
					@item-select="pickedLayout = ''"
				/>
			</div>

			<div class="viewas-or">— or —</div>

			<div class="viewas-field">
				<label for="viewas-layout">Layout</label>
				<LinkField
					id="viewas-layout"
					v-model="pickedLayout"
					target-doctype="UI Layout"
					placeholder="Search layouts…"
					:filters="{ disabled: 0 }"
					:dropdown="false"
					@item-select="pickedUser = ''"
				/>
			</div>

			<template #footer>
				<Button label="Cancel" text severity="secondary" @click="open = false" />
				<Button
					label="Preview"
					icon="pi pi-eye"
					:loading="busy"
					:disabled="!canConfirm"
					@click="confirmPreview"
				/>
			</template>
		</Dialog>
	</template>
</template>

<script setup>
import { ref, computed } from "vue"
import Dialog from "primevue/dialog"
import Button from "primevue/button"
import { useToast } from "primevue/usetoast"
import { useUiConfigStore } from "@yrp/web-engine"
import LinkField from "@/components/LinkField.vue"
import { usePermissions } from "@/composables/usePermissions"

defineProps({
	// Style variant: true inside ChromeBar (demo .chrome-btn), false in AppTopbar.
	chrome: { type: Boolean, default: false },
})

const ui = useUiConfigStore()
const toast = useToast()
const { isAdmin, hasRole } = usePermissions()

// SM gate — server-computed boot roles, never a client-side guess (§10).
const isManager = computed(() => isAdmin.value || hasRole("System Manager"))

const open = ref(false)
const busy = ref(false)
const pickedUser = ref("")
const pickedLayout = ref("")

// Exactly ONE of user/layout — mirrors get_ui_config_for's param contract.
// LinkField's model can hold free text mid-typing; a pick clears the other
// field (item-select above), so "both filled" only means half-typed leftovers.
const canConfirm = computed(
	() => Boolean(pickedUser.value) !== Boolean(pickedLayout.value)
)

function openDialog() {
	pickedUser.value = ""
	pickedLayout.value = ""
	open.value = true
}

async function confirmPreview() {
	if (!canConfirm.value || busy.value) return
	const target = pickedLayout.value
		? { layout: pickedLayout.value }
		: { user: pickedUser.value }
	busy.value = true
	try {
		await ui.previewAs(target)
		open.value = false
		// Diagnostic honesty: a warned layout still renders (that IS the point
		// of previewing it) — surface how degraded the resolution was.
		const warnings = ui.meta?.warnings || []
		if (warnings.length) {
			toast.add({
				severity: "warn",
				summary: "Previewing with config warnings",
				detail: `${warnings.length} warning${warnings.length > 1 ? "s" : ""} — off-vocabulary values fall back. First: ${warnings[0]}`,
				life: 6000,
			})
		}
	} catch (err) {
		// Unknown/disabled user, unknown/disabled/broken layout, permission —
		// the server fails loudly; nothing changed in the store.
		toast.add({
			severity: "error",
			summary: "Preview failed",
			detail: err?.message || "Could not load the preview config",
			life: 6000,
		})
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
/* Shared trigger bones; two skins so the control looks native in each header. */
.viewas-btn {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	cursor: pointer;
	font-family: inherit;
	white-space: nowrap;
	background: none;
	border: 1px solid var(--esd-line);
	color: var(--esd-ink-2);
}
.viewas-btn:hover {
	border-color: var(--esd-accent);
}
.viewas-btn .pi {
	font-size: 12px;
}

/* ChromeBar skin — mirrors .chrome-btn exactly (3px 8px, radius 8, 12px). */
.viewas-btn--chrome {
	border-radius: 8px;
	padding: 3px 8px;
	margin-left: 8px;
	font-size: 12px;
}

/* AppTopbar skin — sized against the 32px cmdk-trigger / icon buttons. */
.viewas-btn--topbar {
	height: 32px;
	border-radius: var(--radius-sm, 8px);
	padding: 0 10px;
	font-size: var(--fs-sm, 12.5px);
	background: var(--esd-bg);
}

@media (max-width: 768px) {
	/* Narrow screens: icon-only (same giveaway rule as the chrome user chip). */
	.viewas-btn__label {
		display: none;
	}
}

.viewas-hint {
	margin: 0 0 14px;
	font-size: 12.5px;
	color: var(--esd-muted);
	line-height: 1.5;
}
.viewas-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.viewas-field label {
	font-size: 11.5px;
	font-weight: 650;
	color: var(--esd-ink-2);
}
.viewas-or {
	text-align: center;
	font-size: 11px;
	color: var(--esd-muted-2);
	margin: 10px 0;
	user-select: none;
}
</style>
