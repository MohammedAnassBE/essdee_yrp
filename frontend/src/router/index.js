import { createRouter, createWebHistory } from "vue-router"

import AdministratorPage from "../components/AdministratorPage.vue"
import CuttingPlan from "../departments/CuttingPlan.vue"
import CuttingPlans from "../departments/CuttingPlans.vue"
import CuttingReports from "../departments/CuttingReports.vue"
import { departments } from "../departments/registry.js"

const routes = [
	{
		path: "/",
		name: "administrator",
		component: AdministratorPage,
	},
	...departments.map((department) => ({
		path: department.path,
		name: department.key,
		component: department.component,
	})),
	{
		path: "/cutting/plans",
		name: "cutting-plans",
		component: CuttingPlans,
	},
	{
		path: "/cutting/reports",
		name: "cutting-reports",
		component: CuttingReports,
	},
	{
		path: "/cutting/plans/:cuttingPlanId",
		name: "cutting-plan",
		component: CuttingPlan,
	},
	{
		path: "/cutting/:cuttingPlanId",
		redirect: (to) => ({
			name: "cutting-plan",
			params: { cuttingPlanId: to.params.cuttingPlanId },
		}),
	},
	{
		path: "/:pathMatch(.*)*",
		redirect: "/",
	},
]

export default createRouter({
	history: createWebHistory("/web/"),
	routes,
})
