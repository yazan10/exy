export const config = { runtime: "nodejs" };

const GH_TOKEN = process.env.GH_TOKEN || "";
const GH_REPO = "yazan10/exy";
const INBOX_PATH = "admin/inbox.json";

const GH_API = "https://api.github.com/repos/" + GH_REPO;

async function ghHeaders(extra) {
  return {
    Authorization: "Bearer " + GH_TOKEN,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "YAZ-admin",
    ...extra,
  };
}

async function readInbox() {
  try {
    const r = await fetch(`${GH_API}/contents/${INBOX_PATH}`, {
      headers: await ghHeaders(),
    });
    if (!r.ok) throw new Error("github " + r.status);
    const j = await r.json();
    const content = Buffer.from(j.content, "base64").toString("utf-8");
    return { list: JSON.parse(content || '{"entries":[]}'), sha: j.sha };
  } catch (e) {
    return { list: { entries: [] }, sha: null, err: String(e) };
  }
}

async function writeInbox(list, sha) {
  const body = JSON.stringify({
    message: "YAZ admin: receive serial " + new Date().toISOString(),
    content: Buffer.from(JSON.stringify(list, null, 2)).toString("base64"),
    sha: sha || undefined,
  });
  const r = await fetch(`${GH_API}/contents/${INBOX_PATH}`, {
    method: "PUT",
    headers: await ghHeaders(),
    body,
  });
  if (!r.ok) throw new Error("github put " + r.status + " " + (await r.text()));
  return true;
}

export default async function handler(req) {
  if (req.method === "OPTIONS") {
    return new Response("", {
      headers: cors(),
    });
  }
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ ok: false, error: "method" }), {
      status: 405,
      headers: cors(),
    });
  }

  let data = {};
  try {
    const body = await req.text();
    const ct = (req.headers.get("content-type") || "").toLowerCase();
    try {
      data = JSON.parse(body);
    } catch (e) {
      data = { text: body };
    }
  } catch (e) {
    data = {};
  }

  const serial = String(data.serial || data.text || "").trim();
  if (!serial) {
    return new Response(JSON.stringify({ ok: false, error: "no serial" }), {
      status: 400,
      headers: cors(),
    });
  }

  const entry = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    device: String(data.device || "").trim(),
    serial: serial,
    note: String(data.note || "").trim(),
    time: data.time || new Date().toISOString(),
    received: new Date().toISOString(),
  };

  let inbox = { entries: [] };
  let sha = null;
  if (!GH_TOKEN) {
    return new Response(JSON.stringify({ ok: false, error: "no GH_TOKEN", entry }), {
      status: 500,
      headers: cors(),
    });
  }

  const got = await readInbox();
  inbox = got.list;
  sha = got.sha;
  if (!Array.isArray(inbox.entries)) inbox.entries = [];
  inbox.entries.push(entry);

  try {
    await writeInbox(inbox, sha);
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: "store fail " + e }), {
      status: 500,
      headers: cors(),
    });
  }

  return new Response(JSON.stringify({ ok: true, serial, saved: inbox.entries.length }), {
    status: 200,
    headers: cors(),
  });
}

function cors() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json; charset=utf-8",
  };
}