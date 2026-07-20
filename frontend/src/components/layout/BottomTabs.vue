<!-- BottomTabs — phone bottom tab bar (layout `nav.position: "bottom-tabs"`,
     USE_CASE §4 Track 1 item 4). Mounted by AppLayout in the mobile shell
     (nav.position "bottom-tabs" OR nav.shell "mobile-shell") INSTEAD of the
     sidebar/topnav; the rail is not mounted at all in that shell. Layouts
     without a mobile knob keep today's sidebar exactly (parity law).

     Hand-rolled token-themed bar — NOT PrimeVue Dock/Menubar (STACK_DECISION
     2026-07-17: those are macOS-dock / desktop-menu topologies, wrong for
     mobile tabs). Touch targets are ≥44px per Track 1 item 4.

     Locked rules (mirrors AppSidebar / NavTopbar):
       - Home is ALWAYS the first tab, unconditionally (store `home` is reserved).
       - tabs flatten from store.navGroups in layout order; icon + label carried.
       - every tab passes the live canRead() gate (preview-aware §10) —
         arrangement never grants capability (spec §15).
       - unknown doctypes drop with a console.warn (same rule as AppSidebar).
     Overflow (`nav.overflow`, default 5): when the tab count exceeds the max,
     the bar shows the first N tabs + a trailing "More" tab that opens a bottom
     sheet with the rest (first N + More). Absent knob → the shipped default. -->
<template>
	<nav class="esd-tabbar" aria-label="Primary">
		<router-link
			v-for="tab in primaryTabs"
			:key="tab.key"
			:to="tab.to"
			class="tabbar-item"
			:class="{ active: isTabActive(tab) }"
			@click="closeMore"
		>
			<i :class="[tab.icon, 'tabbar-ico']" />
			<span class="tabbar-label">{{ tab.label }}</span>
		</router-link>

		<!-- Trailing "More" tab — only when the tab count overflows the bar. -->
		<button
			v-if="hasMore"
			type="button"
			class="tabbar-item tabbar-more"
			:class="{ active: moreOpen || isOverflowRouteActive }"
			:aria-expanded="moreOpen"
			aria-haspopup="true"
			@click="moreOpen = !moreOpen"
		>
			<i class="pi pi-ellipsis-h tabbar-ico" />
			<span class="tabbar-label">More</span>
		</button>
	</nav>

	<!-- Overflow sheet: the tabs that did not fit, in a bottom sheet. -->
	<teleport to="body">
		<div v-if="hasMore && moreOpen" class="esd-tabsheet-scrim" @click="closeMore" />
		<div v-if="hasMore && moreOpen" class="esd-tabsheet" role="dialog" aria-label="More navigation">
			<div class="tabsheet-grip" aria-hidden="true" />
			<div class="tabsheet-grid">
				<router-link
					v-for="tab in overflowTabs"
					:key="tab.key"
					:to="tab.to"
					class="tabsheet-item"
					:class="{ active: isTabActive(tab) }"
					@click="closeMore"
				>
					<i :class="[tab.icon, 'tabsheet-ico']" />
					<span class="tabsheet-label">{{ tab.label }}</span>
				</router-link>
			</div>
		</div>
	</teleport>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useUiConfigStore } from "@yrp/web-engine"
import { usePreviewGate } from "@/composables/usePreviewGate"
import { getRegistryByDoctype } from "@/config/doctypes"

const route = useRoute()
const ui = useUiConfigStore()
// Preview-aware read gate — canRead outside a §10 preview, target hints during.
const { gateRead } = usePreviewGate()

const moreOpen = ref(false)
function closeMore() {
	moreOpen.value = false
}

// Home is always first (store `home` reserved — client renders Home itself).
const HOME_TAB = { key: "__home__", to: "/home", label: "Home", icon: "pi pi-th-large", doctype: null }

// Flatten the layout's nav groups into one ordered tab list (Home + items).
// Registry supplies route/label; gateRead gates (= canRead, preview-aware).
const allTabs = computed(() => {
	const tabs = [HOME_TAB]
	for (const grp of ui.navGroups) {
		for (const item of grp.items || []) {
			const reg = getRegistryByDoctype(item.doctype)
			if (!reg) {
				console.warn(`[essdee tabbar] unknown doctype in layout nav: "${item.doctype}" — dropped`)
				continue
			}
			if (!gateRead(reg.doctype)) continue
			tabs.push({
				key: reg.doctype,
				to: `/${reg.route}`,
				label: reg.label,
				icon: item.icon || reg.icon,
				doctype: reg.doctype,
			})
		}
	}
	return tabs
})

// nav.overflow — max PRIMARY tabs before the trailing "More" tab (first N + More).
// Soft int 2-8 (server NAV_OVERFLOW_MIN/MAX); anything else falls back to 5.
const OVERFLOW_DEFAULT = 5
const overflowMax = computed(() => {
	const n = ui.active.nav?.overflow
	return Number.isInteger(n) && n >= 2 && n <= 8 ? n : OVERFLOW_DEFAULT
})

const hasMore = computed(() => allTabs.value.length > overflowMax.value)
// Contract (CATALOG.md nav.overflow, server NAV_OVERFLOW, ui_config.py): overflow
// is the count of PRIMARY tabs shown — the bar shows the first `overflowMax` tabs
// and collapses the rest behind a trailing "More" tab (first N primary + More).
const primaryTabs = computed(() =>
	hasMore.value ? allTabs.value.slice(0, overflowMax.value) : allTabs.value
)
const overflowTabs = computed(() => (hasMore.value ? allTabs.value.slice(overflowMax.value) : []))

// A tab is active on its base route AND its detail routes (/work-order/WO-1).
function isTabActive(tab) {
	if (tab.to === "/home") return route.path === "/home" || route.path === "/"
	return route.path === tab.to || route.path.startsWith(`${tab.to}/`)
}
// The "More" tab lights up when the current route is one of the hidden tabs.
const isOverflowRouteActive = computed(() => overflowTabs.value.some((t) => isTabActive(t)))

// Close the sheet whenever navigation lands somewhere (belt-and-braces: the
// per-item @click already closes, but a programmatic route change should too).
watch(
	() => route.path,
	() => closeMore()
)
</script>

<style scoped>
/* Bottom bar — a normal flex child at the base of the mobile-shell column (the
   shell is a height:100vh flex column with the main scrolling inside its own
   box), so the bar pins to the bottom without overlapping content and stays
   inside the framed phone column. Hand-rolled from the demo .bottomtabs, on app
   tokens — NOT PrimeVue Dock/Menubar (STACK_DECISION). */
.esd-tabbar {
	flex: none;
	display: flex;
	background: var(--esd-card);
	border-top: 1px solid var(--esd-line);
	/* Respect the phone home-indicator safe area (iOS). */
	padding-bottom: env(safe-area-inset-bottom, 0px);
}

/* Each tab: icon over label, ≥44px touch target (Track 1 item 4). */
.tabbar-item {
	flex: 1 1 0;
	min-width: 0;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 3px;
	min-height: 56px;
	padding: 6px 4px;
	color: var(--esd-muted);
	font-size: 10.5px;
	font-weight: 600;
	text-decoration: none;
	background: none;
	border: 0;
	border-top: 2px solid transparent;
	cursor: pointer;
	font-family: inherit;
	-webkit-tap-highlight-color: transparent;
}
.tabbar-item:hover {
	color: var(--esd-ink-2);
}
.tabbar-item.active {
	color: var(--esd-accent);
	/* Active tint: top accent bar (demo box-shadow:inset 0 2px 0). */
	border-top-color: var(--esd-accent);
}

.tabbar-ico {
	font-size: 18px;
	line-height: 1;
}

.tabbar-label {
	max-width: 100%;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.tabbar-item:focus-visible {
	outline: 2px solid var(--esd-accent2);
	outline-offset: -2px;
}

/* ── Overflow "More" bottom sheet ── */
.esd-tabsheet-scrim {
	position: fixed;
	inset: 0;
	background: rgb(var(--c-ink) / 0.42);
	z-index: 44;
}

.esd-tabsheet {
	position: fixed;
	left: 0;
	right: 0;
	bottom: 0;
	z-index: 45;
	background: var(--esd-card);
	border-top: 1px solid var(--esd-line);
	border-radius: var(--radius) var(--radius) 0 0;
	box-shadow: var(--esd-shadow-pop);
	padding: 8px 14px calc(18px + env(safe-area-inset-bottom, 0px));
	animation: tabsheet-up 0.2s ease;
}
@keyframes tabsheet-up {
	from {
		transform: translateY(100%);
	}
	to {
		transform: translateY(0);
	}
}

.tabsheet-grip {
	width: 40px;
	height: 4px;
	border-radius: 999px;
	background: var(--esd-line);
	margin: 4px auto 12px;
}

.tabsheet-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
	gap: 6px;
}

.tabsheet-item {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 7px;
	min-height: 76px;
	padding: 10px 6px;
	border-radius: var(--radius-sm);
	color: var(--esd-ink-2);
	font-size: 12px;
	font-weight: 600;
	text-align: center;
	text-decoration: none;
}
.tabsheet-item:hover {
	background: var(--esd-slate-50);
}
.tabsheet-item.active {
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
}
.tabsheet-ico {
	font-size: 22px;
	color: var(--esd-muted);
}
.tabsheet-item.active .tabsheet-ico {
	color: var(--esd-accent);
}
.tabsheet-label {
	max-width: 100%;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.tabsheet-item:focus-visible {
	outline: 2px solid var(--esd-accent2);
	outline-offset: -2px;
}
</style>
