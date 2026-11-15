"""Пример метода записи: проверить уставку и передать её на оборудование.

Сценарий: оператор записывает в тег «Уставка температуры» новое значение
(``POST /v1/data/``). Метод проверяет диапазон и отправляет значение
на контроллер. Если значение вне диапазона, запись отклоняется,
и клиент получает ошибку.

Как это настроить:

1. Загрузить описание в каталог: ``python examples/setpoint_write.py --yaml``.
2. Под тегом уставки создать ссылку на метод «Запись уставки» с типом
   «Запись» (2). Параметр ``limit`` — литерал, например ``30``.
   Тег с методом записи обычно не привязывают к хранилищу.
3. Запустить исполнитель:
   ``amqp_url=amqp://пользователь:пароль@сервер/ python examples/setpoint_write.py``.

Метод записи получает записываемые точки последним аргументом, после
всех параметров. Поэтому у функции на один аргумент больше, чем в ``parameters``.
"""
import sys

from prs_methods import description_yaml, fail, method, moment, number, param, points, run


def send_to_controller(value, when):
    """Заглушка: здесь должен быть вызов API вашего оборудования."""
    print(f"{when.isoformat()} -> уставка {value}")


@method(
    "acme.hvac.setpoint_write",
    cn="Запись уставки",
    description="Проверяет диапазон уставки и передаёт её на контроллер.",
    folder="Климат",
    parameters=(param("limit", "float", "Максимально допустимая уставка"),),
    # Пробный вызов: limit = 30, записывается одна точка со значением 21.
    probe=(30, [[1_700_000_000_000_000, 21, None]]),
)
def setpoint_write(limit, written):
    top = number(limit)
    for item in points(written):
        if not 0 <= number(item.y) <= top:
            fail(f"уставка {item.y} вне диапазона 0..{top}")
    for item in points(written):
        send_to_controller(item.y, moment(item.x))
    # У метода записи важно только, был ли отказ: возвращаемое значение платформа не использует.
    return True


if __name__ == "__main__":
    if "--yaml" in sys.argv:
        print(description_yaml(), end="")
    else:
        run()
