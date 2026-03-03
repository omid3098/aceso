"""
Analytics, chart generation, and correlation insights for health tracker.
"""
import io
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Optional

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

FIELD_LABELS = {
    "back_pain": "Back Pain",
    "headache": "Headache",
    "peace_level": "Peace",
    "sleep_quality": "Sleep Quality",
    "sleep_hours": "Sleep (h)",
    "water_amount": "Water",
    "smoke_count": "Cigarettes",
    "caffeine_amount": "Caffeine",
    "screen_hours": "Screen (h)",
    "phone_hours": "Phone (h)",
    "computer_hours": "Computer (h)",
    "sitting_hours": "Sitting (h)",
    "heater_hours": "Heater (h)",
    "heavy_lifting_kg": "Lifting (kg)",
}

FIELD_LABELS_FA = {
    "back_pain": "کمردرد",
    "headache": "سردرد",
    "peace_level": "آرامش",
    "sleep_quality": "خواب",
    "sleep_hours": "مدت خواب",
    "water_amount": "آب",
    "smoke_count": "سیگار",
    "caffeine_amount": "کافئین",
    "screen_hours": "صفحه‌نمایش",
    "phone_hours": "گوشی",
    "computer_hours": "سیستم",
    "sitting_hours": "نشستن",
    "heater_hours": "گرمکن",
    "heavy_lifting_kg": "بلند کردن سنگین",
}


def _get_val(log, field):
    """Extract a value from a sqlite3.Row or dict."""
    if isinstance(log, sqlite3.Row):
        return log[field]
    return log.get(field)


def generate_trend_chart(
    logs: list,
    fields: list[str],
    title: str = "Health Trends",
) -> Optional[bytes]:
    """Generate a PNG line chart for *fields* from the given logs."""
    if not MATPLOTLIB_AVAILABLE or not logs:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))

    for field in fields:
        dates: list[datetime] = []
        values: list[float] = []
        for log in logs:
            val = _get_val(log, field)
            if val is not None:
                ts_str = _get_val(log, "timestamp") or ""
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    continue
                dates.append(ts)
                values.append(float(val))
        if dates:
            ax.plot(
                dates, values,
                marker="o", label=FIELD_LABELS.get(field, field),
                linewidth=2, markersize=4,
            )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _avg(values: list) -> Optional[float]:
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else None


def _pearson_r(x: list[float], y: list[float]) -> Optional[float]:
    """Compute Pearson correlation coefficient. Returns None if insufficient data."""
    if len(x) != len(y) or len(x) < 5:
        return None
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 2)


_REPORT_FIELDS = [
    ("sleep_quality", "😴 خواب"),
    ("sleep_hours", "⏰ مدت خواب"),
    ("back_pain", "🦴 کمردرد"),
    ("headache", "🤕 سردرد"),
    ("peace_level", "🧘 آرامش"),
    ("water_amount", "💧 آب"),
    ("caffeine_amount", "☕ کافئین"),
    ("phone_hours", "📱 گوشی"),
    ("computer_hours", "💻 سیستم"),
    ("sitting_hours", "🪑 نشستن"),
]


def _trend_arrow(curr, prev):
    if curr is None or prev is None:
        return ""
    return " ↑" if curr > prev else (" ↓" if curr < prev else " ﹦")


def generate_weekly_report(
    logs: list,
    prev_logs: list,
    medications: list,
    exercises: list,
) -> str:
    """Return a formatted text report comparing this week to the previous."""

    def collect(rows, field):
        return [_get_val(r, field) for r in rows if _get_val(r, field) is not None]

    lines = ["📊 <b>گزارش هفتگی</b>\n"]
    for key, label in _REPORT_FIELDS:
        curr_avg = _avg(collect(logs, key))
        prev_avg = _avg(collect(prev_logs, key))
        arrow = _trend_arrow(curr_avg, prev_avg)
        curr_str = str(curr_avg) if curr_avg is not None else "—"
        lines.append(f"{label}: {curr_str}{arrow}")

    total_smokes = sum(_get_val(r, "smoke_count") for r in logs if _get_val(r, "smoke_count"))
    prev_smokes = sum(_get_val(r, "smoke_count") for r in prev_logs if _get_val(r, "smoke_count"))
    smoke_arrow = _trend_arrow(total_smokes, prev_smokes)
    smoke_display = int(total_smokes) if total_smokes == int(total_smokes) else total_smokes
    lines.append(f"🚬 سیگار: {smoke_display} نخ{smoke_arrow}")

    if medications:
        lines.append(f"\n💊 دارو: {len(medications)} بار مصرف")
    if exercises:
        total_min = sum(_get_val(e, "duration_minutes") for e in exercises if _get_val(e, "duration_minutes"))
        lines.append(f"🏃 ورزش: {len(exercises)} جلسه ({total_min} دقیقه)")

    return "\n".join(lines)


def generate_monthly_report(
    logs: list,
    prev_logs: list,
    medications: list,
    exercises: list,
) -> str:
    """Return a formatted text report comparing this month to the previous."""

    def collect(rows, field):
        return [_get_val(r, field) for r in rows if _get_val(r, field) is not None]

    if not logs:
        return "📆 داده‌ای برای این ماه ثبت نشده."

    lines = ["📆 <b>گزارش ماهانه</b>\n"]
    for key, label in _REPORT_FIELDS:
        curr_avg = _avg(collect(logs, key))
        prev_avg = _avg(collect(prev_logs, key))
        arrow = _trend_arrow(curr_avg, prev_avg)
        curr_str = str(curr_avg) if curr_avg is not None else "—"
        lines.append(f"{label}: {curr_str}{arrow}")

    total_smokes = sum(_get_val(r, "smoke_count") for r in logs if _get_val(r, "smoke_count"))
    prev_smokes = sum(_get_val(r, "smoke_count") for r in prev_logs if _get_val(r, "smoke_count"))
    smoke_arrow = _trend_arrow(total_smokes, prev_smokes)
    smoke_display = int(total_smokes) if total_smokes == int(total_smokes) else total_smokes
    lines.append(f"🚬 سیگار: {smoke_display} نخ{smoke_arrow}")

    days_logged = len(set(
        _get_val(r, "timestamp")[:10] for r in logs if _get_val(r, "timestamp")
    ))
    lines.append(f"\n📅 روزهای ثبت‌شده: {days_logged}")

    if medications:
        lines.append(f"💊 دارو: {len(medications)} بار مصرف")
    if exercises:
        total_min = sum(_get_val(e, "duration_minutes") for e in exercises if _get_val(e, "duration_minutes"))
        lines.append(f"🏃 ورزش: {len(exercises)} جلسه ({total_min} دقیقه)")

    return "\n".join(lines)


def generate_daily_summary(logs: list, medications: list, exercises: list) -> str:
    """Return a formatted text summary for a single day."""
    if not logs and not medications and not exercises:
        return "📋 امروز هنوز داده‌ای ثبت نشده."

    lines = ["📋 <b>خلاصه امروز</b>\n"]

    fields = [
        ("sleep_quality", "😴 خواب", "/10"),
        ("sleep_hours", "⏰ مدت خواب", " ساعت"),
        ("back_pain", "🦴 کمردرد", "/10"),
        ("headache", "🤕 سردرد", "/10"),
        ("peace_level", "🧘 آرامش", "/10"),
        ("water_amount", "💧 آب", " لیوان"),
        ("smoke_count", "🚬 سیگار", " نخ"),
        ("caffeine_amount", "☕ کافئین", ""),
        ("phone_hours", "📱 گوشی", " ساعت"),
        ("computer_hours", "💻 سیستم", " ساعت"),
        ("sitting_hours", "🪑 نشستن", " ساعت"),
    ]

    latest = {}
    total_smokes = 0
    total_patches = 0
    for log in logs:
        for key, _, _ in fields:
            val = _get_val(log, key)
            if val is not None:
                if key == "smoke_count":
                    total_smokes += val
                else:
                    latest[key] = val
        bp = _get_val(log, "back_patch")
        if bp:
            total_patches += bp

    for key, label, unit in fields:
        if key == "smoke_count":
            display = int(total_smokes) if total_smokes == int(total_smokes) else total_smokes
            lines.append(f"{label}: {display}{unit}")
        elif key in latest:
            lines.append(f"{label}: {latest[key]}{unit}")

    if total_patches:
        lines.append(f"🩹 چسب کمر: {total_patches} بار")

    massage_vals = [_get_val(log, "massage_type") for log in logs if _get_val(log, "massage_type")]
    if massage_vals:
        _massage_map = {"firm": "💪 محکم", "gentle": "🤲 آروم", "none": "❌ نبوده"}
        lines.append(f"💆 ماساژ: {_massage_map.get(massage_vals[-1], massage_vals[-1])}")

    heater_vals = [_get_val(log, "heater_hours") for log in logs if _get_val(log, "heater_hours") is not None]
    if heater_vals:
        lines.append(f"🔌 گرمکن: {heater_vals[-1]} ساعت")

    lifting_vals = [_get_val(log, "heavy_lifting_kg") for log in logs if _get_val(log, "heavy_lifting_kg") is not None]
    if lifting_vals:
        lines.append(f"🏋️ سنگین: {lifting_vals[-1]} کیلو")

    food_items = [_get_val(log, "food_details") for log in logs if _get_val(log, "food_details")]
    if food_items:
        lines.append(f"🍽 غذا: {food_items[-1]}")

    period_vals = [_get_val(log, "period_status") for log in logs if _get_val(log, "period_status") is not None]
    if period_vals:
        lines.append(f"🔴 پریود: {'بله' if period_vals[-1] else 'نه'}")

    note_items = [_get_val(log, "notes") for log in logs if _get_val(log, "notes")]
    if note_items:
        lines.append(f"📝 یادداشت: {note_items[-1]}")

    if medications:
        med_names = [_get_val(m, "name") for m in medications]
        lines.append(f"\n💊 دارو: {', '.join(med_names)}")

    if exercises:
        ex_list = [
            f"{_get_val(e, 'exercise_type')} ({_get_val(e, 'duration_minutes')}min)"
            for e in exercises if _get_val(e, "duration_minutes")
        ]
        if ex_list:
            lines.append(f"🏃 ورزش: {', '.join(ex_list)}")

    return "\n".join(lines)


def compute_correlations(logs: list) -> list[str]:
    """Compute Pearson correlations between lifestyle factors and outcomes."""
    if len(logs) < 7:
        return ["📉 حداقل ۷ روز داده لازمه تا بتونم الگو پیدا کنم."]

    daily: dict[str, dict] = defaultdict(lambda: defaultdict(list))

    for log in logs:
        ts_str = _get_val(log, "timestamp") or ""
        try:
            day = ts_str[:10]
        except (TypeError, IndexError):
            continue
        for field in ("back_pain", "headache", "peace_level", "sleep_quality",
                      "sleep_hours", "sitting_hours", "phone_hours",
                      "computer_hours", "screen_hours",
                      "water_amount", "caffeine_amount", "smoke_count"):
            val = _get_val(log, field)
            if val is not None:
                daily[day][field].append(float(val))

    day_avgs: dict[str, dict[str, float]] = {}
    for day, fields in daily.items():
        day_avgs[day] = {f: sum(v) / len(v) for f, v in fields.items()}

    insights: list[str] = []

    pairs = [
        ("sitting_hours", "back_pain", "نشستن", "کمردرد"),
        ("phone_hours", "headache", "گوشی", "سردرد"),
        ("phone_hours", "back_pain", "گوشی", "کمردرد"),
        ("computer_hours", "headache", "سیستم", "سردرد"),
        ("computer_hours", "back_pain", "سیستم", "کمردرد"),
        ("screen_hours", "headache", "صفحه‌نمایش", "سردرد"),
        ("screen_hours", "back_pain", "صفحه‌نمایش", "کمردرد"),
        ("sleep_quality", "back_pain", "کیفیت خواب", "کمردرد"),
        ("sleep_quality", "headache", "کیفیت خواب", "سردرد"),
        ("sleep_hours", "back_pain", "مدت خواب", "کمردرد"),
        ("sleep_hours", "headache", "مدت خواب", "سردرد"),
        ("water_amount", "headache", "آب", "سردرد"),
        ("caffeine_amount", "headache", "کافئین", "سردرد"),
        ("smoke_count", "peace_level", "سیگار", "آرامش"),
        ("peace_level", "back_pain", "آرامش", "کمردرد"),
    ]

    for cause, effect, cause_fa, effect_fa in pairs:
        x_vals, y_vals = [], []
        for day, avgs in day_avgs.items():
            if cause in avgs and effect in avgs:
                x_vals.append(avgs[cause])
                y_vals.append(avgs[effect])
        r = _pearson_r(x_vals, y_vals)
        if r is not None and abs(r) >= 0.3:
            strength = "قوی" if abs(r) >= 0.6 else "متوسط"
            direction = "مستقیم" if r > 0 else "معکوس"
            insights.append(
                f"📊 {cause_fa} و {effect_fa}: رابطه {strength} {direction} (r={r})"
            )

    if not insights:
        insights.append("🤔 هنوز الگوی مشخصی پیدا نشد. به ثبت داده ادامه بده!")

    return insights


def compute_med_effectiveness(logs: list, medications: list) -> str:
    """Compare pain levels on medication days vs non-medication days."""
    if not medications or len(logs) < 7:
        return "💊 <b>اثربخشی دارو</b>\n\nداده کافی نیست. حداقل ۷ روز داده و چند ثبت دارو لازمه."

    med_days: dict[str, set] = defaultdict(set)
    for m in medications:
        ts_str = _get_val(m, "timestamp") or ""
        day = ts_str[:10]
        name = _get_val(m, "name") or ""
        med_days[name].add(day)

    daily_pain: dict[str, dict[str, list]] = {}
    for log in logs:
        ts_str = _get_val(log, "timestamp") or ""
        day = ts_str[:10]
        if day not in daily_pain:
            daily_pain[day] = {"back_pain": [], "headache": []}
        bp = _get_val(log, "back_pain")
        ha = _get_val(log, "headache")
        if bp is not None:
            daily_pain[day]["back_pain"].append(float(bp))
        if ha is not None:
            daily_pain[day]["headache"].append(float(ha))

    day_avgs: dict[str, dict[str, float]] = {}
    for day, vals in daily_pain.items():
        day_avgs[day] = {}
        for field in ("back_pain", "headache"):
            if vals[field]:
                day_avgs[day][field] = sum(vals[field]) / len(vals[field])

    lines = ["💊 <b>اثربخشی دارو</b>\n"]

    for med_name, days in med_days.items():
        med_bp, no_med_bp = [], []
        med_ha, no_med_ha = [], []
        for day, avgs in day_avgs.items():
            if day in days:
                if "back_pain" in avgs:
                    med_bp.append(avgs["back_pain"])
                if "headache" in avgs:
                    med_ha.append(avgs["headache"])
            else:
                if "back_pain" in avgs:
                    no_med_bp.append(avgs["back_pain"])
                if "headache" in avgs:
                    no_med_ha.append(avgs["headache"])

        if len(med_bp) < 2 or len(no_med_bp) < 2:
            lines.append(f"\n<b>{med_name}</b>: داده کافی نیست")
            continue

        avg_med_bp = round(sum(med_bp) / len(med_bp), 1)
        avg_no_med_bp = round(sum(no_med_bp) / len(no_med_bp), 1)
        avg_med_ha = round(sum(med_ha) / len(med_ha), 1) if med_ha else None
        avg_no_med_ha = round(sum(no_med_ha) / len(no_med_ha), 1) if no_med_ha else None

        lines.append(f"\n<b>{med_name}</b> ({len(days)} روز مصرف):")
        lines.append(f"  🦴 کمردرد: {avg_med_bp} با دارو vs {avg_no_med_bp} بدون دارو")
        if avg_med_ha is not None and avg_no_med_ha is not None:
            lines.append(f"  🤕 سردرد: {avg_med_ha} با دارو vs {avg_no_med_ha} بدون دارو")

    return "\n".join(lines)
