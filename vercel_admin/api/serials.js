const { authed, readBody, json, options, ghGet, ghPut } = require("./_shared");

const PATH = "server/serials.json";

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") return options(res);

  if (req.method === "GET") {
    try {
      const { data } = await ghGet(PATH);
      return json(res, 200, {
        ok: true,
        serials: data.serials || [],
        stats: data.stats || null,
      });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  if (req.method === "POST") {
    if (!authed(req, res)) return;
    try {
      const body = JSON.parse((await readBody(req)) || "{}");
      const { data, sha } = await ghGet(PATH);
      let serials = Array.isArray(data.serials) ? data.serials : [];
      let stats = data.stats && typeof data.stats === "object" ? data.stats : { added: 0, removed: 0 };
      let changed = false;

      const action = String(body.action || "add").toLowerCase();

      if (action === "add") {
        const s = String(body.serial || "").trim().toUpperCase();
        if (!s) return json(res, 400, { ok: false, error: "no serial" });
        if (!serials.includes(s)) { serials.push(s); stats.added++; changed = true; }
      } else if (action === "remove") {
        const s = String(body.serial || "").trim().toUpperCase();
        const before = serials.length;
        serials = serials.filter((x) => String(x).trim().toUpperCase() !== s);
        if (serials.length !== before) { stats.removed++; changed = true; }
      } else if (action === "set") {
        const arr = Array.isArray(body.serials) ? body.serials.map((x) => String(x).trim().toUpperCase()).filter(Boolean) : [];
        serials = arr;
        changed = true;
      } else {
        return json(res, 400, { ok: false, error: "bad action" });
      }

      if (changed) await ghPut(PATH, { serials, stats }, sha, "YAZ admin: update serials");
      return json(res, 200, { ok: true, serials, stats, changed });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  json(res, 405, { ok: false, error: "method" });
};