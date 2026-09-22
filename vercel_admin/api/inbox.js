const API = "https://api.github.com/repos/yazan10/exy/contents";

function ghRaw(path) {
  return fetch(`${API}/${path}`, {
    headers: { Accept: "application/vnd.github.raw+json", "User-Agent": "YAZ-admin" },
  }).then((r) => {
    if (!r.ok) throw new Error(path + " " + r.status);
    return r.json();
  });
}

module.exports = async (req, res) => {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  try {
    const [inbox, serials] = await Promise.all([
      ghRaw("admin/inbox.json"),
      ghRaw("server/serials.json"),
    ]);
    res.end(JSON.stringify({ entries: inbox.entries || [], serials: serials.serials || [] }));
  } catch (e) {
    res.statusCode = 502;
    res.end(JSON.stringify({ error: String(e.message || e) }));
  }
};