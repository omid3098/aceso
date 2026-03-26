# Smart Beverage Tracking System

**Date:** 2026-03-26
**Status:** Approved

## Overview

Replace the current fragmented beverage tracking (separate tea/water quick buttons + water_amount/caffeine_amount in main flow) with a unified smart beverage tracking system. A single "Beverages" menu with per-drink buttons that automatically calculate nutritional values (water, caffeine, sugar, calories).

## Database

### New table: `beverage_log`

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

- Each serving = 0.5 glass = 125ml
- Nutritional values are calculated and stored at insert time (immutable)
- `date` field (TEXT, `YYYY-MM-DD`) for efficient daily queries
- `beverage_id` references keys in the `BEVERAGES` constant

### Beverages constant (in `db.py`)

Per-serving (125ml) nutritional values based on USDA data:

```python
BEVERAGES = {
    "water":    {"emoji": "💧", "label_fa": "آب",       "water_ml": 125, "caffeine_mg": 0,  "sugar_g": 0,  "calories": 0},
    "tea":      {"emoji": "🍵", "label_fa": "چای",      "water_ml": 124, "caffeine_mg": 26, "sugar_g": 0,  "calories": 1},
    "green_tea":{"emoji": "🍵", "label_fa": "چای سبز",  "water_ml": 124, "caffeine_mg": 15, "sugar_g": 0,  "calories": 1},
    "coffee":   {"emoji": "☕", "label_fa": "قهوه",     "water_ml": 124, "caffeine_mg": 50, "sugar_g": 0,  "calories": 1},
    "soda":     {"emoji": "🥤", "label_fa": "نوشابه",   "water_ml": 112, "caffeine_mg": 8,  "sugar_g": 13, "calories": 53},
    "na_beer":  {"emoji": "🍺", "label_fa": "آبجو",     "water_ml": 117, "caffeine_mg": 0,  "sugar_g": 4,  "calories": 18},
    "delster":  {"emoji": "🍺", "label_fa": "دلستر",    "water_ml": 112, "caffeine_mg": 0,  "sugar_g": 10, "calories": 45},
    "juice":    {"emoji": "🧃", "label_fa": "آبمیوه",   "water_ml": 110, "caffeine_mg": 0,  "sugar_g": 11, "calories": 56},
    "milk":     {"emoji": "🥛", "label_fa": "شیر",      "water_ml": 110, "caffeine_mg": 0,  "sugar_g": 6,  "calories": 78},
    "herbal":   {"emoji": "🌿", "label_fa": "دمنوش",    "water_ml": 124, "caffeine_mg": 0,  "sugar_g": 0,  "calories": 1},
}
```

### DB functions

- `insert_beverage(user_id, beverage_id, servings=1)` — looks up BEVERAGES dict, calculates nutritional values, inserts row
- `get_today_beverages(user_id, date_str)` — returns all beverage_log rows for a given day
- `get_today_beverage_totals(user_id, date_str)` — returns aggregated totals (total water_ml, caffeine_mg, sugar_g, calories) and per-beverage serving counts

## Bot UI

### Main menu changes

- Remove quick buttons: "🍵 چای" and "💧 آب"
- Add single button: "🥤 نوشیدنی"

### Beverage submenu (inline keyboard)

When user taps "🥤 نوشیدنی", show inline keyboard:

```
Row 1:  💧 آب (3)      |  🍵 چای (2)
Row 2:  ☕ قهوه (0)     |  🥤 نوشابه (0)    |  🍺 آبجو (0)
Row 3:  🍺 دلستر (0)   |  🧃 آبمیوه (0)    |  🥛 شیر (0)
Row 4:  🍵 چای سبز (0) |  🌿 دمنوش (0)
```

- Row 1: Primary beverages (water & tea) with dedicated placement
- Rows 2-4: Other beverages ordered by usage frequency
- Number in parentheses = today's serving count for that beverage
- Each tap = +1 serving (0.5 glass / 125ml)
- After each tap: keyboard updates with new count + confirmation message:
  `"☕ قهوه +۱ (جمع امروز: ۳)"`

### Main log flow changes

- Remove `water_amount` step from flow
- Remove `caffeine_amount` step from flow

## Reports

### Daily summary

Replace separate water/tea/caffeine display with unified beverages section:

```
🥤 نوشیدنی‌ها:
💧 آب: ۴ لیوان
🍵 چای: ۳ لیوان
☕ قهوه: ۱ لیوان
── مجموع: آب ۸۷۰ml | کافئین ۱۲۸mg | قند ۰g | ۴kcal
```

Only show beverages with servings > 0.

### Weekly/monthly reports

- Show daily averages for: total water (ml), total caffeine (mg), total sugar (g)
- Replace old field references (`water_amount`, `caffeine_amount`, `tea_count`, `water_glasses`) with new `beverage_log` queries

### Correlation analysis

Correlate daily totals from `beverage_log` against health outcomes (headache, back pain):
- Total `water_ml` per day
- Total `caffeine_mg` per day
- Total `sugar_g` per day

Replace old correlations on `water_amount`, `water_glasses`, `tea_count`, `caffeine_amount`.

## Data Migration

One-time migration of historical data from `logs` table to `beverage_log`:

1. **`tea_count`**: For each log row where `tea_count > 0`:
   - Insert into `beverage_log`: `beverage_id="tea"`, `servings=tea_count`
   - Nutritional values calculated from BEVERAGES dict

2. **`water_glasses`**: For each log row where `water_glasses > 0`:
   - Insert into `beverage_log`: `beverage_id="water"`, `servings=water_glasses`
   - Already in half-glass units, direct mapping

3. **`water_amount`**: For each log row where `water_amount > 0`:
   - Insert into `beverage_log`: `beverage_id="water"`, `servings=water_amount * 2`
   - Convert full glasses to half-glass servings

4. **`caffeine_amount`**: For each log row where `caffeine_amount > 0`:
   - Insert into `beverage_log`: `beverage_id="tea"`, `servings=caffeine_amount * 2`
   - Was tracking tea cups; convert to half-glass servings

5. **Double-counting guard**: If a log row has both `water_amount > 0` and `water_glasses > 0`, only migrate `water_amount` (the larger daily total) to avoid double-counting. Similarly, if both `caffeine_amount > 0` and `tea_count > 0`, only migrate `caffeine_amount` (the daily total).

6. Copy `timestamp`, `user_id` from source row; derive `date` from timestamp

7. Migration must be idempotent — check if `beverage_log` already has migrated data before inserting

8. Old columns in `logs` table remain untouched (not deleted) but are no longer used

## Testing

- Test `insert_beverage` with various beverage types, verify nutritional calculations
- Test `get_today_beverages` and `get_today_beverage_totals` aggregation
- Test migration of each old field type
- Test that old data + new data produce correct report totals
- Maintain >=85% coverage
