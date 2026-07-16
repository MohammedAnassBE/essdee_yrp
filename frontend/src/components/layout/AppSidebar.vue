<template>
	<aside class="esd-sidebar" :class="{ pinned, 'drawer-open': drawerOpen }">
		<div class="sidebar-logo" @click="goHome">
			<div class="logo-mark">
				<img :src="logoUrl" alt="Essdee YRP" class="logo-img" />
			</div>
			<span class="logo-text">Essdee YRP</span>
		</div>

		<nav class="sidebar-nav">
			<!-- Home (no group label) -->
			<router-link to="/home" class="nav-item" active-class="active" @click="$emit('navigate')">
				<i class="pi pi-th-large nav-icon" />
				<span class="nav-label">Home</span>
			</router-link>

			<!-- Perm-gated DocType groups (arrangement from store.navGroups) -->
			<div
				v-for="grp in sidebarGroups"
				:key="grp.id"
				class="nav-group"
				:class="{ 'section-collapsed': isCollapsed(grp.id) }"
			>
				<!-- Section header: a toggle button (shown only when the rail is
				     expanded). Collapse state is per-user, persisted server-side via
				     useSidebarCollapse — independent of the rail's expand state.
				     Keyed on the group's stable `id` (spec §19 nit 4); Default seeds
				     ids == today's labels so existing persisted state survives. -->
				<button
					type="button"
					class="nav-group-label"
					:aria-expanded="!isCollapsed(grp.id)"
					@click="toggleSection(grp.id)"
				>
					<span class="nav-group-text">{{ grp.label }}</span>
					<i
						class="pi pi-chevron-down nav-group-chevron"
						:class="{ 'is-collapsed': isCollapsed(grp.id) }"
					/>
				</button>
				<router-link
					v-for="item in grp.items"
					:key="item.route"
					:to="`/${item.route}`"
					class="nav-item"
					active-class="active"
					:title="item.label"
					@click="$emit('navigate')"
				>
					<i :class="[item.icon, 'nav-icon']" />
					<span class="nav-label">{{ item.label }}</span>
				</router-link>
			</div>
		</nav>

		<div class="sidebar-foot">
			<!-- Pin keeps the rail expanded (pushes content); persisted in AppLayout. -->
			<button
				class="pin-btn"
				type="button"
				:title="pinned ? 'Unpin sidebar' : 'Pin sidebar open'"
				:aria-pressed="pinned"
				@click="$emit('toggle-pin')"
			>
				<i :class="pinned ? 'pi pi-angle-left' : 'pi pi-angle-right'" />
			</button>
			<!-- Desk is reserved for Administrator / System Manager (the server
			     gate 302s everyone else back to /web) — hide the link for the rest. -->
			<a v-if="isAdmin || hasRole('System Manager')" class="desk-link" href="/app" title="Open Frappe Desk">
				<i class="pi pi-external-link" />
				<span class="nav-label">Desk</span>
			</a>
		</div>
	</aside>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import { useUiConfigStore } from "@yrp/web-engine"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"
import { useSidebarCollapse } from "@/composables/useSidebarCollapse"

defineProps({ pinned: Boolean, drawerOpen: Boolean })
const emit = defineEmits(["toggle-pin", "navigate"])

const router = useRouter()
const { canRead, isAdmin, hasRole } = usePermissions()
const ui = useUiConfigStore()

// Logo comes from Website Settings via frappe.boot (admin-controlled); falls back
// to the bundled Essdee logo when the field is unset.
const logoUrl = window.frappe?.boot?.app_logo || "/assets/essdee_yrp/frontend/essdee-logo.png"

// Arrangement from the layout (store.navGroups — layout-hidden items already
// filtered), mapped onto the catalog: getRegistryByDoctype supplies route/label/
// flags; unknown doctypes (layout typo, §14 row 12) drop with a console.warn.
// The layout item's icon wins when set (arrangement), else the catalog's.
// Live-perm gate PRESERVED: only items the user canRead render — no read
// permission means not rendered. Admin sees everything; DocTypes not installed
// (e.g. Workstation) resolve canRead → false and drop. Empty groups drop.
const sidebarGroups = computed(() =>
	ui.navGroups
		.map((g) => ({
			id: g.id || g.label,
			label: g.label || g.id,
			items: (g.items || [])
				.map((item) => {
					const reg = getRegistryByDoctype(item.doctype)
					if (!reg) {
						console.warn(`[essdee sidebar] unknown doctype in layout nav: "${item.doctype}" — dropped`)
						return null
					}
					return { ...reg, icon: item.icon || reg.icon }
				})
				.filter(Boolean)
				.filter((d) => canRead(d.doctype)),
		}))
		.filter((g) => g.items.length > 0)
)

// Per-user, server-persisted collapse state for each sidebar SECTION.
const { isCollapsed, toggleSection } = useSidebarCollapse()

function goHome() {
	emit("navigate")
	router.push("/home")
}
</script>

<style scoped>
/* Slim rail by default; expands to a flyout on hover, or stays open when pinned.
   Positioned absolutely over the grid's reserved rail column (see AppLayout) so
   the flyout overlays content instead of reflowing it. */
.esd-sidebar {
	position: absolute;
	top: 0;
	left: 0;
	height: 100%;
	width: var(--sidebar-collapsed-width);
	background: var(--esd-card);
	border-right: 1px solid var(--esd-line);
	display: flex;
	flex-direction: column;
	min-height: 0;
	z-index: 20;
	overflow: hidden;
	transition: width 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}

.esd-sidebar:hover,
.esd-sidebar.pinned {
	width: var(--sidebar-width);
}

/* Unpinned hover = flyout overlaying content → lift it with a shadow. */
.esd-sidebar:not(.pinned):hover {
	box-shadow: var(--esd-shadow-pop);
}

.sidebar-logo {
	height: var(--topbar-height);
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 0 16px;
	border-bottom: 1px solid var(--esd-line);
	cursor: pointer;
	flex-shrink: 0;
}

.logo-mark {
	width: 30px;
	height: 30px;
	border-radius: 7px;
	background: #fff;
	border: 1px solid var(--esd-line);
	display: grid;
	place-items: center;
	flex-shrink: 0;
	overflow: hidden;
}
.logo-img {
	width: 100%;
	height: 100%;
	object-fit: contain;
}

.logo-text {
	font-weight: 600;
	letter-spacing: -0.01em;
}

.sidebar-nav {
	flex: 1;
	overflow-y: auto;
	overflow-x: hidden;
	padding: 10px 8px 24px;
}

.nav-group {
	padding: 2px 0 4px;
}

.nav-group-label {
	/* hidden in the slim rail; revealed (display:flex) when expanded */
	display: none;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
	width: 100%;
	font-size: 11px;
	font-weight: 600;
	letter-spacing: 0.08em;
	text-transform: uppercase;
	color: var(--esd-muted-2);
	padding: 8px 12px 6px;
	background: transparent;
	border: 0;
	text-align: left;
	cursor: pointer;
	font-family: inherit;
}

.nav-group-label:hover {
	color: var(--esd-ink);
}

.nav-group-text {
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

.nav-group-chevron {
	font-size: 10px;
	flex-shrink: 0;
	transition: transform 0.15s ease;
}

.nav-group-chevron.is-collapsed {
	transform: rotate(-90deg);
}

.nav-item {
	display: flex;
	align-items: center;
	gap: 11px;
	padding: 8px 12px;
	border-radius: var(--radius-sm);
	color: var(--esd-ink-2);
	font-size: 13.5px;
	border-left: 3px solid transparent;
	margin: 1px 0;
	white-space: nowrap;
}

.nav-item:hover {
	background: var(--esd-slate-50);
}

.nav-item.active {
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	border-left-color: var(--esd-accent);
	font-weight: 600;
}

.nav-icon {
	width: 18px;
	font-size: 15px;
	flex-shrink: 0;
	color: var(--esd-muted);
	text-align: center;
}

.nav-item.active .nav-icon {
	color: var(--esd-accent);
}

/* Labels: faded out in the slim rail, faded in when expanded (hover/pinned). */
.nav-label,
.logo-text {
	opacity: 0;
	transition: opacity 0.12s ease;
	white-space: nowrap;
}

.esd-sidebar:hover .nav-label,
.esd-sidebar:hover .logo-text,
.esd-sidebar.pinned .nav-label,
.esd-sidebar.pinned .logo-text {
	opacity: 1;
}

.esd-sidebar:hover .nav-group-label,
.esd-sidebar.pinned .nav-group-label {
	display: flex;
}

/* Collapsed section → hide its items, but only when the rail is expanded
   (in the slim rail every item shows as a bare icon). */
.esd-sidebar:hover .nav-group.section-collapsed .nav-item,
.esd-sidebar.pinned .nav-group.section-collapsed .nav-item {
	display: none;
}

/* Keyboard parity (spec: expand on hover AND focus). When focus enters the rail
   it expands and reveals labels — but we do NOT apply the section-collapse hiding
   here, so a keyboard user can tab through every item (hiding the focused item
   would blur it). */
.esd-sidebar:focus-within {
	width: var(--sidebar-width);
}
.esd-sidebar:not(.pinned):focus-within {
	box-shadow: var(--esd-shadow-pop);
}
.esd-sidebar:focus-within .nav-label,
.esd-sidebar:focus-within .logo-text {
	opacity: 1;
}
.esd-sidebar:focus-within .nav-group-label {
	display: flex;
}

/* overflow:hidden on the rail would clip a default focus ring — inset it. */
.nav-item:focus-visible,
.pin-btn:focus-visible,
.desk-link:focus-visible {
	outline: 2px solid var(--esd-accent2);
	outline-offset: -2px;
	border-radius: var(--radius-sm);
}

.sidebar-foot {
	border-top: 1px solid var(--esd-line);
	padding: 8px;
	display: flex;
	align-items: center;
	gap: 6px;
	flex-shrink: 0;
}

.pin-btn {
	background: transparent;
	border: 0;
	color: var(--esd-muted);
	padding: 6px 9px;
	border-radius: var(--radius-sm);
	cursor: pointer;
	flex-shrink: 0;
}

.pin-btn:hover {
	background: var(--esd-slate-50);
	color: var(--esd-ink);
}

.desk-link {
	display: flex;
	align-items: center;
	gap: 8px;
	color: var(--esd-muted);
	font-size: 12.5px;
	padding: 6px 9px;
	border-radius: var(--radius-sm);
}

.desk-link:hover {
	background: var(--esd-slate-50);
	color: var(--esd-ink);
}

/* ── Mobile: off-canvas drawer (no hover-expand) ── */
@media (max-width: 768px) {
	.esd-sidebar {
		width: var(--sidebar-width);
		transform: translateX(-100%);
		transition: transform 0.2s ease;
		box-shadow: var(--esd-shadow-pop);
		z-index: 30;
	}
	.esd-sidebar.drawer-open {
		transform: translateX(0);
	}
	/* Drawer is full-width → always show labels + group headers. */
	.esd-sidebar .nav-label,
	.esd-sidebar .logo-text {
		opacity: 1;
	}
	.esd-sidebar .nav-group-label {
		display: flex;
	}
	.esd-sidebar.drawer-open .nav-group.section-collapsed .nav-item {
		display: none;
	}
}
</style>
