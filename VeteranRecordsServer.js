//Install these
//npm init -y
//npm install express sqlite3 ejs

const express = require("express");
const path = require("path");
const db = require("./db");

const app = express();
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.static("public"));

// Home page
app.get("/", (req, res) => {
    res.render("index");
});

// Search route
app.get("/search", (req, res) => {
    const q = req.query.q?.trim() || "";

    db.all(
        `
        SELECT id, name
        FROM burials
        WHERE name LIKE ?
        ORDER BY name
        LIMIT 100
        `,
        [`%${q}%`],
        (err, rows) => {
            if (err) return res.send("Database error");
            res.render("results", { rows, q });
        }
    );
});

// Detail page
app.get("/burial/:id", (req, res) => {
    const id = req.params.id;

    db.get(
        `
        SELECT b.name,
               w.name AS war,
               c.name AS cemetery,
               p.section, p.range, p.lot, p.grave
        FROM burials b
        LEFT JOIN wars w ON b.war_id = w.id
        LEFT JOIN plots p ON b.plot_id = p.id
        LEFT JOIN cemeteries c ON p.cemetery_id = c.id
        WHERE b.id = ?
        `,
        [id],
        (err, row) => {
            if (err) return res.send("Database error");
            if (!row) return res.send("Not found");
            res.render("detail", { row });
        }
    );
});

app.listen(3000, () => {
    console.log("Server running on http://localhost:3000");
});