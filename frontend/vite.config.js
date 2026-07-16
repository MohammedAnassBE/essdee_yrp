import { defineConfig, searchForWorkspaceRoot } from "vite"
import vue from "@vitejs/plugin-vue"
import path from "path"
import fs from "fs"

export default defineConfig({
	server: {
		port: 8082,
		proxy: getProxyOptions(),
		fs: {
			// Absolute paths only — a bare relative fs.allow replaces Vite's
			// default allow-list and can 403 src/ itself in dev (spec §6.2).
			allow: [
				searchForWorkspaceRoot(process.cwd()), // keep default root
				path.resolve(__dirname, "../../yrp/frontend"), // @yrp/web-engine source
				path.resolve(__dirname, "../essdee_yrp/fixtures"), // fixture JSON import (spec §12.3)
			],
		},
	},
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
		// dedupe is THE fix for bare-import resolution through the file: link —
		// there is no node_modules on the walk-up path from apps/yrp/ (spec §6.2).
		dedupe: ["vue", "pinia"],
	},
	build: {
		outDir: "../essdee_yrp/public/frontend",
		emptyOutDir: true,
		target: "es2015",
		rollupOptions: {
			output: {
				// Distinct entry prefix ("essdee-") so web.py can glob the entry
				// unambiguously — Vite may emit a vendor chunk literally named
				// "index", which would otherwise also match index-*.js.
				entryFileNames: "assets/essdee-[hash].js",
				chunkFileNames: "assets/[name]-[hash].js",
				assetFileNames: "assets/[name]-[hash].[ext]",
			},
		},
	},
})

function getProxyOptions() {
	const config = getCommonSiteConfig()
	const webserver_port = config ? config.webserver_port : 8000
	return {
		"^/(app|login|api|assets|files|private)": {
			target: `http://127.0.0.1:${webserver_port}`,
			ws: true,
			router: function (req) {
				const site_name = req.headers.host.split(":")[0]
				return `http://${site_name}:${webserver_port}`
			},
		},
	}
}

function getCommonSiteConfig() {
	let currentDir = path.resolve(".")
	while (currentDir !== "/") {
		if (
			fs.existsSync(path.join(currentDir, "sites")) &&
			fs.existsSync(path.join(currentDir, "apps"))
		) {
			let configPath = path.join(currentDir, "sites", "common_site_config.json")
			if (fs.existsSync(configPath)) {
				return JSON.parse(fs.readFileSync(configPath))
			}
			return null
		}
		currentDir = path.resolve(currentDir, "..")
	}
	return null
}
