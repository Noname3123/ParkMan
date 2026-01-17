import os
import uuid
import time as tm
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv
import clickhouse_connect
from pymongo import MongoClient
from bson import ObjectId

from prometheus_client import start_http_server, Gauge, Counter, Summary
import schedule


# ============================================================
# Weekly Parking Distribution Batch Processor
# ============================================================
# TASK:
# 1) Uzimanje zadnje stare average distribucije iz NOVOG ClickHouseDB-a (baseline store)
# 2) Računanje average distribucije za trenutni tjedan (iz source ClickHouse)
# 3) Usporedba starog i novog average-a, ako postoji odstupanje baca alert
#
# DODATNO (praktično nužno):
# 4) Spremi novu baseline distribuciju u baseline tablicu i označi je aktivnom
#
# Napomena:
# - U projektu imate tablicu:
#     parking_db.parking_usage_baseline
#   (vidi ClickHouseDB/AdminContainer/script_to_run/parking_usage_average-table.sql)
# - Source podaci su tipično:
#     parking_db.parking_usage
#
# ALERT:
# - Ovdje "alert" = Prometheus gauge + log poruka
#   (Grafana/Prometheus alerting kasnije može triggerati notifikacije)
# ============================================================


# =========================
# Prometheus metrics
# =========================
JOB_DURATION = Summary("weekly_baseline_job_duration_seconds", "Time spent in weekly baseline job")
LAST_RUN_TS = Gauge("weekly_baseline_last_run_timestamp", "Unix timestamp of last successful run")
ALERT_ACTIVE = Gauge("weekly_baseline_alert_active", "1 if deviation alert triggered, else 0")
MAX_ABS_DIFF = Gauge("weekly_baseline_max_abs_diff", "Max absolute difference between old and new avg")
MAX_REL_DIFF = Gauge("weekly_baseline_max_rel_diff", "Max relative difference between old and new avg")
ALERT_COUNT = Counter("weekly_baseline_alert_count_total", "Total number of alerts triggered")
ROWS_WRITTEN = Counter("weekly_baseline_rows_written_total", "Rows written into baseline table")


# =========================
# Config (ENV) - Mongo (parking lot id resolve)
# =========================

MONGO_URI = os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "")  # CHANGE
PARKING_LOT_NAME = os.getenv("PARKING_LOT_NAME", "Zagreb City Center Garage")  # CHANGE
PARKING_LOT_NAME_REGEX = os.getenv("PARKING_LOT_NAME_REGEX", "false").lower() == "true"  # CHANGE


# =========================
# Config (ENV) - ClickHouse
# =========================
# Imamo 2 ClickHouse-a u priči:
# - SOURCE: gdje je parking_usage (raw/usage events)
# - ANALYTICS/BASELINE: gdje je parking_usage_baseline (novo spremište baseline-a)
#
# Ako trenutno imate samo 1 ClickHouse, postavi iste vrijednosti za oba.

CH_SOURCE_HOST = os.getenv("CH_SOURCE_HOST", os.getenv("CLICKHOUSE_HOST", "localhost"))  # CHANGE
CH_SOURCE_PORT = int(os.getenv("CH_SOURCE_PORT", os.getenv("CLICKHOUSE_PORT", "8123")))  # CHANGE
CH_SOURCE_USER = os.getenv("CH_SOURCE_USER", os.getenv("CLICKHOUSE_USER", "parkman_user"))  # CHANGE
CH_SOURCE_PASS = os.getenv("CH_SOURCE_PASS", os.getenv("CLICKHOUSE_PASS", "parkman_user_pass"))  # CHANGE
CH_SOURCE_DB = os.getenv("CH_SOURCE_DB", "parking_db")  # CHANGE

CH_BASELINE_HOST = os.getenv("CH_BASELINE_HOST", CH_SOURCE_HOST)  # CHANGE
CH_BASELINE_PORT = int(os.getenv("CH_BASELINE_PORT", str(CH_SOURCE_PORT)))  # CHANGE
CH_BASELINE_USER = os.getenv("CH_BASELINE_USER", CH_SOURCE_USER)  # CHANGE
CH_BASELINE_PASS = os.getenv("CH_BASELINE_PASS", CH_SOURCE_PASS)  # CHANGE
CH_BASELINE_DB = os.getenv("CH_BASELINE_DB", "parking_db")  # CHANGE

# CHANGE: tablice
SOURCE_TABLE = os.getenv("SOURCE_TABLE", "parking_usage")  # CHANGE
BASELINE_TABLE = os.getenv("BASELINE_TABLE", "parking_usage_baseline")  # CHANGE


# =========================
# Config (ENV) - Time window
# =========================
# "current week" definicija:
# - Default: zadnjih 7 dana od "sad"
# - Alternativa: ISO week (od ponedjeljka 00:00)
WEEK_MODE = os.getenv("WEEK_MODE", "LAST_7_DAYS")  # CHANGE: LAST_7_DAYS | ISO_WEEK
USE_UTC = os.getenv("USE_UTC", "true").lower() == "true"  # CHANGE

# CHANGE: ako želite “lokalni tjedan” (Europe/Zagreb), napravite offset u satima
TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "0"))  # CHANGE: npr. 1 za CET, 2 za CEST


# =========================
# Config (ENV) - Alert thresholds
# =========================
# Minimalno:
# - abs diff threshold (npr. 2 auta)
# - relative diff threshold (npr. 0.3 = 30%)
# - opcionalno Z-score threshold (ako imate std_dev u baseline-u)
ABS_DIFF_THRESHOLD = float(os.getenv("ABS_DIFF_THRESHOLD", "2.0"))  # CHANGE
REL_DIFF_THRESHOLD = float(os.getenv("REL_DIFF_THRESHOLD", "0.30"))  # CHANGE
USE_ZSCORE = os.getenv("USE_ZSCORE", "true").lower() == "true"  # CHANGE
ZSCORE_THRESHOLD = float(os.getenv("ZSCORE_THRESHOLD", "3.0"))  # CHANGE


# =========================
# Scheduler
# =========================
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9396"))  # CHANGE
RUN_ONCE = os.getenv("RUN_ONCE", "true").lower() == "true"  # CHANGE
SCHEDULE_WEEKDAY = os.getenv("SCHEDULE_WEEKDAY", "monday").lower()  # CHANGE
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "00:05")  # CHANGE (HH:MM)


# ------------------------------------------------------------
# Helpers: time
# ------------------------------------------------------------
def _now() -> datetime:
    if USE_UTC:
        return datetime.now(timezone.utc)
    return datetime.now()

def _apply_tz_offset(dt: datetime) -> datetime:
    # CHANGE: jednostavan offset (ako želite lokalni tjedan)
    if TZ_OFFSET_HOURS == 0:
        return dt
    return dt + timedelta(hours=TZ_OFFSET_HOURS)

def get_week_range(now: datetime) -> Tuple[datetime, datetime]:
    """
    Returns (start, end) datetimes used for "current week" aggregation.
    end is exclusive-ish (we use < end in queries).
    """
    now = _apply_tz_offset(now)

    if WEEK_MODE.upper() == "ISO_WEEK":
        # ISO week: Monday 00:00 -> now
        # weekday(): Monday=0 ... Sunday=6
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        end = now
    else:
        # LAST_7_DAYS
        end = now
        start = now - timedelta(days=7)

    # vratimo nazad u UTC “query time” ako koristimo offset
    # (offset je samo za definiciju prozora)
    start = start - timedelta(hours=TZ_OFFSET_HOURS)
    end = end - timedelta(hours=TZ_OFFSET_HOURS)

    # ensure tz-aware
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return start, end


# ------------------------------------------------------------
# Helpers: Mongo parking_lot_id resolve
# ------------------------------------------------------------
def resolve_parking_lot_id() -> str:
    """
    Dohvaća parking_lot_id iz Mongo Manager DB po imenu lota.
    """
    if not MONGO_URI:
        raise RuntimeError("Missing MONGO_MANAGER_DATABASE_R_ONLY_URI env var")

    client = MongoClient(MONGO_URI)
    try:
        db = client.get_default_database()
        if db is None:
            raise RuntimeError("Mongo URI does not include DB name")

        if PARKING_LOT_NAME_REGEX:
            query = {"name": {"$regex": PARKING_LOT_NAME, "$options": "i"}}  # CHANGE
        else:
            query = {"name": PARKING_LOT_NAME}  # CHANGE

        doc = db.parking_lots.find_one(query, {"_id": 1, "name": 1})
        if not doc:
            raise RuntimeError(f"Parking lot not found in Mongo. Query={query}")

        lot_id = str(doc["_id"])
        print(f"[WeeklyBatch] Resolved parking_lot_id={lot_id} for '{doc.get('name')}'")
        return lot_id
    finally:
        client.close()


# ------------------------------------------------------------
# Helpers: ClickHouse clients
# ------------------------------------------------------------
def ch_client_source():
    return clickhouse_connect.get_client(
        host=CH_SOURCE_HOST, port=CH_SOURCE_PORT, user=CH_SOURCE_USER, password=CH_SOURCE_PASS, database=CH_SOURCE_DB
    )

def ch_client_baseline():
    return clickhouse_connect.get_client(
        host=CH_BASELINE_HOST, port=CH_BASELINE_PORT, user=CH_BASELINE_USER, password=CH_BASELINE_PASS, database=CH_BASELINE_DB
    )


# ------------------------------------------------------------
# Step 1: load last active baseline
# ------------------------------------------------------------
def load_active_baseline(chb, parking_lot_id: str) -> Dict[int, dict]:
    """
    Returns {hour_of_day: {avg, std, max, n, calc_date}} for the active baseline.
    If none exists, returns empty dict.
    """
    # Find latest active calculation_date
    q_date = f"""
        SELECT max(calculation_date) AS max_date
        FROM {CH_BASELINE_DB}.{BASELINE_TABLE}
        WHERE parking_lot_id = %(lot)s AND is_active = 1
    """
    res = chb.query(q_date, parameters={"lot": parking_lot_id})
    max_date = res.result_rows[0][0] if res.result_rows else None
    if not max_date:
        print("[WeeklyBatch] No active baseline found (first run).")
        return {}

    q = f"""
        SELECT hour_of_day, avg_car_count, std_dev_car_count, max_observed_cars, sample_count, calculation_date
        FROM {CH_BASELINE_DB}.{BASELINE_TABLE}
        WHERE parking_lot_id = %(lot)s AND is_active = 1 AND calculation_date = %(d)s
    """
    rows = chb.query(q, parameters={"lot": parking_lot_id, "d": max_date}).result_rows

    baseline = {}
    for hour, avg, std, maxcars, n, calc_date in rows:
        baseline[int(hour)] = {
            "avg": float(avg),
            "std": float(std) if std is not None else 0.0,
            "max": int(maxcars) if maxcars is not None else 0,
            "n": int(n) if n is not None else 0,
            "calc_date": calc_date,
        }

    print(f"[WeeklyBatch] Loaded active baseline: {len(baseline)} hours (calc_date={max_date})")
    return baseline


# ------------------------------------------------------------
# Step 2: compute weekly distribution from source data
# ------------------------------------------------------------
def compute_weekly_distribution(chs, parking_lot_id: str, start: datetime, end: datetime) -> Dict[int, dict]:
    """
    Returns {hour_of_day: {avg, std, max, n}} computed over [start, end).
    """
    q = f"""
        SELECT
            toHour(timestamp) AS hour_of_day,
            avg(toFloat64(car_count)) AS avg_car_count,
            stddevPop(toFloat64(car_count)) AS std_dev_car_count,
            max(toInt32(car_count)) AS max_observed_cars,
            count() AS sample_count
        FROM {CH_SOURCE_DB}.{SOURCE_TABLE}
        WHERE parking_lot_id = %(lot)s
          AND timestamp >= %(start)s
          AND timestamp < %(end)s
        GROUP BY hour_of_day
        ORDER BY hour_of_day
    """
    rows = chs.query(q, parameters={"lot": parking_lot_id, "start": start, "end": end}).result_rows

    dist = {}
    for hour, avg, std, maxcars, n in rows:
        dist[int(hour)] = {
            "avg": float(avg) if avg is not None else 0.0,
            "std": float(std) if std is not None else 0.0,
            "max": int(maxcars) if maxcars is not None else 0,
            "n": int(n) if n is not None else 0,
        }

    print(f"[WeeklyBatch] Computed weekly distribution: {len(dist)} hours from {start} to {end}")
    return dist


# ------------------------------------------------------------
# Step 3: compare and alert
# ------------------------------------------------------------
def compare_distributions(old: Dict[int, dict], new: Dict[int, dict]) -> Tuple[bool, dict]:
    """
    Returns (alert_triggered, stats)
    stats includes max_abs_diff, max_rel_diff, worst_hour, and per_hour details (optional).
    """
    max_abs = 0.0
    max_rel = 0.0
    worst_hour = None
    alert = False

    for h in range(24):
        if h not in new:
            continue  # nema podataka za taj sat ovaj tjedan

        new_avg = new[h]["avg"]
        old_avg = old.get(h, {}).get("avg", None)

        # ako nema stare baseline za taj sat, preskoči usporedbu (ili tretiraj kao 0)
        if old_avg is None:
            continue

        abs_diff = abs(new_avg - old_avg)
        rel_diff = abs_diff / max(1e-9, abs(old_avg))  # zaštita od 0

        if abs_diff > max_abs:
            max_abs = abs_diff
            worst_hour = h
        if rel_diff > max_rel:
            max_rel = rel_diff
            worst_hour = worst_hour if worst_hour is not None else h

        # Threshold checks
        if abs_diff >= ABS_DIFF_THRESHOLD and rel_diff >= REL_DIFF_THRESHOLD:
            alert = True

        # Optional Z-score check using OLD stddev
        if USE_ZSCORE:
            old_std = old.get(h, {}).get("std", 0.0) or 0.0
            if old_std > 0:
                z = abs(new_avg - old_avg) / old_std
                if z >= ZSCORE_THRESHOLD:
                    alert = True

    stats = {
        "max_abs_diff": float(max_abs),
        "max_rel_diff": float(max_rel),
        "worst_hour": worst_hour,
    }
    return alert, stats


# ------------------------------------------------------------
# Step 4: write new baseline and activate it
# ------------------------------------------------------------
def deactivate_old_baseline(chb, parking_lot_id: str):
    """
    ClickHouse mutation: set is_active=0 where currently active for that lot.
    (ReplacingMergeTree allows it, but mutations are async.)
    """
    q = f"""
        ALTER TABLE {CH_BASELINE_DB}.{BASELINE_TABLE}
        UPDATE is_active = 0
        WHERE parking_lot_id = %(lot)s AND is_active = 1
    """
    try:
        chb.command(q, parameters={"lot": parking_lot_id})
        print("[WeeklyBatch] Deactivation mutation issued for old baseline.")
    except Exception as e:
        # nije fatalno, ali logiraj
        print(f"[WeeklyBatch] WARNING: failed to deactivate old baseline (mutation): {e}")


def write_new_baseline(chb, parking_lot_id: str, weekly: Dict[int, dict], calculation_date: datetime):
    """
    Inserts 24 rows (or less if missing hours) for the new baseline.
    baseline_id shared across rows.
    """
    baseline_id = str(uuid.uuid4())  # CHANGE: baseline run id
    calc_date = calculation_date.date()

    # Insert rows
    values = []
    for h in range(24):
        d = weekly.get(h)
        if not d:
            continue
        values.append(
            (
                baseline_id,
                calc_date,
                parking_lot_id,
                int(h),
                float(d["avg"]),
                float(d["std"]),
                int(d["max"]),
                int(d["n"]),
                1,  # is_active
            )
        )

    if not values:
        print("[WeeklyBatch] No weekly rows to write to baseline table.")
        return

    insert_q = f"""
        INSERT INTO {CH_BASELINE_DB}.{BASELINE_TABLE}
        (baseline_id, calculation_date, parking_lot_id, hour_of_day,
         avg_car_count, std_dev_car_count, max_observed_cars, sample_count, is_active)
        VALUES
    """
    # clickhouse_connect može insertati batch s insert(...)
    chb.insert(
        table=f"{CH_BASELINE_DB}.{BASELINE_TABLE}",
        data=values,
        column_names=[
            "baseline_id", "calculation_date", "parking_lot_id", "hour_of_day",
            "avg_car_count", "std_dev_car_count", "max_observed_cars", "sample_count", "is_active"
        ],
    )

    ROWS_WRITTEN.inc(len(values))
    print(f"[WeeklyBatch] Wrote new baseline rows: {len(values)} (baseline_id={baseline_id}, calc_date={calc_date})")


# ------------------------------------------------------------
# Main job
# ------------------------------------------------------------
@JOB_DURATION.time()
def run_weekly_job():
    print("[WeeklyBatch] Starting weekly distribution job...")

    parking_lot_id = resolve_parking_lot_id()

    start, end = get_week_range(_now())
    print(f"[WeeklyBatch] Week window: start={start} end={end} (mode={WEEK_MODE})")

    chs = ch_client_source()
    chb = ch_client_baseline()

    # Step 1
    old_baseline = load_active_baseline(chb, parking_lot_id)

    # Step 2
    weekly = compute_weekly_distribution(chs, parking_lot_id, start, end)

    # Step 3
    alert, stats = compare_distributions(old_baseline, weekly)

    MAX_ABS_DIFF.set(stats["max_abs_diff"])
    MAX_REL_DIFF.set(stats["max_rel_diff"])

    if alert:
        ALERT_ACTIVE.set(1)
        ALERT_COUNT.inc(1)
        print(f"[WeeklyBatch][ALERT] Deviation detected! "
              f"max_abs_diff={stats['max_abs_diff']:.3f}, max_rel_diff={stats['max_rel_diff']:.3f}, worst_hour={stats['worst_hour']}")
    else:
        ALERT_ACTIVE.set(0)
        print(f"[WeeklyBatch] No significant deviation. "
              f"max_abs_diff={stats['max_abs_diff']:.3f}, max_rel_diff={stats['max_rel_diff']:.3f}")

    # Step 4 (store new baseline)
    # CHANGE: želite li uvijek zapisati novu baseline (preporučeno) ili samo ako nema stare?
    ALWAYS_WRITE_BASELINE = os.getenv("ALWAYS_WRITE_BASELINE", "true").lower() == "true"  # CHANGE

    if ALWAYS_WRITE_BASELINE and weekly:
        deactivate_old_baseline(chb, parking_lot_id)
        write_new_baseline(chb, parking_lot_id, weekly, calculation_date=_now())

    LAST_RUN_TS.set(tm.time())
    print("[WeeklyBatch] Done.")


def schedule_weekly():
    """
    Schedulanje unutar containera. Alternativa je cron (ali ovdje slijedimo stil iz ETL_BATCH).
    """
    day_map = {
        "monday": schedule.every().monday,
        "tuesday": schedule.every().tuesday,
        "wednesday": schedule.every().wednesday,
        "thursday": schedule.every().thursday,
        "friday": schedule.every().friday,
        "saturday": schedule.every().saturday,
        "sunday": schedule.every().sunday,
    }
    if SCHEDULE_WEEKDAY not in day_map:
        raise ValueError(f"Unsupported weekday: {SCHEDULE_WEEKDAY}")

    # primjer: schedule.every().monday.at("00:05").do(run_weekly_job)
    day_map[SCHEDULE_WEEKDAY].at(SCHEDULE_TIME).do(run_weekly_job)
    print(f"[WeeklyBatch] Scheduled weekly job: {SCHEDULE_WEEKDAY} at {SCHEDULE_TIME}")


if __name__ == "__main__":
    load_dotenv()

    # Expose Prometheus metrics
    start_http_server(PROMETHEUS_PORT)
    print(f"[WeeklyBatch] Prometheus metrics on :{PROMETHEUS_PORT}")

    if RUN_ONCE:
        run_weekly_job()
    else:
        schedule_weekly()
        while True:
            schedule.run_pending()
            tm.sleep(1)
