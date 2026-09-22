const { authed, readBody, json, options, ghGet, ghPut } = require("./_shared");

const INBOX = "admin/inbox.json";
const SERIALS = "server/serials.json";

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") return options(res);

  if (req.method === "GET") {
    try {
      const [inb, reg] = await Promise.all([ghGet(INBOX), ghGet(SERIALS)]);
      return json(res, 200, { ok: true, entries: inb.data.entries || [], serials: reg.data.serials || [] });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  if (req.method === "POST") {
    if (!authed(req, res)) return;
    try {
      const body = JSON.parse((await readBody(req)) || "{}");
      const action = String(body.action || "").toLowerCase();
      const id = String(body.id || "");

      const [inb, reg] = await Promise.all([ghGet(INBOX), ghGet(SERIALS)]);
      const entries = (inb.data.entries || []).slice();
      const serials = Array.isArray(reg.data.serials) ? reg.data.serials.slice() : [];
      let result = { ok: true, action };

      const idx = entries.findIndex((e) => e.id === id);

      if (action === "delete") {
        if (idx === -1) return json(res, 404, { ok: false, error: "not found" });
        entries.splice(idx, 1);
        await ghPut(INBOX, { entries }, inb.sha, "YAZ admin: delete request");
        result.entries = entries.length;
        return json(res, 200, result);
      }

      if (action === "approve") {
        if (idx === -1) return json(res, 404, { ok: false, error: "not found" });
        const serial = String(entries[idx].serial || "").trim().toUpperCase();
        if (!serial) return json(res, 400, { ok: false, error: "no serial" });

        const [inb2] = await Promise.all([ghGet(INBOX)]);
        const e2 = (inb2.data.entries || []).slice();
        const idx2 = e2.findIndex((x) => x.id === id);
        if (idx2 !== -1) {
          e2.splice(idx2, 1);
          await ghPut(INBOX, { entries: e2 }, inb2.sha, "YAZ admin: approve request");
        }

        if (!serials.includes(serial)) serials.push(serial);
        await ghPut(SERIALS, { serials }, reg.sha, "YAZ admin: approve serial " + serial);
        result.serial = serial;
        result.serials = serials.length;
        return json(res, 200, result);
      }

      json(res, 400, { ok: false, error: "bad action" });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  json(res, 405, { ok: false, error: "method" });
};