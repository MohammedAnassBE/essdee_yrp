import { createRouter, createWebHistory } from "vue-router"

const routes = [
	{
		path: "/",
		component: () => import("@/components/layout/AppLayout.vue"),
		children: [
			{
				path: "",
				redirect: "/home",
			},
			// Home — work hub landing
			{
				path: "home",
				name: "Home",
				component: () => import("@/views/home/HomePage.vue"),
			},
			// ── Rich production-config flows (R1a) — EXPLICIT routes, declared
			//    BEFORE the generic :docRoute/:id catch-all so they win the match.
			//    IPDConfigView: the IPD config surface (BOM + processes + matrices)
			//    for an EXISTING IPD. Create flows go through DocDetail (the
			//    rich view assumes the doc already exists; preserves the strict
			//    "no Desk redirect" rule — see conventions.md 2026-05-29).
			//    ProcessMatrixEditor: the "process the combination" editor; also
			//    handles :id === "new" (create) reading ?ipd=&process= from query.
			{
				path: "item-production-detail/new",
				name: "IPDCreate",
				component: () => import("@/views/dynamic/DocDetail.vue"),
				props: { docRoute: "item-production-detail", id: "new" },
			},
			// /web edit-fields path. IPDConfigView is the rich BOM/matrix surface;
			// editing the IPD's scalar fields + child rows happens via DocDetail
			// here. Must be declared BEFORE the IPDConfigView catch-all.
			{
				path: "item-production-detail/:id/fields",
				name: "IPDEditFields",
				component: () => import("@/views/dynamic/DocDetail.vue"),
				props: (route) => ({ docRoute: "item-production-detail", id: route.params.id }),
			},
			{
				path: "item-production-detail/:id",
				name: "IPDConfig",
				component: () => import("@/views/dynamic/IPDConfigView.vue"),
				props: true,
			},
			{
				path: "ipd-process-matrix/:id",
				name: "ProcessMatrix",
				component: () => import("@/views/dynamic/ProcessMatrixEditor.vue"),
				props: true,
			},
			//    BOMMappingEditor (R1b): the "Item BOM based on attribute mapping"
			//    editor. Cross-product of the produced item's attribute values ×
			//    the BOM item's attribute values + per-combination quantities.
			{
				path: "item-bom-attribute-mapping/:id",
				name: "BOMMapping",
				component: () => import("@/views/dynamic/BOMMappingEditor.vue"),
				props: true,
			},
			// Generic read-only detail/form page (DocDetail) — serves every
			// sidebar DocType. View mode now; edit/create + write flows next.
			{
				path: ":docRoute/:id",
				name: "DocDetail",
				component: () => import("@/views/dynamic/DocDetail.vue"),
				props: true,
			},
			// Dynamic list (catch-all) — serves every sidebar DocType.
			{
				path: ":docRoute",
				name: "DynamicList",
				component: () => import("@/views/dynamic/DynamicListPage.vue"),
				props: true,
			},
		],
	},
]

const router = createRouter({
	history: createWebHistory("/web"),
	routes,
})

// Auth guard — boot.user is injected by web.py (load_user()); for Guests it is
// the string "Guest", otherwise the user object. Bounce Guests to login.
router.beforeEach((to) => {
	const bootUser = window.frappe?.boot?.user
	const isGuest = bootUser === "Guest" || bootUser?.name === "Guest"
	if (isGuest) {
		window.location.href = `/login?redirect-to=${encodeURIComponent("/web" + to.fullPath)}`
		return false
	}
})

// ── Stale-chunk recovery ────────────────────────────────────────────────────
// After a new build deploys, an already-open tab still references the PREVIOUS
// build's lazy chunks (hashed filenames). The next navigation/preload then 404s
// with "Failed to fetch dynamically imported module", stranding the user (e.g.
// on "+ New"). Recover with a ONE-SHOT full reload at the intended destination
// to pull the current build. A short time-guard prevents a reload loop if the
// chunk is genuinely missing rather than merely stale.
// Stale-chunk handling. After a new build deploys, an already-open tab still
// references the PREVIOUS build's hashed chunks, so a dynamic import can 404.
// We USED TO force a full reload to recover — but that reload redirected the user
// mid-interaction (typing an Item on the Production Order grid bounced the page
// back to a blank /new and wiped their input). AUTO-RELOAD IS DISABLED (user
// request, 2026-06-01): we swallow the error and log a hint instead; the user
// refreshes manually (Ctrl+Shift+R) to pick up a new build. NOTHING here
// navigates or reloads the page anymore.
function onStaleChunk(cause) {
	console.warn(
		"[essdee] a code chunk failed to load — a newer build is probably deployed. " +
		"Hard-refresh (Ctrl+Shift+R) to update. cause:",
		cause || "",
	)
}

router.onError((error) => {
	const msg = error?.message || ""
	if (/dynamically imported module|module script failed|Failed to fetch/i.test(msg)) {
		onStaleChunk(msg)
	}
})

// Vite's preload helper dispatches this when a modulepreload fails. Prevent the
// default unhandled hard-error, but do NOT reload.
window.addEventListener("vite:preloadError", (event) => {
	event.preventDefault()
	onStaleChunk(event?.payload?.message)
})

export default router
