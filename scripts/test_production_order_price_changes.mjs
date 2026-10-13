import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const script_path = new URL("../essdee_yrp/public/js/production_order.js", import.meta.url);

function load_form_handlers() {
    let handlers;
    const context = {
        __: (value) => value,
        frappe: {
            ui: { form: { on(_doctype, registered) { handlers = registered; } } },
            user: { full_name: (user) => user || "Current Viewer" },
            datetime: { str_to_user: (value) => `formatted:${value}` },
            utils: {
                escape_html: (value) => String(value)
                    .replaceAll("&", "&amp;")
                    .replaceAll("<", "&lt;")
                    .replaceAll(">", "&gt;")
                    .replaceAll('"', "&quot;")
                    .replaceAll("'", "&#39;"),
            },
        },
    };
    vm.runInNewContext(fs.readFileSync(script_path, "utf8"), context);
    return handlers;
}

function make_form(price_requests) {
    let content = "";
    const wrapper = {
        html(value) {
            if (value === undefined) return content;
            content = String(value);
            return this;
        },
    };
    return {
        doc: { docstatus: 1, __onload: { price_requests } },
        fields_dict: { ppo_price_request_html: { $wrapper: wrapper } },
        price_html: () => wrapper.html(),
    };
}

test("refresh renders the Production Order price request history", () => {
    const frm = make_form([{
        name: "PPR-2026-00064",
        status: "Approved",
        requested_by: "sharmitha.p@essdee.fit",
        requested_at: "2026-07-13 15:29:35",
        approved_by: "approver@essdee.fit",
        approved_at: "2026-07-13 16:00:00",
    }]);

    load_form_handlers().refresh(frm);

    const html = frm.price_html();
    assert.match(html, /href="\/app\/sd-yrp-ppo-price-request\/PPR-2026-00064"/);
    assert.match(html, /indicator-pill green">Approved</);
    assert.match(html, /sharmitha\.p@essdee\.fit/);
    assert.match(html, /formatted:2026-07-13 15:29:35/);
    assert.match(html, /approver@essdee\.fit/);
    assert.match(html, /formatted:2026-07-13 16:00:00/);
});

test("refresh shows an explicit empty state when no price requests exist", () => {
    const frm = make_form([]);
    load_form_handlers().refresh(frm);
    assert.match(frm.price_html(), /No price change requests/);
});

test("price history carries a visible Price Changes heading like the history grids", () => {
    for (const requests of [[], [{ name: "PPR-1", status: "Pending" }]]) {
        const frm = make_form(requests);
        load_form_handlers().refresh(frm);
        assert.match(frm.price_html(), /<div class="control-label">Price Changes<\/div>/);
    }
});

test("price request history escapes values and encodes request links", () => {
    const frm = make_form([{
        name: "PPR 64/evil",
        status: "<Approved>",
        requested_by: "<requester@example.com>",
        requested_at: "2026<date>",
        approved_by: "Approver & Co",
        approved_at: "2026<approved>",
    }]);

    load_form_handlers().refresh(frm);

    const html = frm.price_html();
    assert.match(html, /href="\/app\/sd-yrp-ppo-price-request\/PPR%2064%2Fevil"/);
    assert.match(html, /&lt;Approved&gt;/);
    assert.match(html, /&lt;requester@example\.com&gt;/);
    assert.match(html, /Approver &amp; Co/);
    assert.match(html, /formatted:2026&lt;approved&gt;/);
    assert.doesNotMatch(html, /<Approved>|<requester@example\.com>|Approver & Co/);
});

test("missing requester data is not attributed to the current viewer", () => {
    const frm = make_form([{ name: "PPR-LEGACY", status: "Approved" }]);
    load_form_handlers().refresh(frm);
    assert.doesNotMatch(frm.price_html(), /Current Viewer/);
});
