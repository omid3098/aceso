"""
Analytics, chart generation, and correlation insights for health tracker.
"""
import io
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
    "sleep_quality": "Sleep",
    "stress_level": "Stress",
    "anxiety_level": "Anxiety",
    "water_amount": "Water",
    "smoke_count": "Cigarettes",
    "caffeine_amount": "Caffeine",
    "screen_hours": "Screen (h)",
    "sitting_hours": "Sitting (h)",
}

FIELD_LABELS_FA = {
    "back_pain": "کمردرد",
    "headache": "سردرد",
    "peace_level": "آرامش",
    "sleep_quality": "خواب",
    "stress_level": "استرس",
    "anxiety_level": "اضطراب",
    "water_amount": "آب",
    "smoke_count": "سیگار",
    "caffeine_amount": "کافئین",
    "screen_hours": "صفحه‌نمایش",
    "sitting_hours": "نشستن",
}


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
            val = log[field] if isinstance(log, sqlite3.Row) else log.get(field)
            if val is not None:
                ts_str = log["timestamp"] if isinstance(log, sqlite3.Row) else log.get("timestamp", "")
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


def generate_weekly_report(
    logs: list,
    prev_logs: list,
    medications: list,
    exercises: list,
) -> str:
    """Return a formatted text report comparing this week to the previous."""

    def collect(rows, field):
        return [r[field] for r in rows if r[field] is not None]

    def trend_arrow(curr, prev):
        if curr is None or prev is None:
            return ""
        return " ↑" if curr > prev else (" ↓" if curr < prev else " ﹦")

    fields = [
        ("sleep_quality", "😴 خواب"),
        ("back_pain", "🦴 کمردرد"),
        ("headache", "🤕 سردرد"),
        ("peace_level", "🧘 آرامش"),
        ("stress_level", "😰 استرس"),
        ("anxiety_level", "😟 اضطراب"),
        ("water_amount", "💧 آب"),
        ("caffeine_amount", "☕ کافئین"),
        ("screen_hours", "📱 صفحه‌نمایش"),
        ("sitting_hours", "🪑 نشستن"),
    ]

    lines = ["📊 <b>گزارش هفتگی</b>\n"]
    for key, label in fields:
        curr_avg = _avg(collect(logs, key))
        prev_avg = _avg(collect(prev_logs, key))
        arrow = trend_arrow(curr_avg, prev_avg)
        curr_str = str(curr_avg) if curr_avg is not None else "—"
        lines.append(f"{label}: {curr_str}{arrow}")

    total_smokes = sum(r["smoke_count"] for r in logs if r["smoke_count"])
    prev_smokes = sum(r["smoke_count"] for r in prev_logs if r["smoke_count"])
    smoke_arrow = trend_arrow(total_smokes, prev_smokes)
    lines.append(f"🚬 سیگار: {total_smokes} نخ{smoke_arrow}")

    if medications:
        lines.append(f"\n💊 دارو: {len(medications)} بار مصرف")
    if exercises:
        total_min = sum(e["duration_minutes"] for e in exercises if e["duration_minutes"])
        lines.append(f"🏃 ورزش: {len(exercises)} جلسه ({total_min} دقیقه)")

    return "\n".join(lines)


def generate_daily_summary(logs: list, medications: list, exercises: list) -> str:
    """Return a formatted text summary for a single day."""
    if not logs and not medications and not exercises:
        return "📋 امروز هنوز داده‌ای ثبت نشده."

    lines = ["📋 <b>خلاصه امروز</b>\n"]

    fields = [
        ("sleep_quality", "😴 خواب", "/10"),
        ("back_pain", "🦴 کمردرد", "/10"),
        ("headache", "🤕 سردرد", "/10"),
        ("peace_level", "🧘 آرامش", "/10"),
        ("stress_level", "😰 استرس", "/10"),
        ("anxiety_level", "😟 اضطراب", "/10"),
        ("water_amount", "💧 آب", " لیوان"),
        ("smoke_count", "🚬 سیگار", " نخ"),
        ("caffeine_amount", "☕ کافئین", ""),
        ("screen_hours", "📱 صفحه‌نمایش", " ساعت"),
        ("sitting_hours", "🪑 نشستن", " ساعت"),
    ]

    latest = {}
    total_smokes = 0
    for log in logs:
        for key, _, _ in fields:
            val = log[key]
            if val is not None:
                if key == "smoke_count":
                    total_smokes += val
                else:
                    latest[key] = val

    for key, label, unit in fields:
        if key == "smoke_count":
            lines.append(f"{label}: {total_smokes}{unit}")
        elif key in latest:
            lines.append(f"{label}: {latest[key]}{unit}")

    food_items = [log["food_details"] for log in logs if log["food_details"]]
    if food_items:
        lines.append(f"🍽 غذا: {food_items[-1]}")

    period_vals = [log["period_status"] for log in logs if log["period_status"] is not None]
    if period_vals:
        lines.append(f"🔴 پریود: {'بله' if period_vals[-1] else 'نه'}")

    note_items = [log["notes"] for log in logs if log["notes"]]
    if note_items:
        lines.append(f"📝 یادداشت: {note_items[-1]}")

    if medications:
        med_names = [f"{m['name']}" for m in medications]
        lines.append(f"\n💊 دارو: {', '.join(med_names)}")

    if exercises:
        ex_list = [
            f"{e['exercise_type']} ({e['duration_minutes']}min)"
            for e in exercises if e["duration_minutes"]
        ]
        if ex_list:
            lines.append(f"🏃 ورزش: {', '.join(ex_list)}")

    return "\n".join(lines)


def compute_correlations(logs: list) -> list[str]:
    """Compute simple threshold-based correlations. Returns list of insight strings."""
    if len(logs) < 7:
        return ["📉 حداقل ۷ روز داده لازمه تا بتونم الگو پیدا کنم."]

    insights: list[str] = []
    daily: dict[str, dict] = defaultdict(lambda: defaultdict(list))

    for log in logs:
        ts_str = log["timestamp"] if isinstance(log, sqlite3.Row) else log.get("timestamp", "")
        try:
            day = ts_str[:10]
        except (TypeError, IndexError):
            continue
        for field in ("back_pain", "headache", "peace_level", "sleep_quality",
                      "stress_level", "sitting_hours", "screen_hours",
                      "water_amount", "caffeine_amount", "smoke_count"):
            val = log[field] if isinstance(log, sqlite3.Row) else log.get(field)
            if val is not None:
                daily[day][field].append(float(val))

    day_avgs: dict[str, dict[str, float]] = {}
    for day, fields in daily.items():
        day_avgs[day] = {f: sum(v) / len(v) for f, v in fields.items()}

    def compare(cause_field: str, effect_field: str, threshold: float,
                cause_label: str, effect_label: str, direction: str = "above") -> Optional[str]:
        high_days = []
        low_days = []
        for day, avgs in day_avgs.items():
            if cause_field not in avgs or effect_field not in avgs:
                continue
            if direction == "above" and avgs[cause_field] > threshold:
                high_days.append(avgs[effect_field])
            elif direction == "below" and avgs[cause_field] < threshold:
                high_days.append(avgs[effect_field])
            else:
                low_days.append(avgs[effect_field])

        if len(high_days) >= 2 and len(low_days) >= 2:
            avg_high = round(sum(high_days) / len(high_days), 1)
            avg_low = round(sum(low_days) / len(low_days), 1)
            diff = round(abs(avg_high - avg_low), 1)
            if diff >= 0.8:
                op = ">" if direction == "above" else "<"
                return (
                    f"🔍 روزهایی که {cause_label} {op} {threshold}: "
                    f"میانگین {effect_label} = {avg_high} "
                    f"vs {avg_low} (بقیه روزها)"
                )
        return None

    correlations = [
        ("sitting_hours", "back_pain", 6, "نشستن (ساعت)", "کمردرد", "above"),
        ("screen_hours", "headache", 6, "صفحه‌نمایش (ساعت)", "سردرد", "above"),
        ("sleep_quality", "headache", 5, "کیفیت خواب", "سردرد", "below"),
        ("sleep_quality", "back_pain", 5, "کیفیت خواب", "کمردرد", "below"),
        ("water_amount", "headache", 6, "آب (لیوان)", "سردرد", "below"),
        ("caffeine_amount", "headache", 2, "کافئین", "سردرد", "above"),
        ("stress_level", "back_pain", 6, "استرس", "کمردرد", "above"),
        ("smoke_count", "peace_level", 5, "سیگار (نخ)", "آرامش", "above"),
    ]

    for args in correlations:
        result = compare(*args)
        if result:
            insights.append(result)

    if not insights:
        insights.append("🤔 هنوز الگوی مشخصی پیدا نشد. به ثبت داده ادامه بده!")

    return insights
