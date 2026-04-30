// npm init -y
// npm install express sqlite3

const express = require("express");
const path    = require("path");
const db      = require("./db");

const app = express();
app.use(express.static(path.join(__dirname, "public")));

// API: search — GET /api/search?q=name&war=Vietnam&war=Korea
app.get("/api/search", (req, res) => {
    const q    = (req.query.q || "").trim();
    const wars = [].concat(req.query.war || []).filter(Boolean);

    let sql      = `SELECT id, name, war, branch_of_service, date_of_death, burial_location
                    FROM veterans WHERE name LIKE ?`;
    const params = [`%${q}%`];

    if (wars.length > 0) {
        const placeholders = wars.map(() => "?").join(", ");
        sql += ` AND war IN (${placeholders})`;
        params.push(...wars);
    }

    sql += " ORDER BY name LIMIT 100";

    db.all(sql, params, (err, rows) => {
        if (err) { console.error(err); return res.status(500).json({ error: "Database error." }); }
        res.json(rows);
    });
});

// API: single record — GET /api/veteran/:id
app.get("/api/veteran/:id", (req, res) => {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) return res.status(400).json({ error: "Invalid ID." });

    db.get(
        `SELECT id, name, date_of_birth, date_of_death, war, branch_of_service, burial_location
         FROM veterans WHERE id = ?`,
        [id],
        (err, row) => {
            if (err) { console.error(err); return res.status(500).json({ error: "Database error." }); }
            if (!row) return res.status(404).json({ error: "Record not found." });
            res.json(row);
        }
    );
});

// All other routes serve the single-page
app.use((req, res) => {
    res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(3000, () => {
    console.log("Server running at http://localhost:3000");
});