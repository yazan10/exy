module.exports = (req, res) => {
  res.statusCode = 200;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.end(JSON.stringify({ ok: true, t: new Date().toISOString(), token: process.env.GH_TOKEN ? "GH_TOKEN-set" : "no-GH_TOKEN" }));
};