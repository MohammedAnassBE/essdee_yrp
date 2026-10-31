import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { getAppLogo } from "../src/utils/appLogo.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

test("getAppLogo returns Desk's boot app logo, or empty when none is set", () => {
	assert.equal(getAppLogo({ app_logo: "/files/logo.png" }), "/files/logo.png")
	assert.equal(getAppLogo({ app_logo: "  /assets/frappe/images/frappe-framework-logo.svg " }), "/assets/frappe/images/frappe-framework-logo.svg")
	assert.equal(getAppLogo({ app_logo: "" }), "")
	assert.equal(getAppLogo({ app_logo: null }), "")
	assert.equal(getAppLogo({}), "")
	assert.equal(getAppLogo(undefined), "")
})

test("top bar renders the logo image and keeps the EY monogram as fallback", () => {
	const app = source("../src/App.vue")
	assert.match(app, /<img v-if="appLogo && !isLogoBroken" class="app-brand__logo" :src="appLogo"[^>]*@error="isLogoBroken = true"/)
	assert.match(app, /<span v-else class="app-brand__mark" aria-hidden="true">EY<\/span>/)
	assert.match(source("../src/styles/main.css"), /\.app-brand__logo \{[^}]*width: 29px;[^}]*height: 29px;[^}]*object-fit: contain;/)
})

test("/web boot and favicon come from Frappe, like Desk", () => {
	const web = source("../../essdee_yrp/www/web.py")
	assert.match(web, /"app_logo": get_app_logo\(\)/)
	assert.doesNotMatch(web, /context\.favicon\s*=/)
})
