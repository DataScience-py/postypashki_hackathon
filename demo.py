"""
demo.py — сквозной прогон measurement-системы одной командой.

Цепочка: реальные продажи -> синтетические касания -> атрибуция ->
ROMI -> (плюс два блока на 100% реальных данных: incrementality и
прогноз, взятые как есть из задач 7 и 9).

Запуск:
    pip install -r requirements.txt
    python demo.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bot import simulator
from src.attribution import run_all_models, MODELS
from src.romi import romi_by_channel, format_romi
from src.incrementality import (
    load_daily_orders,
    diff_in_diff,
    weekend_confound_range,
    required_sample_size,
    power_simulation,
)
from src.forecast import load_daily_orders as load_forecast_orders, backtest, mae, mape

DB_PATH = "demo.db"
BASE_XLSX = "data/base.xlsx"
SCHEMA_PATH = "bd/schema_sqlite.sql"


def section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def step1_build_and_simulate():
    section("ШАГ 1/4. Реальные продажи + СИНТЕТИЧЕСКИЕ касания (bot/simulator.py)")
    simulator.run(db_path=DB_PATH, base_xlsx_path=BASE_XLSX, schema_path=SCHEMA_PATH)


def step2_attribution():
    section("ШАГ 2/4. Атрибуция — 5 моделей (src/attribution.py)")
    revenue_by_model = run_all_models(DB_PATH)
    for model in MODELS:
        print(f"\n  -- {model} --")
        for channel, revenue in sorted(
            revenue_by_model[model].items(), key=lambda x: -x[1]
        ):
            print(f"     {channel:15s} {revenue:>12,.0f} \u20bd".replace(",", " "))
    return revenue_by_model


def step3_romi(revenue_by_model: dict):
    section(
        "ШАГ 3/4. ROMI и CAC — position_based, затраты по СИНТЕТИЧЕСКОЙ рыночной оценке"
    )
    conn = sqlite3.connect(DB_PATH)
    cost_rows = conn.execute(
        "SELECT channel_name, SUM(cost) as total_cost, MAX(cost_is_estimate) as is_estimate "
        "FROM placements GROUP BY channel_name"
    ).fetchall()
    conn.close()
    cost = {ch: c for ch, c, _ in cost_rows}
    estimated = {ch for ch, _, is_est in cost_rows if is_est}

    revenue = dict(revenue_by_model["position_based"])
    revenue.setdefault("organic", 0.0)
    cost.setdefault("organic", 0.0)

    orders_placeholder = {
        ch: 0 for ch in revenue
    }  # число заказов не нужно для romi(), только для CAC
    results = romi_by_channel(
        revenue, cost, orders_placeholder, margin=0.7, estimated_channels=estimated
    )
    for r in results:
        tag = (
            " [СИНТЕТИЧЕСКАЯ оценка стоимости]"
            if r.cost_is_estimate
            else (" [затрат нет]" if r.cost == 0 else "")
        )
        print(
            f"  {r.channel:15s} revenue={r.revenue:>12,.0f} \u20bd  "
            f"cost={r.cost:>8,.0f} \u20bd  ROMI(margin=0.7)={format_romi(r.romi)}{tag}".replace(
                ",", " "
            )
        )
    print("\n  ВАЖНАЯ ОГОВОРКА: стоимость канала здесь = сумма 4 условных размещений")
    print("  за период (не один пост), чтобы масштаб был сопоставим с выручкой —")
    print("  но и это по-прежнему рыночная ОЦЕНКА, не реальные счета.")


def step4_real_data_blocks():
    section("ШАГ 4/4. Incrementality и прогноз — 100% РЕАЛЬНЫЕ данные (без синтетики)")

    print("\n-- Incrementality: DiD, продвижение ПРО 20-23.08 vs контроль СТАРТ --")
    orders = load_daily_orders(BASE_XLSX)
    did = diff_in_diff(orders, "2026-08-15", "2026-08-19", "2026-08-20", "2026-08-23")
    print(
        f"   ПРО: {did['pro_pre']:.2f} -> {did['pro_treat']:.2f} заказов/день "
        f"(+{did['pro_delta']:.2f})"
    )
    print(
        f"   СТАРТ (контроль): {did['start_pre']:.2f} -> {did['start_treat']:.2f} "
        f"(+{did['start_delta']:.2f})"
    )
    print(f"   Эффект рекламы (DiD) = {did['effect_per_day']:+.2f} заказов/день")

    rng = weekend_confound_range(orders, "2026-08-09")
    print(f"\n-- Всплеск 9 августа: скидка и выходной неразличимы --")
    print(
        f"   Заказов: {rng['spike_orders']:.0f}. Честная вилка эффекта рекламы: "
        f"от {rng['lower_bound']:.0f} до {rng['upper_bound']:.0f}"
    )

    n = required_sample_size(0.05, 0.5)
    print(
        f"\n-- Holdout на будущее: нужно {n} человек на группу (baseline 5%, лифт +50%) --"
    )

    print("\n-- Прогноз продаж: backtest бейзлайнов (walk-forward) --")
    daily = load_forecast_orders(BASE_XLSX)
    y = daily["n_orders"].values
    bt = backtest(y, daily["date"])
    for m in ["naive", "seasonal7", "ma7", "wd_profile"]:
        print(
            f"   {m:12s} MAE={mae(bt['actual'].values, bt[m].values):5.2f}  "
            f"MAPE={mape(bt['actual'].values, bt[m].values):6.1f}%"
        )


def final_summary():
    section("ЧТО РЕАЛЬНОЕ, А ЧТО СИНТЕТИКА В ЭТОМ ПРОГОНЕ")
    print("""
  РЕАЛЬНОЕ:
    - Все 795 строк / 628 заказов продаж (base.xlsx) — без изменений
    - Incrementality-разбор (DiD, вилка для 9 августа) — реальные даты и суммы
    - Backtest прогноза — реальный дневной ряд заказов

  СИНТЕТИЧЕСКОЕ (помечено в коде и в выводе выше):
    - 3 канала, кампании, размещения — реального трекинга исторически не было
    - Сами touches (кто по какой ссылке пришёл) — сгенерированы вероятностно
    - Стоимость размещений (5 000-15 000 ₽) — рыночная оценка, не счета

  Смысл прогона: показать, что вся цепочка "касание -> атрибуция -> ROMI"
  реально работает end-to-end на реальных продажах — а не только описана
  в архитектуре. Когда появится реальный трекинг (задача 5), синтетический
  шаг 1 меняется на настоящие данные бота без изменений в шагах 2-4.
""")


if __name__ == "__main__":
    step1_build_and_simulate()
    revenue_by_model = step2_attribution()
    step3_romi(revenue_by_model)
    step4_real_data_blocks()
    final_summary()
