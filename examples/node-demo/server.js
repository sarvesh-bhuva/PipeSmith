const express = require("express");
const _ = require("lodash");

const app = express();
app.get("/", (_req, res) => res.json(_.pick({ app: "pipesmith-node-demo", ok: true }, ["app", "ok"])));
app.listen(process.env.PORT || 3000);
