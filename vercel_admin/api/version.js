const { authed, readBody, json, options, ghGet, ghPut } = require("./_shared");

const PATH = "server/version.json";

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") return options(res);

  if (req.method === "GET") {
    try {
      const { data } = await ghGet(PATH);
      return json(res, 200, { ok: true, ...data });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  if (req.method === "POST") {
    if (!authed(req, res)) return;
    try {
      const body = JSON.parse((await readBody(req)) || "{}");
      const { data, sha } = await ghGet(PATH);

      const version = String(body.version || data.version || "").trim();
      if (!version) return json(res, 400, { ok: false, error: "no version" });

      data.version = version;
      if (body.min_version !== undefined) data.min_version = String(body.min_version).trim();
      if (body.mandatory !== undefined) data.mandatory = !!body.mandatory;
      if (body.url !== undefined) data.url = String(body.url).trim();
      if (body.notes !== undefined) data.notes = String(body.notes).trim();

      await ghPut(PATH, data, sha, "YAZ admin: set version " + version);
      return json(res, 200, { ok: true, ...data });
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e.message || e) });
    }
  }

  json(res, 405, { ok: false, error: "method" });
};