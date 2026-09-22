const { sha256, ADMIN_HASH, makeToken, readBody, json, options, cors } = require("./_shared");

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") return options(res);
  if (req.method !== "POST") return json(res, 405, { ok: false, error: "method" });

  let body = {};
  try { body = JSON.parse((await readBody(req)) || "{}"); } catch (e) {}
  const pass = String(body.password || "");

  if (!pass || sha256(pass) !== ADMIN_HASH) {
    return json(res, 401, { ok: false, error: "wrong password" });
  }
  json(res, 200, { ok: true, token: makeToken(), admin: true });
};