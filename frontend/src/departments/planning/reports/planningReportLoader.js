import { getCuttingReportPermissions } from "../../../api/cuttingReports.js"
import { getFinishingCapabilities } from "../../../api/finishing.js"
import { getSewingCapabilities } from "../../../api/sewing.js"
import { planningReports } from "./planningReportCatalog.js"

const GROUP_LOADERS = { cutting: getCuttingReportPermissions, sewing: getSewingCapabilities, finishing: getFinishingCapabilities }

/** Planning reports readable under the Planning `sections.reports` capability, loading each enabled group. */
export async function loadPlanningReports(section = {}, loaders = GROUP_LOADERS) {
	const groups = Object.keys(loaders).filter(group => section.groups?.[group] === true)
	const loaded = await Promise.all(groups.map(group => loaders[group]()))
	const capabilities = Object.fromEntries(groups.map((group, index) => [group, loaded[index] || {}]))
	return planningReports({ ...capabilities, production: section.groups?.production === true ? section.production : {} })
}
