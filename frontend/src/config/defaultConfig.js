// Compiled-in fallback config = the SAME file that seeds Premium White
// (spec §12.3). Vite inlines the JSON import, so fixture, seeded record and
// client fallback are ONE file — drift is impossible, and the white-screen
// scenario is structurally unreachable (the fallback is inside the JS already
// executing). The fixture is in exact `bench export-fixtures` format: an array
// of docs whose `config` field is a JSON *string*.
import { ENGINE_SCHEMA_VERSION } from "@/engine"

import layouts from "../../../essdee_yrp/fixtures/ui_layout.json"

// Guarded end-to-end: a missing/renamed "Premium White" in
// the fixture — or an unparseable config string — must never throw at module
// init (that IS the white screen this file exists to prevent). Degrade to a
// minimal empty-but-complete skeleton with a LOUD error so the break is seen
// in review/console, not by end users.
function loadFallback() {
	try {
		const record = Array.isArray(layouts) ? layouts.find((l) => l?.name === "Premium White") : null
		if (!record) throw new Error('no layout named "Premium White" in fixtures/ui_layout.json')
		const raw = record.config
		const parsed = typeof raw === "string" ? JSON.parse(raw) : raw
		if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))
			throw new Error('"Premium White" layout config is not a JSON object')
		return parsed
	} catch (e) {
		console.error(
			`[essdee-web] compiled-in Premium White layout is broken (${e?.message}) — ` +
				"serving a minimal empty fallback; fix essdee_yrp/fixtures/ui_layout.json",
			e
		)
		// Mirrors the server skeleton (ui_config.get_skeleton): every key the
		// renderer reads exists, so nothing crashes — nav/home are just empty.
		return {
			schema_version: ENGINE_SCHEMA_VERSION,
			nav: { groups: [], hidden: {} },
			screens: { home: { blocks: [], hidden: {} } },
			listViews: {},
			quickCreate: [],
			theme: { mode: "user", accent: null },
		}
	}
}

export const fallbackConfig = loadFallback()
