# Smart Beverage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragmented water/tea/caffeine tracking with a unified smart beverage system that auto-calculates nutritional values.

**Architecture:** New `beverage_log` table with per-serving nutritional data. A `BEVERAGES` dict defines drink types. Bot gets a single "Beverages" menu button that opens an inline keyboard. Old data migrates to the new table. Reports read from `beverage_log` instead of old fields.

**Tech Stack:** Python, SQLite, pyTelegramBotAPI, pytest

---

## File Structure

- **Modify:** `db.py` — Add `BEVERAGES` dict, `beverage_log` table creation, beverage CRUD functions, migration logic
- **Modify:** `bot.py` — Replace tea/water buttons with beverage menu, add inline keyboard handler, remove old flow steps
- **Modify:** `reports.py` — Update daily/weekly/monthly summaries and correlations to use `beverage_log`
- **Modify:** `tests/test_db.py` — Tests for new DB functions
- **Modify:** `tests/test_bot.py` — Tests for beverage menu handler
- **Modify:** `tests/test_reports.py` — Tests for updated reports

---

### Task 1: Add BEVERAGES dict and beverage_log table to db.py

**Files:**
- Modify: `db.py:1-116`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for beverage_log table creation**

```python
# Add to tests/test_db.py

def test_init_db_creates_beverage_log_table():
    db.init_db()
    with db.get_connection() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='beverage_log'"
        )
        assert cur.fetchone() is not None


def test_beverage_log_table_has_expected_columns():
    db.init_db()
    with db.get_connection() as conn:
        cur = conn.execute("PRAGMA table_info(beverage_log)")
        columns = {row[1] for row in cur.fetchall()}
    expected = {"id", "user_id", "beverage_id", "servings", "water_ml",
                "caffeine_mg", "sugar_g", "calories", "date", "timestamp"}
    assert expected == columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py::test_init_db_creates_beverage_log_table tests/test_db.py::test_beverage_log_table_has_expected_columns -v`
Expected: FAIL — table does not exist

- [ ] **Step 3: Add BEVERAGES dict and beverage_log table to db.py**

Add after the `SCHEMA` string (around line 70):

```python
BEVERAGES = {
    "water":     {"emoji": "\U0001f4a7", "label_fa": "آب",       "water_ml": 125, "caffeine_mg": 0,  "sugar_g": 0,  "calories": 0},
    "tea":       {"emoji": "\U0001f375", "label_fa": "چای",      "water_ml": 124, "caffeine_mg": 26, "sugar_g": 0,  "calories": 1},
    "green_tea": {"emoji": "\U0001f375", "label_fa": "چای سبز",  "water_ml": 124, "caffeine_mg": 15, "sugar_g": 0,  "calories": 1},
    "coffee":    {"emoji": "☕",         "label_fa": "قهوه",     "water_ml": 124, "caffeine_mg": 50, "sugar_g": 0,  "calories": 1},
    "soda":      {"emoji": "\U0001f964", "label_fa": "نوشابه",   "water_ml": 112, "caffeine_mg": 8,  "sugar_g": 13, "calories": 53},
    "na_beer":   {"emoji": "\U0001f37a", "label_fa": "آبجو",     "water_ml": 117, "caffeine_mg": 0,  "sugar_g": 4,  "calories": 18},
    "delster":   {"emoji": "\U0001f37a", "label_fa": "دلستر",    "water_ml": 112, "caffeine_mg": 0,  "sugar_g": 10, "calories": 45},
    "juice":     {"emoji": "\U0001f9c3", "label_fa": "آبمیوه",   "water_ml": 110, "caffeine_mg": 0,  "sugar_g": 11, "calories": 56},
    "milk":      {"emoji": "\U0001f95b", "label_fa": "شیر",      "water_ml": 110, "caffeine_mg": 0,  "sugar_g": 6,  "calories": 78},
    "herbal":    {"emoji": "\U0001f33f", "label_fa": "دمنوش",    "water_ml": 124, "caffeine_mg": 0,  "sugar_g": 0,  "calories": 1},
}
```

Add to the `SCHEMA` string, before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS beverage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    beverage_id TEXT NOT NULL,
    servings REAL NOT NULL DEFAULT 1,
    water_ml REAL NOT NULL,
    caffeine_mg REAL NOT NULL,
    sugar_g REAL NOT NULL,
    calories REAL NOT NULL,
    date TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py::test_init_db_creates_beverage_log_table tests/test_db.py::test_beverage_log_table_has_expected_columns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add BEVERAGES dict and beverage_log table schema"
```

---

### Task 2: Add beverage CRUD functions to db.py

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for insert_beverage**

```python
# Add to tests/test_db.py
from datetime import timezone

def test_insert_beverage_returns_row_id():
    db.init_db()
    row_id = db.insert_beverage(user_id=1, beverage_id="tea")
    assert row_id == 1


def test_insert_beverage_calculates_nutrition():
    db.init_db()
    db.insert_beverage(user_id=1, beverage_id="tea")
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM beverage_log WHERE id = 1").fetchone()
    assert row["beverage_id"] == "tea"
    assert row["servings"] == 1
    assert row["water_ml"] == 124
    assert row["caffeine_mg"] == 26
    assert row["sugar_g"] == 0
    assert row["calories"] == 1


def test_insert_beverage_custom_servings():
    db.init_db()
    db.insert_beverage(user_id=1, beverage_id="coffee", servings=3)
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM beverage_log WHERE id = 1").fetchone()
    assert row["servings"] == 3
    assert row["caffeine_mg"] == 150  # 50 * 3
    assert row["water_ml"] == 372     # 124 * 3


def test_insert_beverage_sets_date():
    db.init_db()
    ts = datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
    db.insert_beverage(user_id=1, beverage_id="water", timestamp=ts)
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM beverage_log WHERE id = 1").fetchone()
    assert row["date"] == "2026-03-15"
    assert row["timestamp"] == "2026-03-15 10:30:00"


def test_insert_beverage_invalid_beverage_id():
    db.init_db()
    with pytest.raises(ValueError, match="Unknown beverage"):
        db.insert_beverage(user_id=1, beverage_id="unknown_drink")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k "test_insert_beverage" -v`
Expected: FAIL — `insert_beverage` not defined

- [ ] **Step 3: Implement insert_beverage**

Add to `db.py` after the existing beverage-related functions (after `get_today_water_glasses`):

```python
def insert_beverage(
    user_id: int,
    beverage_id: str,
    servings: float = 1,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a beverage log entry. Calculates nutrition from BEVERAGES dict."""
    if beverage_id not in BEVERAGES:
        raise ValueError(f"Unknown beverage: {beverage_id}")
    bev = BEVERAGES[beverage_id]
    ts = (timestamp or datetime.now(timezone.utc))
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    date_str = ts.strftime("%Y-%m-%d")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO beverage_log "
            "(user_id, beverage_id, servings, water_ml, caffeine_mg, sugar_g, calories, date, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, beverage_id, servings,
                bev["water_ml"] * servings,
                bev["caffeine_mg"] * servings,
                bev["sugar_g"] * servings,
                bev["calories"] * servings,
                date_str, ts_str,
            ),
        )
        conn.commit()
        return cur.lastrowid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k "test_insert_beverage" -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for query functions**

```python
# Add to tests/test_db.py

def test_get_today_beverages():
    db.init_db()
    ts = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts)
    db.insert_beverage(user_id=1, beverage_id="water", servings=2, timestamp=ts)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts)
    rows = db.get_today_beverages(user_id=1, date_str="2026-03-15")
    assert len(rows) == 3


def test_get_today_beverages_filters_by_date():
    db.init_db()
    ts1 = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts1)
    db.insert_beverage(user_id=1, beverage_id="water", timestamp=ts2)
    rows = db.get_today_beverages(user_id=1, date_str="2026-03-15")
    assert len(rows) == 1


def test_get_today_beverage_totals():
    db.init_db()
    ts = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts)
    db.insert_beverage(user_id=1, beverage_id="coffee", timestamp=ts)
    totals = db.get_today_beverage_totals(user_id=1, date_str="2026-03-15")
    assert totals["total_caffeine_mg"] == 26 + 26 + 50
    assert totals["total_water_ml"] == 124 + 124 + 124
    assert totals["per_beverage"]["tea"] == 2
    assert totals["per_beverage"]["coffee"] == 1


def test_get_today_beverage_totals_empty_day():
    db.init_db()
    totals = db.get_today_beverage_totals(user_id=1, date_str="2026-03-15")
    assert totals["total_caffeine_mg"] == 0
    assert totals["total_water_ml"] == 0
    assert totals["per_beverage"] == {}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k "test_get_today_beverage" -v`
Expected: FAIL — functions not defined

- [ ] **Step 7: Implement query functions**

Add to `db.py` after `insert_beverage`:

```python
def get_today_beverages(user_id: int, date_str: str) -> list[sqlite3.Row]:
    """Return all beverage_log rows for a given date."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM beverage_log WHERE user_id = ? AND date = ?",
            (user_id, date_str),
        )
        return list(cur.fetchall())


def get_today_beverage_totals(user_id: int, date_str: str) -> dict:
    """Return aggregated beverage totals for a given date."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT COALESCE(SUM(water_ml), 0) as total_water_ml, "
            "COALESCE(SUM(caffeine_mg), 0) as total_caffeine_mg, "
            "COALESCE(SUM(sugar_g), 0) as total_sugar_g, "
            "COALESCE(SUM(calories), 0) as total_calories "
            "FROM beverage_log WHERE user_id = ? AND date = ?",
            (user_id, date_str),
        )
        row = cur.fetchone()
        cur2 = conn.execute(
            "SELECT beverage_id, SUM(servings) as total_servings "
            "FROM beverage_log WHERE user_id = ? AND date = ? "
            "GROUP BY beverage_id",
            (user_id, date_str),
        )
        per_beverage = {r["beverage_id"]: r["total_servings"] for r in cur2.fetchall()}
    return {
        "total_water_ml": row["total_water_ml"],
        "total_caffeine_mg": row["total_caffeine_mg"],
        "total_sugar_g": row["total_sugar_g"],
        "total_calories": row["total_calories"],
        "per_beverage": per_beverage,
    }
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k "test_get_today_beverage" -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add insert_beverage and beverage query functions"
```

---

### Task 3: Add beverage data for date range queries (for reports)

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_db.py

def test_get_beverages_by_date_range():
    db.init_db()
    ts1 = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    ts3 = datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts1)
    db.insert_beverage(user_id=1, beverage_id="water", timestamp=ts2)
    db.insert_beverage(user_id=1, beverage_id="coffee", timestamp=ts3)
    rows = db.get_beverages_by_date_range(user_id=1, start_date="2026-03-10", end_date="2026-03-16")
    assert len(rows) == 2


def test_get_daily_beverage_totals_by_range():
    db.init_db()
    ts1 = datetime(2026, 3, 10, 8, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc)
    ts3 = datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts1)
    db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts2)
    db.insert_beverage(user_id=1, beverage_id="coffee", timestamp=ts3)
    result = db.get_daily_beverage_totals_by_range(user_id=1, start_date="2026-03-10", end_date="2026-03-12")
    assert "2026-03-10" in result
    assert result["2026-03-10"]["total_caffeine_mg"] == 52  # 26 * 2
    assert "2026-03-11" in result
    assert result["2026-03-11"]["total_caffeine_mg"] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k "test_get_beverages_by_date_range or test_get_daily_beverage_totals" -v`
Expected: FAIL

- [ ] **Step 3: Implement functions**

Add to `db.py`:

```python
def get_beverages_by_date_range(
    user_id: int, start_date: str, end_date: str,
) -> list[sqlite3.Row]:
    """Return beverage_log rows within [start_date, end_date)."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM beverage_log WHERE user_id = ? AND date >= ? AND date < ? "
            "ORDER BY timestamp ASC",
            (user_id, start_date, end_date),
        )
        return list(cur.fetchall())


def get_daily_beverage_totals_by_range(
    user_id: int, start_date: str, end_date: str,
) -> dict[str, dict]:
    """Return per-day aggregated beverage totals for a date range."""
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT date, "
            "SUM(water_ml) as total_water_ml, "
            "SUM(caffeine_mg) as total_caffeine_mg, "
            "SUM(sugar_g) as total_sugar_g, "
            "SUM(calories) as total_calories "
            "FROM beverage_log WHERE user_id = ? AND date >= ? AND date < ? "
            "GROUP BY date",
            (user_id, start_date, end_date),
        )
        result = {}
        for row in cur.fetchall():
            result[row["date"]] = {
                "total_water_ml": row["total_water_ml"],
                "total_caffeine_mg": row["total_caffeine_mg"],
                "total_sugar_g": row["total_sugar_g"],
                "total_calories": row["total_calories"],
            }
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k "test_get_beverages_by_date_range or test_get_daily_beverage_totals" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add beverage date range query functions for reports"
```

---

### Task 4: Add data migration function

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for migration**

```python
# Add to tests/test_db.py

def test_migrate_beverages_tea_count():
    db.init_db()
    db.insert_log(user_id=1, tea_count=3)
    db.migrate_legacy_beverages()
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(rows) == 1
    assert rows[0]["beverage_id"] == "tea"
    assert rows[0]["servings"] == 3


def test_migrate_beverages_water_glasses():
    db.init_db()
    db.insert_log(user_id=1, water_glasses=2.5)
    db.migrate_legacy_beverages()
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(rows) == 1
    assert rows[0]["beverage_id"] == "water"
    assert rows[0]["servings"] == 2.5


def test_migrate_beverages_water_amount():
    db.init_db()
    db.insert_log(user_id=1, water_amount=4)
    db.migrate_legacy_beverages()
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(rows) == 1
    assert rows[0]["beverage_id"] == "water"
    assert rows[0]["servings"] == 8  # 4 glasses * 2 half-glasses


def test_migrate_beverages_caffeine_amount():
    db.init_db()
    db.insert_log(user_id=1, caffeine_amount=2)
    db.migrate_legacy_beverages()
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(rows) == 1
    assert rows[0]["beverage_id"] == "tea"
    assert rows[0]["servings"] == 4  # 2 cups * 2 half-cups


def test_migrate_beverages_double_count_guard_water():
    """When both water_amount and water_glasses exist, only migrate water_amount."""
    db.init_db()
    db.insert_log(user_id=1, water_amount=5, water_glasses=2)
    db.migrate_legacy_beverages()
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    water_rows = [r for r in rows if r["beverage_id"] == "water"]
    assert len(water_rows) == 1
    assert water_rows[0]["servings"] == 10  # from water_amount only


def test_migrate_beverages_double_count_guard_tea():
    """When both caffeine_amount and tea_count exist, only migrate caffeine_amount."""
    db.init_db()
    db.insert_log(user_id=1, caffeine_amount=3, tea_count=2)
    db.migrate_legacy_beverages()
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    tea_rows = [r for r in rows if r["beverage_id"] == "tea"]
    assert len(tea_rows) == 1
    assert tea_rows[0]["servings"] == 6  # from caffeine_amount only


def test_migrate_beverages_idempotent():
    db.init_db()
    db.insert_log(user_id=1, tea_count=2)
    db.migrate_legacy_beverages()
    db.migrate_legacy_beverages()  # run again
    rows = db.get_today_beverages(user_id=1, date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(rows) == 1  # not duplicated
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -k "test_migrate_beverages" -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Implement migrate_legacy_beverages**

Add to `db.py`:

```python
def migrate_legacy_beverages() -> int:
    """One-time migration of legacy tea/water/caffeine data to beverage_log.
    Returns number of rows migrated. Idempotent — skips if data already exists."""
    with get_connection() as conn:
        # Check if migration already ran
        existing = conn.execute("SELECT COUNT(*) as cnt FROM beverage_log").fetchone()["cnt"]
        if existing > 0:
            return 0

        cur = conn.execute(
            "SELECT id, user_id, timestamp, tea_count, water_glasses, "
            "water_amount, caffeine_amount FROM logs "
            "WHERE tea_count > 0 OR water_glasses > 0 OR water_amount > 0 OR caffeine_amount > 0"
        )
        rows = cur.fetchall()
        count = 0
        for row in rows:
            ts_str = row["timestamp"]
            date_str = ts_str[:10]
            user_id = row["user_id"]
            tea_count = row["tea_count"] or 0
            water_glasses = row["water_glasses"] or 0
            water_amount = row["water_amount"] or 0
            caffeine_amount = row["caffeine_amount"] or 0

            # Double-count guard: prefer water_amount over water_glasses
            if water_amount > 0:
                servings = water_amount * 2
                bev = BEVERAGES["water"]
                conn.execute(
                    "INSERT INTO beverage_log "
                    "(user_id, beverage_id, servings, water_ml, caffeine_mg, sugar_g, calories, date, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, "water", servings,
                     bev["water_ml"] * servings, bev["caffeine_mg"] * servings,
                     bev["sugar_g"] * servings, bev["calories"] * servings,
                     date_str, ts_str),
                )
                count += 1
            elif water_glasses > 0:
                bev = BEVERAGES["water"]
                conn.execute(
                    "INSERT INTO beverage_log "
                    "(user_id, beverage_id, servings, water_ml, caffeine_mg, sugar_g, calories, date, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, "water", water_glasses,
                     bev["water_ml"] * water_glasses, bev["caffeine_mg"] * water_glasses,
                     bev["sugar_g"] * water_glasses, bev["calories"] * water_glasses,
                     date_str, ts_str),
                )
                count += 1

            # Double-count guard: prefer caffeine_amount over tea_count
            if caffeine_amount > 0:
                servings = caffeine_amount * 2
                bev = BEVERAGES["tea"]
                conn.execute(
                    "INSERT INTO beverage_log "
                    "(user_id, beverage_id, servings, water_ml, caffeine_mg, sugar_g, calories, date, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, "tea", servings,
                     bev["water_ml"] * servings, bev["caffeine_mg"] * servings,
                     bev["sugar_g"] * servings, bev["calories"] * servings,
                     date_str, ts_str),
                )
                count += 1
            elif tea_count > 0:
                bev = BEVERAGES["tea"]
                conn.execute(
                    "INSERT INTO beverage_log "
                    "(user_id, beverage_id, servings, water_ml, caffeine_mg, sugar_g, calories, date, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, "tea", tea_count,
                     bev["water_ml"] * tea_count, bev["caffeine_mg"] * tea_count,
                     bev["sugar_g"] * tea_count, bev["calories"] * tea_count,
                     date_str, ts_str),
                )
                count += 1

        conn.commit()
        return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -k "test_migrate_beverages" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add legacy beverage data migration function"
```

---

### Task 5: Update bot.py — beverage menu and inline keyboard

**Files:**
- Modify: `bot.py:89-94` (FLOWS), `bot.py:353-370` (main_menu_keyboard), `bot.py:1058-1084` (tea/water handlers)
- Test: `tests/test_bot.py`

- [ ] **Step 1: Write failing tests for beverage keyboard and handler**

```python
# Add to tests/test_bot.py

def test_beverage_keyboard_layout(isolated_db):
    kb = bot._beverage_kb(user_id=1)
    # Should be an InlineKeyboardMarkup
    assert hasattr(kb, "keyboard")
    # Row 1: water and tea (2 buttons)
    assert len(kb.keyboard[0]) == 2
    # Row 2: coffee, soda, na_beer (3 buttons)
    assert len(kb.keyboard[1]) == 3
    # Row 3: delster, juice, milk (3 buttons)
    assert len(kb.keyboard[2]) == 3
    # Row 4: green_tea, herbal (2 buttons)
    assert len(kb.keyboard[3]) == 2


def test_beverage_keyboard_shows_today_counts(isolated_db):
    ts = datetime(2026, 3, 15, 10, 0, 0)
    with patch.object(bot, "_today_str", return_value="2026-03-15"):
        db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts)
        db.insert_beverage(user_id=1, beverage_id="tea", timestamp=ts)
        kb = bot._beverage_kb(user_id=1)
    # Tea button (row 0, col 1) should show count 2
    tea_btn = kb.keyboard[0][1]
    assert "(2)" in tea_btn.text


def test_main_menu_has_beverage_button():
    kb = bot.main_menu_keyboard()
    all_buttons = [btn.text for row in kb.keyboard for btn in row]
    assert "🥤 نوشیدنی" in all_buttons
    assert "🍵 چای" not in all_buttons
    assert "💧 آب" not in all_buttons
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot.py -k "test_beverage_keyboard or test_main_menu_has_beverage" -v`
Expected: FAIL

- [ ] **Step 3: Update main_menu_keyboard — remove tea/water, add beverage**

In `bot.py`, modify `main_menu_keyboard()` (around line 353):

```python
def main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("📝 ثبت داده"))
    markup.row(types.KeyboardButton("📊 گزارش"))
    markup.row(
        types.KeyboardButton("🔥 درد الان"),
        types.KeyboardButton("🚬 سیگار"),
    )
    markup.row(
        types.KeyboardButton("🥤 نوشیدنی"),
        types.KeyboardButton("🏃 ورزش"),
    )
    markup.row(
        types.KeyboardButton("📋 بیشتر"),
        types.KeyboardButton("↩️"),
    )
    return markup
```

- [ ] **Step 4: Add _beverage_kb function**

Add to `bot.py` near the keyboard functions section:

```python
# Beverage menu layout: list of rows, each row is a list of beverage_ids
_BEVERAGE_LAYOUT = [
    ["water", "tea"],
    ["coffee", "soda", "na_beer"],
    ["delster", "juice", "milk"],
    ["green_tea", "herbal"],
]


def _beverage_kb(user_id: int) -> types.InlineKeyboardMarkup:
    """Build inline keyboard for beverage selection with today's counts."""
    today = _today_str(user_id)
    totals = database.get_today_beverage_totals(user_id, today)
    per_bev = totals["per_beverage"]

    markup = types.InlineKeyboardMarkup()
    for row_ids in _BEVERAGE_LAYOUT:
        buttons = []
        for bev_id in row_ids:
            bev = database.BEVERAGES[bev_id]
            count = int(per_bev.get(bev_id, 0))
            label = f"{bev['emoji']} {bev['label_fa']} ({count})"
            buttons.append(types.InlineKeyboardButton(label, callback_data=f"bev_{bev_id}"))
        markup.row(*buttons)
    return markup
```

- [ ] **Step 5: Add beverage button handler and callback handler**

Replace the `handle_tea` and `handle_water` handlers in `bot.py` with:

```python
@bot.message_handler(func=lambda m: m.text == "🥤 نوشیدنی")
def handle_beverage_menu(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    uid = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🥤 <b>نوشیدنی انتخاب کن:</b>",
        reply_markup=_beverage_kb(uid),
    )
```

Add a new callback handler:

```python
@bot.callback_query_handler(func=lambda c: c.data.startswith("bev_"))
def handle_beverage_callback(call: types.CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی نداری.")
        return
    bev_id = call.data[4:]
    if bev_id not in database.BEVERAGES:
        bot.answer_callback_query(call.id, "نوشیدنی نامعتبر.")
        return
    uid = call.from_user.id
    database.insert_beverage(user_id=uid, beverage_id=bev_id)
    today = _today_str(uid)
    totals = database.get_today_beverage_totals(uid, today)
    count = int(totals["per_beverage"].get(bev_id, 0))
    bev = database.BEVERAGES[bev_id]
    bot.answer_callback_query(call.id, f"{bev['emoji']} +۱")
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_beverage_kb(uid),
        )
    except Exception:
        pass
```

- [ ] **Step 6: Remove old tea/water handlers**

Delete `handle_tea` (lines 1058-1069) and `handle_water` (lines 1072-1084) functions entirely.

- [ ] **Step 7: Remove water_amount and caffeine_amount from log flow**

In `bot.py`, update FLOWS dict (line 89-95):

```python
FLOWS: dict[str, list[str]] = {
    "log": [
        "sleep_quality", "sleep_hours", "back_pain", "headache",
        "peace_level",
        "food_details",
        "phone_hours", "computer_hours", "sitting_hours", "knitting_hours", "notes",
    ],
    # ... rest unchanged
}
```

Also remove `water_amount` and `caffeine_amount` from:
- `STEP_VALID_RANGE` (lines 116-117)
- `QUESTIONS` (lines 135, 137)
- `STEP_LABELS` (lines 160, 162)
- `STEP_UNITS` (lines 181-182)
- `_EDITABLE_FIELDS` (lines 801-805)
- `_finish_flow` — remove `water_amount` and `caffeine_amount` from the `insert_log` call (lines 546-547)
- `_generate_feedback` — remove water_amount feedback (lines 513-517)

- [ ] **Step 8: Run all tests to verify they pass**

Run: `pytest tests/test_bot.py -v`
Expected: PASS (some existing tests that reference tea/water buttons will need updating — adjust assertions)

- [ ] **Step 9: Commit**

```bash
git add bot.py tests/test_bot.py
git commit -m "feat: replace tea/water buttons with unified beverage menu"
```

---

### Task 6: Update reports.py — daily summary

**Files:**
- Modify: `reports.py:259-367`
- Test: `tests/test_reports.py`

- [ ] **Step 1: Write failing test for new daily summary beverage section**

```python
# Add to tests/test_reports.py

def test_daily_summary_shows_beverages():
    beverages = [
        {"beverage_id": "tea", "servings": 2, "water_ml": 248, "caffeine_mg": 52, "sugar_g": 0, "calories": 2},
        {"beverage_id": "water", "servings": 4, "water_ml": 500, "caffeine_mg": 0, "sugar_g": 0, "calories": 0},
        {"beverage_id": "coffee", "servings": 1, "water_ml": 124, "caffeine_mg": 50, "sugar_g": 0, "calories": 1},
    ]
    result = reports.generate_daily_summary([], [], [], beverages=beverages)
    assert "نوشیدنی" in result
    assert "چای" in result
    assert "آب" in result
    assert "قهوه" in result
    assert "کافئین" in result or "caffeine" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reports.py::test_daily_summary_shows_beverages -v`
Expected: FAIL

- [ ] **Step 3: Update generate_daily_summary to accept beverages parameter**

In `reports.py`, modify `generate_daily_summary` signature and add beverage section:

```python
def generate_daily_summary(logs: list, medications: list, exercises: list, *, beverages: list | None = None) -> str:
```

Remove old water/tea/caffeine display logic (lines ~272-274 for `water_amount`/`caffeine_amount` in fields list, lines ~282-316 for `total_tea`/`total_water_glasses`).

Add at the end before medications section:

```python
    if beverages:
        lines.append("\n🥤 نوشیدنی‌ها:")
        total_water_ml = 0
        total_caffeine_mg = 0
        total_sugar_g = 0
        total_calories = 0
        for bev in beverages:
            bev_id = bev["beverage_id"] if isinstance(bev, dict) else bev["beverage_id"]
            bev_info = BEVERAGES.get(bev_id, {})
            servings = bev["servings"]
            half_glasses = int(servings) if servings == int(servings) else servings
            glasses = servings / 2
            glasses_display = int(glasses) if glasses == int(glasses) else glasses
            label = bev_info.get("label_fa", bev_id)
            emoji = bev_info.get("emoji", "")
            lines.append(f"{emoji} {label}: {glasses_display} لیوان")
            total_water_ml += bev["water_ml"]
            total_caffeine_mg += bev["caffeine_mg"]
            total_sugar_g += bev["sugar_g"]
            total_calories += bev["calories"]
        lines.append(
            f"── مجموع: آب {int(total_water_ml)}ml | "
            f"کافئین {int(total_caffeine_mg)}mg | "
            f"قند {int(total_sugar_g)}g | "
            f"{int(total_calories)}kcal"
        )
```

Add at top of reports.py:
```python
from db import BEVERAGES
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reports.py::test_daily_summary_shows_beverages -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reports.py tests/test_reports.py
git commit -m "feat: add beverage section to daily summary report"
```

---

### Task 7: Update reports.py — weekly/monthly reports and correlations

**Files:**
- Modify: `reports.py:161-257` (weekly/monthly), `reports.py:370-459` (correlations)
- Test: `tests/test_reports.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_reports.py

def test_weekly_report_shows_beverage_totals():
    result = reports.generate_weekly_report(
        [], [], [], [],
        beverage_totals={"total_water_ml": 5000, "total_caffeine_mg": 300, "total_sugar_g": 50},
        prev_beverage_totals={"total_water_ml": 4000, "total_caffeine_mg": 250, "total_sugar_g": 40},
    )
    assert "آب" in result or "water" in result.lower()
    assert "کافئین" in result


def test_correlation_uses_beverage_data():
    daily_beverage = {
        "2026-03-01": {"total_water_ml": 1000, "total_caffeine_mg": 100, "total_sugar_g": 20},
        "2026-03-02": {"total_water_ml": 500,  "total_caffeine_mg": 200, "total_sugar_g": 30},
        "2026-03-03": {"total_water_ml": 1500, "total_caffeine_mg": 50,  "total_sugar_g": 10},
        "2026-03-04": {"total_water_ml": 800,  "total_caffeine_mg": 150, "total_sugar_g": 25},
        "2026-03-05": {"total_water_ml": 1200, "total_caffeine_mg": 80,  "total_sugar_g": 15},
        "2026-03-06": {"total_water_ml": 600,  "total_caffeine_mg": 180, "total_sugar_g": 35},
        "2026-03-07": {"total_water_ml": 1300, "total_caffeine_mg": 60,  "total_sugar_g": 12},
    }
    logs = [
        {"timestamp": f"2026-03-0{i+1} 12:00:00", "headache": (i % 5) + 3, "back_pain": (i % 4) + 2}
        for i in range(7)
    ]
    result = reports.compute_correlations(logs, daily_beverage=daily_beverage)
    assert isinstance(result, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reports.py -k "test_weekly_report_shows_beverage or test_correlation_uses_beverage" -v`
Expected: FAIL

- [ ] **Step 3: Update weekly/monthly report functions**

Add `beverage_totals` and `prev_beverage_totals` keyword arguments to both `generate_weekly_report` and `generate_monthly_report`. Replace old `tea_count`, `water_glasses` lines with beverage summary:

```python
def generate_weekly_report(
    logs: list, prev_logs: list, medications: list, exercises: list,
    *, beverage_totals: dict | None = None, prev_beverage_totals: dict | None = None,
) -> str:
```

Replace old tea/water lines (186-195) with:

```python
    if beverage_totals:
        days = 7
        avg_water = round(beverage_totals.get("total_water_ml", 0) / days)
        avg_caffeine = round(beverage_totals.get("total_caffeine_mg", 0) / days)
        avg_sugar = round(beverage_totals.get("total_sugar_g", 0) / days)
        prev_avg_water = round(prev_beverage_totals.get("total_water_ml", 0) / days) if prev_beverage_totals else None
        prev_avg_caffeine = round(prev_beverage_totals.get("total_caffeine_mg", 0) / days) if prev_beverage_totals else None
        prev_avg_sugar = round(prev_beverage_totals.get("total_sugar_g", 0) / days) if prev_beverage_totals else None
        lines.append(f"💧 آب (میانگین): {avg_water}ml/روز{_trend_arrow(avg_water, prev_avg_water)}")
        lines.append(f"☕ کافئین (میانگین): {avg_caffeine}mg/روز{_trend_arrow(avg_caffeine, prev_avg_caffeine)}")
        lines.append(f"🍬 قند (میانگین): {avg_sugar}g/روز{_trend_arrow(avg_sugar, prev_avg_sugar)}")
```

Do the same for `generate_monthly_report`.

- [ ] **Step 4: Update compute_correlations**

Add `daily_beverage` keyword argument:

```python
def compute_correlations(logs: list, *, daily_beverage: dict | None = None) -> list[str]:
```

Replace old beverage correlation pairs (lines 410-413) with new ones that use `daily_beverage` data:

```python
        # Beverage correlations from beverage_log
        ("bev_water_ml", "headache", "آب", "سردرد"),
        ("bev_caffeine_mg", "headache", "کافئین", "سردرد"),
        ("bev_sugar_g", "headache", "قند", "سردرد"),
```

And inject the daily_beverage data into `day_avgs`:

```python
    if daily_beverage:
        for day, bev_data in daily_beverage.items():
            if day not in day_avgs:
                day_avgs[day] = {}
            day_avgs[day]["bev_water_ml"] = bev_data.get("total_water_ml", 0)
            day_avgs[day]["bev_caffeine_mg"] = bev_data.get("total_caffeine_mg", 0)
            day_avgs[day]["bev_sugar_g"] = bev_data.get("total_sugar_g", 0)
```

Remove old pairs: `("water_amount", "headache", ...)`, `("water_glasses", "headache", ...)`, `("tea_count", "headache", ...)`, `("caffeine_amount", "headache", ...)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_reports.py -k "test_weekly_report_shows_beverage or test_correlation_uses_beverage" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add reports.py tests/test_reports.py
git commit -m "feat: update weekly/monthly reports and correlations for beverage system"
```

---

### Task 8: Wire up bot.py report callers to pass beverage data

**Files:**
- Modify: `bot.py:1454-1600`

- [ ] **Step 1: Update _send_today_summary to pass beverages**

In `bot.py`, modify `_send_today_summary`:

```python
def _send_today_summary(chat_id: int, user_id: int) -> None:
    today = _today_str(user_id)
    tomorrow = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    logs = database.get_logs_by_date_range(user_id, today, tomorrow)
    meds = database.get_medications_by_date_range(user_id, today, tomorrow)
    exercises = database.get_recent_exercises(50, user_id=user_id)
    today_exercises = [e for e in exercises if e["timestamp"][:10] == today]
    beverages = database.get_today_beverages(user_id, today)
    text = reports.generate_daily_summary(logs, meds, today_exercises, beverages=beverages)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
```

- [ ] **Step 2: Update _send_weekly_report to pass beverage totals**

```python
def _send_weekly_report(chat_id: int, user_id: int) -> None:
    today = _now_local(user_id).date()
    week_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    week_end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    prev_start = (today - timedelta(days=13)).strftime("%Y-%m-%d")

    logs = database.get_logs_by_date_range(user_id, week_start, week_end)
    prev_logs = database.get_logs_by_date_range(user_id, prev_start, week_start)
    meds = database.get_medications_by_date_range(user_id, week_start, week_end)
    exercises = database.get_recent_exercises(100, user_id=user_id)
    week_exercises = [e for e in exercises if e["timestamp"][:10] >= week_start]

    bev_daily = database.get_daily_beverage_totals_by_range(user_id, week_start, week_end)
    bev_totals = {
        "total_water_ml": sum(d["total_water_ml"] for d in bev_daily.values()),
        "total_caffeine_mg": sum(d["total_caffeine_mg"] for d in bev_daily.values()),
        "total_sugar_g": sum(d["total_sugar_g"] for d in bev_daily.values()),
    }
    prev_bev_daily = database.get_daily_beverage_totals_by_range(user_id, prev_start, week_start)
    prev_bev_totals = {
        "total_water_ml": sum(d["total_water_ml"] for d in prev_bev_daily.values()),
        "total_caffeine_mg": sum(d["total_caffeine_mg"] for d in prev_bev_daily.values()),
        "total_sugar_g": sum(d["total_sugar_g"] for d in prev_bev_daily.values()),
    }

    text = reports.generate_weekly_report(
        logs, prev_logs, meds, week_exercises,
        beverage_totals=bev_totals, prev_beverage_totals=prev_bev_totals,
    )
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
```

- [ ] **Step 3: Update _send_monthly_report similarly**

Same pattern as weekly, adjusting date ranges.

- [ ] **Step 4: Update _send_insights to pass beverage data**

```python
def _send_insights(chat_id: int, user_id: int) -> None:
    logs = database.get_recent_logs(200, user_id=user_id)
    # Get beverage data for correlation
    today = _now_local(user_id).date()
    start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    daily_bev = database.get_daily_beverage_totals_by_range(user_id, start, end)
    insights = reports.compute_correlations(logs, daily_beverage=daily_bev)
    text = "🔍 <b>بینش‌ها</b>\n\n" + "\n\n".join(insights)
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard())
```

- [ ] **Step 5: Update _format_last_log to remove old beverage fields**

Remove references to `water_amount`, `caffeine_amount`, `tea_count` from `_format_last_log`.

- [ ] **Step 6: Update _send_chart to remove water_amount from lifestyle chart**

In `_send_chart`, remove `"water_amount"` from the lifestyle chart fields list (line 1524).

- [ ] **Step 7: Update _send_history to remove old beverage references**

Remove `water_amount`, `tea_count`, `water_glasses` from the history display.

- [ ] **Step 8: Run all tests**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add bot.py
git commit -m "feat: wire up beverage data to all report endpoints"
```

---

### Task 9: Update help text and run migration on init

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Update help text**

In `handle_help` (line 726), replace `"🍵 <b>چای</b> / 💧 <b>آب</b>"` with `"🥤 <b>نوشیدنی</b>"`.

- [ ] **Step 2: Call migration in main()**

In `main()` (line 1716), add after `database.init_db()`:

```python
    migrated = database.migrate_legacy_beverages()
    if migrated:
        logger.info("Migrated %d legacy beverage records.", migrated)
```

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: update help text and run beverage migration on startup"
```

---

### Task 10: Final integration test and coverage check

**Files:**
- Test: all test files

- [ ] **Step 1: Run full test suite with coverage**

Run: `pytest --tb=short -v`
Expected: All tests PASS

- [ ] **Step 2: Check coverage**

Run: `pytest --cov --cov-report=term-missing`
Expected: Coverage >= 85%

- [ ] **Step 3: Fix any coverage gaps**

Add tests as needed for uncovered branches.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: ensure full coverage for beverage tracking system"
```
