"""Тип 1, чтение, произвольные параметры: среднее по любому числу тегов.

Сценарий: тег «Средняя температура цеха» ничего не хранит. При чтении
метод усредняет значения всех датчиков цеха на момент ``finish`` запроса.
Датчиков в разных цехах разное число, поэтому список параметров
не фиксирован.

Настройка на платформе:

1. ``python examples/read_average.py --yaml > average.yaml`` и загрузить файл в каталог.
2. У определения «Среднее» включить «Произвольные параметры»
   (загрузчик описания пока не переносит флаг ``variadic``).
3. В меню тега «Средняя температура цеха»: «Новый метод» → «Ссылка на метод
   из каталога» → «Среднее». Тип — «Чтение» (1). Параметры — теги датчиков
   («Данные тега(-ов)» или привязка к тегу), сколько угодно.
   Платформа прочитает их на момент ``finish`` из запроса клиента.
4. ``amqp_url=amqp://пользователь:пароль@сервер/ python examples/read_average.py``.
"""
from prs_methods import fail, is_good, main, method, number, readings


@method(
    "acme.climate.average",
    cn="Среднее",
    description="Среднее годных значений всех параметров. Датчики без связи пропускаются.",
    folder="Климат",
    variadic=True,
    probe=(20, 22, 24),
)
def average(*args):
    good = []
    for arg in args:
        # Литерал или пробный аргумент: качества у него нет.
        if isinstance(arg, (int, float, str)):
            good.append(number(arg))
            continue
        # Параметр может читать сразу несколько тегов: берём последнюю точку каждого.
        for reading in readings(arg):
            if reading.points and is_good(reading.points[-1].q):
                good.append(number(reading.points[-1].y))
    if not good:
        fail("нет ни одного годного значения")
    return sum(good) / len(good)


if __name__ == "__main__":
    main()
