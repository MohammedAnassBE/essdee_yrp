import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"
import { parse, compileScript } from "@vue/compiler-sfc"

const file = new URL("../src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue", import.meta.url)

test("related workspace modules wait for dialog render and retain a closeable loading/error state", () => {
 const source = fs.readFileSync(file, "utf8")
 const script = compileScript(parse(source).descriptor, { id: "dialog" }).content
 assert.doesNotMatch(script, /^import Fabric(?:DeliveryChallan|GoodsReceivedNote) from/m)
 assert.match(script, /workspaceModule\(\(\) => import\("\.\.\/FabricDeliveryChallan.vue"\)\)/)
 assert.match(script, /workspaceModule\(\(\) => import\("\.\.\/FabricGoodsReceivedNote.vue"\)\)/)
 const setup = source.split("<script setup>")[1].split("</script>")[0]
 const start = setup.indexOf("function workspaceModule(")
 assert.ok(start >= 0)
 const code = setup.slice(start, setup.indexOf("const props", start))
 let loads = 0, options
 const create = new Function("defineAsyncComponent", "h", "Message", "Button", "close", code + "; return workspaceModule")(
  value => { options = value; return value }, (...args) => args, "Message", "Button", () => {},
 )
 create(() => { loads++; return Promise.resolve({}) })
 assert.equal(loads, 0)
 assert.equal(options.delay, 0)
 assert.equal(options.loadingComponent.render()[2][1][1].label, "Close")
 assert.equal(options.errorComponent.render()[2][1][1].label, "Close")
 options.loader(); assert.equal(loads, 1)
})
