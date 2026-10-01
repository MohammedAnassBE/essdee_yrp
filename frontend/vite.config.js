import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

export default defineConfig({
	plugins: [vue()],
	server: {
		port: 8082,
	},
	build: {
		outDir: "../essdee_yrp/public/frontend",
		emptyOutDir: true,
		target: "es2015",
		rollupOptions: {
			output: {
				entryFileNames: "assets/essdee-[hash].js",
				chunkFileNames: "assets/[name]-[hash].js",
				assetFileNames: "assets/[name]-[hash].[ext]",
			},
		},
	},
})
