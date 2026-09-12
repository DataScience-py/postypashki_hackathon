"""
Задача 8. Как считать ROMI.

Исторический ROMI посчитать нельзя — в base.xlsx нет ни одной цифры
затрат на рекламу. Этот модуль считает ROMI и CAC по каналам там, где
затраты ЕСТЬ (факт из реестра размещений или явно помеченная рыночная
оценка) — и честно возвращает None там, где считать не на чем.
"""
from dataclasses import dataclass


@dataclass
class ChannelResult:
    channel: str
    revenue: float
    cost: float
    orders: int
    romi: float | None
    cac: float | None
    cost_is_estimate: bool


def romi_by_channel(revenue: dict[str, float], cost: dict[str, float],
                     orders: dict[str, int], margin: float = 1.0,
                     estimated_channels: set[str] | None = None) -> list[ChannelResult]:
    """Считает ROMI и CAC по каждому каналу.

    margin — доля выручки, остающаяся после себестоимости курса
    (0.7 = считать по марже, 1.0 = считать по чистой выручке).

    Канал с cost == 0 (свой канал, органика) получает romi=None, а не
    бесконечность — деление на ноль не считается "отличным результатом".
    """
    estimated_channels = estimated_channels or set()
    results = []
    for channel, rev in revenue.items():
        c = cost.get(channel, 0.0)
        n_orders = orders.get(channel, 0)
        margin_revenue = rev * margin

        romi = (margin_revenue - c) / c if c > 0 else None
        cac = c / n_orders if n_orders > 0 and c > 0 else (0.0 if c == 0 else None)

        results.append(ChannelResult(
            channel=channel, revenue=rev, cost=c, orders=n_orders,
            romi=romi, cac=cac, cost_is_estimate=channel in estimated_channels,
        ))
    return results


def romi_attr_vs_inc(attributed_revenue: float, incremental_revenue: float,
                      cost: float, margin: float = 1.0) -> dict:
    """Сравнивает ROMI по модели атрибуции (сколько выручки приписано
    каналу) с incremental ROMI (сколько реклама добавила на самом деле,
    по результату holdout-теста). Разрыв между ними — органический спрос,
    который приписан рекламе, хотя случился бы и без неё."""
    if cost <= 0:
        return {"romi_attr": None, "romi_inc": None, "gap_revenue": None}

    romi_attr = (attributed_revenue * margin - cost) / cost
    romi_inc = (incremental_revenue * margin - cost) / cost
    return {
        "romi_attr": romi_attr,
        "romi_inc": romi_inc,
        "gap_revenue": attributed_revenue - incremental_revenue,
    }


def format_romi(value: float | None) -> str:
    return "неопределено (затраты = 0)" if value is None else f"{value:+.0%}"


if __name__ == "__main__":
    # Демонстрация на синтетических цифрах: attributed revenue условные,
    # затраты — рыночная оценка 5 000-15 000 ₽ за пост на канал
    # ~20 000 подписчиков (research/Реестр_рекламы_и_ресерч.xlsx,
    # лист "Рыночные цены"), явно помечены как оценка, а не факт.
    revenue = {"channel_A": 150_000, "channel_B": 80_000, "own_channel": 200_000}
    cost = {"channel_A": 12_000, "channel_B": 9_000, "own_channel": 0}
    orders = {"channel_A": 18, "channel_B": 9, "own_channel": 25}
    estimated = {"channel_A", "channel_B"}  # цены — рыночная оценка, не счета

    print("=== ROMI и CAC по каналам (демо на синтетике) ===")
    for r in romi_by_channel(revenue, cost, orders, margin=0.7, estimated_channels=estimated):
        tag = " [оценка стоимости]" if r.cost_is_estimate else ""
        cac_str = "н/д" if r.cac is None else f"{r.cac:,.0f} ₽".replace(",", " ")
        print(f"  {r.channel:15s} ROMI(margin=0.7)={format_romi(r.romi):22s} "
              f"CAC={cac_str}{tag}")

    print("\n=== ROMI_attr vs ROMI_inc (демо на синтетике) ===")
    result = romi_attr_vs_inc(attributed_revenue=150_000, incremental_revenue=95_000,
                               cost=12_000, margin=0.7)
    gap_str = f"{result['gap_revenue']:,.0f}".replace(",", " ")
    print(f"  ROMI_attr = {format_romi(result['romi_attr'])}")
    print(f"  ROMI_inc  = {format_romi(result['romi_inc'])}")
    print(f"  Разрыв (выручка, приписанная рекламе, но случившаяся бы и так): {gap_str} ₽")
