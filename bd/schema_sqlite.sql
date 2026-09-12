-- MVP-срез схемы (полная версия — см. schema.sql / DATABASE_README.md).
-- Только то, что нужно для сквозного прогона: campaigns -> placements ->
-- tracking_codes -> touches, плюс payments (реальные продажи).

CREATE TABLE IF NOT EXISTS courses (
    course_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    course_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    campaign_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS placements (
    placement_id      TEXT PRIMARY KEY,
    campaign_id       TEXT NOT NULL REFERENCES campaigns(campaign_id),
    channel_name      TEXT NOT NULL,
    cost              REAL NOT NULL DEFAULT 0,
    cost_is_estimate  INTEGER NOT NULL DEFAULT 0  -- 1 = рыночная оценка, не факт
);

CREATE TABLE IF NOT EXISTS tracking_codes (
    code          TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL REFERENCES campaigns(campaign_id),
    placement_id  TEXT NOT NULL REFERENCES placements(placement_id)
);

CREATE TABLE IF NOT EXISTS touches (
    touch_id        TEXT PRIMARY KEY,
    hashed_user_id  TEXT NOT NULL,
    tracking_code   TEXT REFERENCES tracking_codes(code),  -- NULL = органика
    channel_name    TEXT NOT NULL,
    event_type      TEXT NOT NULL,   -- bot_start | manual_visit
    ts              TEXT NOT NULL,
    is_first_touch  INTEGER NOT NULL DEFAULT 0,
    is_synthetic    INTEGER NOT NULL DEFAULT 1  -- в этом MVP всегда 1: реального трекинга не было
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT NOT NULL,
    hashed_user_id  TEXT NOT NULL,  -- в демо = student_id (реальной Telegram-привязки в base.xlsx нет)
    course_name     TEXT NOT NULL,
    amount          REAL NOT NULL,
    ts              TEXT NOT NULL
);
