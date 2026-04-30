const sqlite3 = require("sqlite3").verbose();

const db = new sqlite3.Database("./veterans.db", sqlite3.OPEN_READONLY);

module.exports = db;