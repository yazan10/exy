const crypto = require("crypto");

const ADMIN_HASH = "3ffecb73c54aa67f3418bd7d8892c8f7391af31bddbaf11bccdc79ce23a550c0";
const SECRET = process.env.ADMIN_SECRET || (ADMIN_HASH + "::yaz-admin");
const GH_TOKEN = process.env.GH_TOKEN || "";
const GH_REPO = "yazan10/exy";
const GH_API = "https://api.github.com/repos/" + GH_REPO;

function sha256(s) {
  return crypto.createHash("sha256").update(String(s)).digest("hex");
}

function hmac(data) {
  return crypto.createHmac("sha256", SECRET).update(data).digest("base64url");
}

function makeToken() {
  const payload = Buffer.from(JSON.stringify({ exp: Date.now() + 12 * 3600 * 1000 })).toString("base64url");
  return payload + "." + hmac(payload);
}

function verifyToken(token) {
  try {
    const parts = String(token || "").split(".");
    if (parts.length !== 2) return false;
    const [b, sig] = parts;
    if (hmac(b) !== sig) return false;
    const p = JSON.parse(Buffer.from(b, "base64url").toString());
    return p.exp > Date.now();
  } catch (e) {
    return false;
  }
}

function readBody(req) {
  return new Promise((resolve) => {
    let b = "";
    req.on("data", (c) => (b += c));
    req.on("end", () => resolve(b));
  });
}

function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
}

function json(res, status, obj) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  cors(res);
  res.end(JSON.stringify(obj));
}

function options(res) {
  res.statusCode = 204;
  cors(res);
  res.end();
}

function authed(req, res) {
  const h = req.headers["authorization"] || "";
  const tok = h.startsWith("Bearer ") ? h.slice(7) : "";
  if (!verifyToken(tok)) {
    json(res, 401, { ok: false, error: "unauthorized" });
    return null;
  }
  return true;
}

async function ghGet(path) {
  const r = await fetch(`${GH_API}/contents/${path}`, {
    headers: { Authorization: "Bearer " + GH_TOKEN, Accept: "application/vnd.github+json", "User-Agent": "YAZ-admin" },
  });
  if (!r.ok) throw new Error("read " + r.status);
  const j = await r.json();
  return { data: JSON.parse(Buffer.from(j.content, "base64").toString("utf-8")), sha: j.sha };
}

async function ghPut(path, data, sha, msg) {
  const r = await fetch(`${GH_API}/contents/${path}`, {
    method: "PUT",
    headers: { Authorization: "Bearer " + GH_TOKEN, Accept: "application/vnd.github+json", "User-Agent": "YAZ-admin", "Content-Type": "application/json" },
    body: JSON.stringify({ message: msg || "YAZ admin update " + path, content: Buffer.from(JSON.stringify(data, null, 2)).toString("base64"), sha: sha || undefined }),
  });
  if (!r.ok) throw new Error("write " + r.status + " " + (await r.text()).slice(0, 200));
  return true;
}

module.exports = { sha256, makeToken, verifyToken, authed, readBody, json, options, ghGet, ghPut, GH_TOKEN, GH_API, ADMIN_HASH };