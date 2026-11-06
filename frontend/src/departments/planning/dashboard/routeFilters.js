export const DASHBOARD_VIEW = "dashboard"
export const TRACKING_VIEW = "tracking"

const list = (value) => [].concat(value ?? []).flatMap((item) => String(item).split(",")).map((item) => item.trim()).filter(Boolean)

/** Tab, PPO Tracking filters and Show dispatched held in the route query. */
export function readTrackingQuery(query = {}) {
	return {
		view: query.view === TRACKING_VIEW ? TRACKING_VIEW : DASHBOARD_VIEW,
		filters: { ppo: list(query.ppo), lot: list(query.lot), process: list(query.process) },
		showDispatched: query.dispatched === "1",
	}
}

export function trackingQuery({ filters, showDispatched }) {
	const query = { view: TRACKING_VIEW }
	for (const kind of ["ppo", "lot", "process"]) if (filters[kind]?.length) query[kind] = [...filters[kind]]
	if (showDispatched) query.dispatched = "1"
	return query
}

/** Query of a Dashboard drill-down: PPO Tracking with the PPOs or lots selected. */
export function drillQuery(drill) {
	return trackingQuery({ filters: { ppo: drill.ppo, lot: drill.lot, process: [] }, showDispatched: drill.dispatched })
}
