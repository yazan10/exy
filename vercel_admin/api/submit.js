const GH_TOKEN = process.env.GH_TOKEN || "";
const GH_REPO = "yazan10/exy";
const INBOX_PATH = "admin/inbox.json";
const GH_API = "https://api.github.com/repos/" + GH_REPO;

function send(res, status, obj) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.end(JSON.stringify(obj));
}

async function readInbox() {
  const r = await fetch(`${GH_API}/contents/${INBOX_PATH}`, {
    headers: { Authorization: "Bearer " + GH_TOKEN, Accept: "application/vnd.github+json", "User-Agent": "YAZ-admin" },
  });
  if (!r.ok) throw new Error("read " + r.status);
  const j = await r.json();
  return { list: JSON.parse(Buffer.from(j.content, "base64").toString("utf-8")), sha: j.sha };
}

async function writeInbox(list, sha) {
  const r = await fetch(`${GH_API}/contents/${INBOX_PATH}`, {
    method: "PUT",
    headers: { Authorization: "Bearer " + GH_TOKEN, Accept: "application/vnd.github+json", "User-Agent": "YAZ-admin", "Content-Type": "application/json" },
    body: JSON.stringify({ message: "YAZ admin: receive " + new Date().toISOString(), content: Buffer.from(JSON.stringify(list, null, 2)).toString("base64"), sha: sha || undefined }),
  });
  if (!r.ok) throw new Error("write " + r.status + " " + (await r.text()).slice(0, 200));
  return true;
}

module.exports = async (req, res) => {
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    return res.end();
  }
  if (req.method !== "POST") return send(res, 405, { ok: false, error: "method" });

  let data = {};
  try {
    const body = await new Promise((resolve) => {
      let b = "";
      req.on("data", (c) => (b += c));
      req.on("end", () => resolve(b));
    });
    try { data = JSON.parse(body); } catch (e) { data = { text: body }; }
  } catch (e) { data = {}; }

  const serial = String(data.serial || data.text || "").trim();
  if (!serial) return send(res, 400, { ok: false, error: "no serial" });
  if (!GH_TOKEN) return send(res, 500, { ok: false, error: "no GH_TOKEN" });

  const entry = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    device: String(data.device || "").trim(),
    serial,
    note: String(data.note || "").trim(),
    time: data.time || new Date().toISOString(),
    received: new Date().toISOString(),
  };

  try {
    const { list, sha } = await readInbox();
    if (!Array.isArray(list.entries)) list.entries = [];
    if (!list.stats || typeof list.stats !== "object") list.stats = { received: 0, activated: 0, deleted: 0 };
    list.entries.push(entry);
    list.stats.received = (list.stats.received || 0) + 1;
    await writeInbox(list, sha);
    send(res, 200, { ok: true, serial, saved: list.entries.length });
  } catch (e) {
    send(res, 500, { ok: false, error: "store fail " + e.message });
  }
};