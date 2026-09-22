const { authed, readBody, json, options, ghGet, ghPut } = require("./_shared");

const INBOX = "admin/inbox.json";
const SERIALS = "server/serials.json";

function normStats(s) {
  return s && typeof s === "object"
    ? { received: s.received || 0, activated: s.activated || 0, deleted: s.deleted || 0 }
    : { received: 0, activated: 0, deleted: 0 };
}

function findIdx(entries, id, serial) {
  if (id) {
    const i = entries.findIndex((e) => e.id === id);
    if (i !== -1) return i;
  }
  const s = String(serial || "").trim().toUpperCase();
  if (s) {
    const i = entries.findIndex((e) => String(e.serial || "").trim().toUpperCase() === s);
    if (i !== -1) return i;
  }
  return -1;
}

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") return options(res);

  if (req.method === "GET") {
    try {
      const [inb, reg] = await Promise.all([ghGet(INBOX), ghGet(SERIALS)]);
      return json(res, 200, {
        ok: true,
        entries: inb.data.entries || [],
        serials: reg.data.serials || [],
        stats: {
          ...normStats(inb.data.stats),
          serials_added: (reg.data.stats && reg.data.stats.added) || 0,
          serials_removed: (reg.data.stats && reg.data.stats.removed) || 0,
          total_serials: (reg.data.serials || []).length,
          total_requests: (inb.data.entries || []).length,
        },
      });
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
      const serialWant = String(body.serial || "").trim().toUpperCase();

      if (action !== "approve" && action !== "delete") {
        return json(res, 400, { ok: false, error: "bad action" });
      }

      const [inb, reg] = await Promise.all([ghGet(INBOX), ghGet(SERIALS)]);
      let entries = (inb.data.entries || []).slice();
      const serials = Array.isArray(reg.data.serials) ? reg.data.serials.slice() : [];
      const inStats = normStats(inb.data.stats);
      const regStats = reg.data.stats && typeof reg.data.stats === "object" ? reg.data.stats : { added: 0, removed: 0 };

      const idx = findIdx(entries, id, serialWant);
      const serial = idx !== -1 ? String(entries[idx].serial || "").trim().toUpperCase() : serialWant;

      if (!serial) return json(res, 400, { ok: false, error: "no serial" });

      if (action === "approve") {
        if (idx !== -1) {
          entries.splice(idx, 1);
          inStats.activated++;
          await ghPut(INBOX, { entries, stats: inStats }, inb.sha, "YAZ admin: approve request");
        } else if (!serials.includes(serial)) {
          return json(res, 404, { ok: false, error: "not found" });
        }

        if (!serials.includes(serial)) {
          serials.push(serial);
          regStats.added++;
          await ghPut(SERIALS, { serials, stats: regStats }, reg.sha, "YAZ admin: approve serial " + serial);
        }

        return json(res, 200, {
          ok: true,
          action,
          serial,
          added: true,
          message: "activated",
          serials: serials.length,
          pending: entries.length,
        });
      }

      // delete
      if (idx === -1) return json(res, 404, { ok: false, error: "not found" });
      entries.splice(idx, 1);
      inStats.deleted++;
      await ghPut(INBOX, { entries, stats: inStats }, inb.sha, "YAZ admin: delete request");
      return json(res, 200, { ok: true, action, deleted: serial, pending: entries.length });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  json(res, 405, { ok: false, error: "method" });
};