<template>
	<!-- Mobile shell (layout nav.position === "bottom-tabs" OR nav.shell ===
	     "mobile-shell", USE_CASE §4 Track 1 item 4): a compact phone chrome —
	     the topbar (its own <768px media rules collapse it at a phone viewport)
	     over a single-column scrolling main, with the PRIMARY nav in a bottom
	     tab bar pinned to the column base; neither the sidebar rail nor the pill
	     row is mounted.
	     `mobile-shell` additionally FRAMES the shell to a phone-width column so a
	     mobile persona previews correctly at desktop widths too. Only layouts
	     that OPT IN get this — the Default keeps today's sidebar (parity law). -->
	<div
		v-if="useMobileShell"
		class="esd-shell esd-shell--mobile"
		:class="{ 'esd-shell--framed': mobileShell }"
	>
		<!-- No drawer in this shell (bottom tabs are the nav) → no hamburger. -->
		<ChromeBar v-if="hasChrome" />
		<AppTopbar v-else :drawer-open="false" :show-hamburger="false" />
		<main class="esd-main esd-main--mobile">
			<router-view v-slot="{ Component }">
				<transition name="route-fade" mode="out-in">
					<component :is="Component" :key="$route.path" />
				</transition>
			</router-view>
		</main>
		<BottomTabs />
		<CommandPalette />
		<KnobsPanel />
		<!-- §10 View-as strip: renders only while an SM preview is active. -->
		<PreviewBanner />
	</div>

	<!-- Topbar-pill shell (layout nav.position === "topbar", 2026-07-15 Demo-7
	     skin): chrome strip + pill nav stacked over the main column; the sidebar
	     is not mounted at all. Only layouts that OPT IN via the knob get this. -->
	<div v-else-if="topbarNav" class="esd-shell esd-shell--topnav">
		<!-- No drawer exists in this shell (pills scroll horizontally on narrow
		     screens), so neither header gets a hamburger: ChromeBar only shows
		     one when has-drawer is passed, and AppTopbar's is switched off —
		     it was a dead control here (no toggle-drawer handler). -->
		<ChromeBar v-if="hasChrome" />
		<AppTopbar v-else :drawer-open="false" :show-hamburger="false" />
		<NavTopbar />
		<main class="esd-main esd-main--topnav">
			<router-view v-slot="{ Component }">
				<transition name="route-fade" mode="out-in">
					<component :is="Component" :key="$route.path" />
				</transition>
			</router-view>
		</main>
		<CommandPalette />
		<!-- Self-service knobs (locked 2026-07-15): shown to every user in every
		     layout; renders nothing visually different until a knob is touched. -->
		<KnobsPanel />
		<!-- §10 View-as strip: renders only while an SM preview is active. -->
		<PreviewBanner />
	</div>

	<!-- Default shell — today's sidebar + topbar grid, unchanged (parity law).
	     ChromeBar swaps in for AppTopbar only when the layout has a chrome knob. -->
	<div
		v-else
		class="esd-shell"
		:class="{ pinned: effectivePinned, 'drawer-open': drawerOpen, 'esd-shell--right': railSide === 'right' }"
	>
		<!-- Reserves the rail's width in the grid; the real sidebar is positioned
		     absolutely over it so it can expand into a flyout without reflowing. -->
		<div class="rail-spacer" aria-hidden="true" />
		<AppSidebar
			:pinned="effectivePinned"
			:drawer-open="drawerOpen"
			:rail-side="railSide"
			:icon-rail="iconRail"
			@toggle-pin="togglePin"
			@navigate="drawerOpen = false"
		/>
		<!-- Sidebar shell: whichever header renders must be able to open the
		     mobile drawer — under 768px it is the ONLY way into the nav. -->
		<ChromeBar
			v-if="hasChrome"
			has-drawer
			:drawer-open="drawerOpen"
			@toggle-drawer="drawerOpen = !drawerOpen"
		/>
		<AppTopbar v-else :drawer-open="drawerOpen" @toggle-drawer="drawerOpen = !drawerOpen" />
		<main class="esd-main">
			<!-- Key by path so each DocType/record gets a fresh instance — the
			     dynamic views capture their doctype at setup (useDoc/useDocList),
			     so reusing the instance across routes would load stale data. -->
			<router-view v-slot="{ Component }">
				<transition name="route-fade" mode="out-in">
					<component :is="Component" :key="$route.path" />
				</transition>
			</router-view>
		</main>
		<!-- Mobile drawer scrim (closes the drawer on tap). -->
		<div class="esd-scrim" @click="drawerOpen = false" />
		<CommandPalette />
		<KnobsPanel />
		<!-- §10 View-as strip: renders only while an SM preview is active. -->
		<PreviewBanner />
	</div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue"
import { useUiConfigStore, KnobsPanel } from "@yrp/web-engine"
import AppSidebar from "./AppSidebar.vue"
import AppTopbar from "./AppTopbar.vue"
import ChromeBar from "./ChromeBar.vue"
import NavTopbar from "./NavTopbar.vue"
import BottomTabs from "./BottomTabs.vue"
import PreviewBanner from "./PreviewBanner.vue"
import CommandPalette from "@/components/CommandPalette.vue"
import { useAuth } from "@/composables/useAuth"

// Layout-driven shell knobs (2026-07-15). Both default OFF: a layout without
// them — the Default — renders today's DOM exactly (parity law). Reactive to
// the store so View-as / Refresh UI reshapes the shell live.
const ui = useUiConfigStore()
const hasChrome = computed(() => {
	const c = ui.active.chrome
	return c !== null && typeof c === "object" && !Array.isArray(c)
})

// ── Nav-family shell selection (USE_CASE §4 Track 1 item 4). Every knob is
// opt-in: an absent nav.position resolves to "sidebar" and nav.shell to
// "standard", so the Default renders today's sidebar shell byte-identically
// (parity law). The three branches are mutually exclusive in the template:
// mobile shell → topnav shell → sidebar shell (the default v-else).
const navPosition = computed(() => ui.active.nav?.position || "sidebar")
const navSidebarMode = computed(() => ui.active.nav?.sidebar || "flyout")
const navShell = computed(() => ui.active.nav?.shell || "standard")

// bottom-tabs (position) OR mobile-shell (shell) → the phone shell with a bottom
// tab bar. mobileShell also frames the column to phone width.
const mobileShell = computed(() => navShell.value === "mobile-shell")
const useMobileShell = computed(() => navPosition.value === "bottom-tabs" || mobileShell.value)
const topbarNav = computed(() => navPosition.value === "topbar")

// Sidebar-family variants (consumed only by the v-else sidebar branch):
//   sidebar-right → rail on the right edge; icon-rail → permanent icon-only rail.
const railSide = computed(() => (navPosition.value === "sidebar-right" ? "right" : "left"))
const iconRail = computed(() => navPosition.value === "icon-rail")
// nav.sidebar: "pinned" makes the sidebar-family shells rest EXPANDED (see
// effectivePinned below, defined once the user pin ref exists).
const layoutPinned = computed(() => navSidebarMode.value === "pinned")

// Rail is slim by default (hover to expand); "pin" keeps it expanded and pushes
// content. Persisted per-browser so a user's preference survives reloads.
// localStorage can throw (Safari private mode, sandboxed iframe) — never let that
// crash the shell mount; persistence just degrades to per-session.
const PIN_KEY = "essdee.sidebar.pinned"
function readPinned() {
	try {
		return localStorage.getItem(PIN_KEY) === "1"
	} catch {
		return false
	}
}
function writePinned(v) {
	try {
		localStorage.setItem(PIN_KEY, v ? "1" : "0")
	} catch {
		/* non-fatal — persistence degrades to this session only */
	}
}

const pinned = ref(readPinned())
const drawerOpen = ref(false)

// nav.sidebar: "pinned" ORs with the user's own pin toggle, so the Default (no
// knob) tracks the user's localStorage pin exactly — effectivePinned === pinned
// there (parity law); a "pinned" layout just forces the expanded resting state.
const effectivePinned = computed(() => pinned.value || layoutPinned.value)

function togglePin() {
	pinned.value = !pinned.value
	writePinned(pinned.value)
}

// Esc closes the mobile drawer.
function onKeydown(e) {
	if (e.key === "Escape" && drawerOpen.value) drawerOpen.value = false
}

const { checkAuth } = useAuth()
onMounted(() => {
	checkAuth()
	document.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => document.removeEventListener("keydown", onKeydown))
</script>

<style scoped>
.esd-shell {
	position: relative;
	display: grid;
	grid-template-columns: var(--rail-w) 1fr;
	grid-template-rows: var(--topbar-height) 1fr;
	grid-template-areas:
		"rail topbar"
		"rail main";
	height: 100vh;
	--rail-w: var(--sidebar-collapsed-width);
}

/* Topbar-pill shell (opt-in): simple column — chrome strip, pill row, main. */
.esd-shell--topnav {
	display: flex;
	flex-direction: column;
}
.esd-main--topnav {
	flex: 1;
	min-height: 0;
}

/* Mobile shell (opt-in: bottom-tabs / mobile-shell) — column of header, a
   single scrolling main, and the bottom tab bar (a normal flex child, so it
   stays at the column's bottom and never overlaps content; main scrolls inside
   its own box). */
.esd-shell--mobile {
	display: flex;
	flex-direction: column;
	/* No rail to clear — keep the engine's Knobs FAB at the left edge, lifted
	   clear of the bottom tab bar below. The rail-offset rule excludes this
	   shell, so this 18px is the only match. */
	--yrp-knobs-left: 18px;
}
.esd-main--mobile {
	flex: 1;
	min-height: 0;
	overflow-y: auto;
	padding: 18px 16px 24px;
	background: var(--esd-bg);
}
/* Lift the engine Knobs FAB above the ~56px bottom tab bar (it hardcodes
   bottom:18px; nudged here so it never sits on the bar). */
.esd-shell--mobile :deep(.yrp-knobs) {
	bottom: calc(64px + env(safe-area-inset-bottom, 0px));
}
/* mobile-shell FRAMES the app to a phone-width column, centered, with side
   hairlines — a mobile persona previews correctly even on a desktop viewport.
   The bottom tab bar rides inside this column (flex child, not fixed). */
.esd-shell--framed {
	max-width: 440px;
	margin: 0 auto;
	border-left: 1px solid var(--esd-line);
	border-right: 1px solid var(--esd-line);
}

/* Pinned → grid reserves the full sidebar width; content is pushed (no overlay). */
.esd-shell.pinned {
	--rail-w: var(--sidebar-width);
}

/* sidebar-right (opt-in): the rail column moves to the RIGHT; content sits left.
   rail-spacer still occupies grid-area "rail", now the right column. */
.esd-shell--right {
	grid-template-columns: 1fr var(--rail-w);
	grid-template-areas:
		"topbar rail"
		"main rail";
}
/* With the rail on the right there is nothing at the left edge to clear, so the
   Knobs FAB returns to the left margin (the rail-offset rule below excludes this
   shell, so this 18px is the only match). */
.esd-shell.esd-shell--right {
	--yrp-knobs-left: 18px;
}

/* Left-rail sidebar shells only (default sidebar + icon-rail): shift the engine's
   Knobs FAB right of the rail so it never covers the rail-footer collapse chevron
   (pin button). Rides --rail-w, so it also clears the pinned full-width sidebar and
   collapses back to the demo 18px on mobile (--rail-w: 0px). Excluded shells keep
   the FAB at the left margin via their own rule above: the topbar shell (no rail),
   the mobile shell (bottom-tabs, no rail), and sidebar-right (rail on the right
   edge — nothing at the left to clear). Excluding them here means those shells'
   own 18px rules apply regardless of source order. */
.esd-shell:not(.esd-shell--topnav):not(.esd-shell--mobile):not(.esd-shell--right) {
	--yrp-knobs-left: calc(var(--rail-w) + 18px);
}

.rail-spacer {
	grid-area: rail;
}

.esd-main {
	grid-area: main;
	overflow-y: auto;
	padding: 22px 28px 60px;
	background: var(--esd-bg);
}

/* Scrim only exists on mobile when the drawer is open. */
.esd-scrim {
	display: none;
}

@media (max-width: 768px) {
	.esd-shell {
		grid-template-columns: 1fr;
		grid-template-areas:
			"topbar"
			"main";
		--rail-w: 0px;
	}
	.rail-spacer {
		display: none;
	}
	.esd-shell.drawer-open .esd-scrim {
		display: block;
		position: fixed;
		inset: 0;
		background: rgb(var(--c-ink) / 0.42);
		z-index: 25;
	}
}

/* Subtle cross-fade between routes so navigation feels smooth, not a hard cut.
   Short + opacity-only so it never delays interaction. */
.route-fade-enter-active,
.route-fade-leave-active {
	transition: opacity 0.15s ease;
}
.route-fade-enter-from,
.route-fade-leave-to {
	opacity: 0;
}
</style>
