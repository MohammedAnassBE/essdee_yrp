import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../essdee_yrp/public/js/SewingPlan/components/DataEntryTab.vue", import.meta.url), "utf8");

const payloadBefore = (method) => {
    const call = source.indexOf(`sd_yrp_sewing_plan.${method}"`);
    assert.ok(call > 0, `${method} call not found`);
    const start = source.lastIndexOf("const payload = {", call);
    assert.ok(start > 0, `${method} payload not found`);
    return source.slice(start, call);
};

for (const method of ["submit_data_entry_log", "update_sewing_plan_data"]) {
    test(`Desk ${method} payload carries the Sewing Unit scope`, () => {
        const payload = payloadBefore(method);
        assert.match(payload, /\bsupplier:\s*props\.selected_supplier\b/);
        assert.match(payload, /\blot:\s*active_lot\.value\b/);
        assert.match(payload, /\bplan:\s*active_plan\.value\b/);
    });
}
