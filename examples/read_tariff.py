"""Тип 1, чтение, фиксированные параметры: тариф на момент запроса.

Сценарий: у тега «Тариф» нет хранимых значений. Когда клиент читает тег
(``GET /v1/data/``), метод вычисляет тариф на момент ``finish`` запроса:
днём (7:00–23:00 по Москве) дневной, ночью ночной.

Настройка на платформе:

1. ``python examples/read_tariff.py --yaml > tariff.yaml`` и загрузить файл в каталог.
2. В меню тега «Тариф»: «Новый метод» → «Ссылка на метод из каталога» →
   «Тариф по времени». Тип — «Чтение» (1), инициаторов нет. Параметры:
   ``request`` — «Данные из запроса клиента», ``day`` и ``night`` — литералы.
   Тег с методом чтения не привязывают к хранилищу.
3. ``amqp_url=amqp://пользователь:пароль@сервер/ python examples/read_tariff.py``.

Платформа отдаёт клиенту результат функции как значение тега
с меткой времени ``finish`` запроса.
"""
from datetime import datetime, timedelta, timezone

from prs_methods import main, method, moment, number, param

MOSCOW = timezone(timedelta(hours=3))


@method(
    "acme.energy.tariff",
    cn="Тариф по времени",
    description="Дневной или ночной тариф на момент чтения тега.",
    folder="Энергия",
    parameters=(
        param("request", "json", "Запрос клиента"),
        param("day", "float", "Дневной тариф"),
        param("night", "float", "Ночной тариф"),
    ),
    # 2023-11-14 22:13 UTC = 01:13 по Москве, ожидается ночной тариф.
    probe=({"tagId": ["1"], "finish": 1_700_000_000_000_000}, 6.5, 2.5),
)
def tariff(request, day, night):
    finish = request.get("finish") if isinstance(request, dict) else None
    when = moment(finish) if finish is not None else datetime.now(timezone.utc)
    hour = when.astimezone(MOSCOW).hour
    return number(day) if 7 <= hour < 23 else number(night)


if __name__ == "__main__":
    main()
