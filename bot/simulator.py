"""
bot/simulator.py — наполняет БД для MVP-демо.

ЧТО РЕАЛЬНОЕ: продажи (payments) — все 628 заказов из base.xlsx, без изменений.
ЧТО СИНТЕТИЧЕСКОЕ: каналы, размещения, tracking-коды и САМИ КАСАНИЯ —
реального трекинга исторически не было (в этом весь смысл задачи 5),
поэтому касания сгенерированы вероятностно, с уважением к находкам EDA:
окно атрибуции 9 дней (задача 6), органика — не "весь остаток", а
честная доля.

hashed_user_id в этом демо = student_id из base.xlsx. Это упрощение:
реальной привязки к Telegram user_id в выданных данных нет и быть не
может (задача 4) — student_id используется только как стабильный ключ
для демонстрации механики, а не как настоящий хэш.
"""
import hashlib
import random
import sqlite3
from pathlib import Path

import pandas as pd

RNG_SEED = 42
ATTRIBUTION_WINDOW_DAYS = 9  # посчитано в задаче 6 — 90% лага "касание -> покупка"

# Синтетический реестр каналов. cost — рыночная оценка (5 000-15 000 ₽ за
# пост на канал ~20 000 подписчиков), а не счета за реальные размещения.
SYNTHETIC_CHANNELS = [
    {"campaign_id": "camp_launch_pro", "channel_name": "ch_erudichka",
     "cost": 12_000, "campaign_type": "external_ad"},
    {"campaign_id": "camp_start_sale", "channel_name": "ch_studyhub",
     "cost": 9_000, "campaign_type": "external_ad"},
    {"campaign_id": "camp_own_channel", "channel_name": "own_channel",
     "cost": 0, "campaign_type": "own_channel"},
]
ORGANIC_SHARE = 0.35  # доля заказов без единого касания — честная органика


def build_schema(conn: sqlite3.Connection, schema_path: str):
    conn.executescript(Path(schema_path).read_text(encoding="utf-8"))


def load_real_payments(conn: sqlite3.Connection, base_xlsx_path: str) -> pd.DataFrame:
    """Грузит РЕАЛЬНЫЕ продажи как есть — 795 строк base.xlsx."""
    df = pd.read_excel(base_xlsx_path)
    df.columns = ["student_id", "amount", "course", "ts"]
    df["ts"] = pd.to_datetime(df["ts"])
    df["hashed_user_id"] = df["student_id"].astype(str).map(hashed_id)

    df.to_sql("_raw", conn, if_exists="replace", index=False)
    conn.execute("""
        INSERT INTO payments (student_id, hashed_user_id, course_name, amount, ts)
        SELECT CAST(student_id AS TEXT), hashed_user_id, course, amount, ts FROM _raw
    """)
    conn.execute("DROP TABLE _raw")
    conn.commit()
    return df


def seed_channels(conn: sqlite3.Connection):
    for ch in SYNTHETIC_CHANNELS:
        conn.execute(
            "INSERT INTO campaigns (campaign_id, name, campaign_type) VALUES (?, ?, ?)",
            (ch["campaign_id"], ch["campaign_id"], ch["campaign_type"]),
        )
        placement_id = f"pl_{ch['channel_name']}"
        conn.execute(
            "INSERT INTO placements (placement_id, campaign_id, channel_name, cost, cost_is_estimate) "
            "VALUES (?, ?, ?, ?, ?)",
            (placement_id, ch["campaign_id"], ch["channel_name"], ch["cost"], int(ch["cost"] > 0)),
        )
        code = f"code_{ch['channel_name']}"
        conn.execute(
            "INSERT INTO tracking_codes (code, campaign_id, placement_id) VALUES (?, ?, ?)",
            (code, ch["campaign_id"], placement_id),
        )
    conn.commit()


def hashed_id(raw_id: str) -> str:
    return hashlib.sha256(f"demo-salt:{raw_id}".encode()).hexdigest()


def simulate_touches(conn: sqlite3.Connection, payments_df: pd.DataFrame):
    """Для каждого РЕАЛЬНОГО заказа вероятностно генерирует синтетическое
    касание за 0..9 дней до покупки, либо помечает заказ как органику."""
    rng = random.Random(RNG_SEED)
    channels = [c for c in SYNTHETIC_CHANNELS if c["cost"] >= 0]
    codes = {c["channel_name"]: f"code_{c['channel_name']}" for c in channels}

    orders = payments_df.groupby(["student_id", "ts"], as_index=False).first()
    touch_rows = []
    seen_first = set()

    for _, row in orders.iterrows():
        student_id = str(row["student_id"])
        order_ts = row["ts"]

        if rng.random() < ORGANIC_SHARE:
            continue  # органика — вообще без touch, это тоже честный случай

        channel = rng.choice(channels)
        lag_days = rng.randint(0, ATTRIBUTION_WINDOW_DAYS)
        touch_ts = order_ts - pd.Timedelta(days=lag_days, hours=rng.randint(0, 23))

        h_id = hashed_id(student_id)
        is_first = h_id not in seen_first
        seen_first.add(h_id)

        touch_rows.append((
            f"touch_{len(touch_rows)}", h_id, codes[channel["channel_name"]],
            channel["channel_name"],
            "bot_start" if channel["channel_name"] != "own_channel" else "manual_visit",
            touch_ts.isoformat(), int(is_first), 1,
        ))

    conn.executemany(
        "INSERT INTO touches (touch_id, hashed_user_id, tracking_code, channel_name, "
        "event_type, ts, is_first_touch, is_synthetic) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        touch_rows,
    )
    conn.commit()
    return len(touch_rows), len(orders) - len(touch_rows)


def run(db_path: str = "demo.db", base_xlsx_path: str = "data/base.xlsx",
        schema_path: str = "bd/schema_sqlite.sql"):
    Path(db_path).unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    build_schema(conn, schema_path)

    payments_df = load_real_payments(conn, base_xlsx_path)
    seed_channels(conn)
    n_touched, n_organic = simulate_touches(conn, payments_df)

    print(f"[simulator] Реальных строк продаж загружено: {len(payments_df)}")
    print(f"[simulator] Синтетических касаний сгенерировано: {n_touched}")
    print(f"[simulator] Заказов без касаний (органика): {n_organic}")
    conn.close()
    return db_path


if __name__ == "__main__":
    run()
