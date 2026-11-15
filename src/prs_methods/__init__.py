"""SDK для внешних методов платформы Peresvet.

Метод — обычная функция Python. Платформа вызывает её через RabbitMQ,
передаёт аргументы и записывает результат в тег. Минимальный файл::

    from prs_methods import method, number, run

    @method("acme.energy.sum")
    def sum_energy(a, b):
        return number(a) + number(b)

    if __name__ == "__main__":
        run()

Что импортировать:

* объявить метод — ``method``, ``param``;
* достать значение из аргумента — ``number``, ``value``, ``point``,
  ``points``, ``readings``, ``moment``;
* проверить данные и отказаться считать — ``require_good``, ``is_good``,
  ``fail``;
* запустить исполнитель — ``run``;
* получить YAML для каталога платформы — ``description_yaml``.

Пошаговое руководство — в README.md, рабочие примеры — в каталоге ``examples``.
"""
from prs_methods.catalog import Parameter, param
from prs_methods.errors import MethodError, fail
from prs_methods.method import description, description_yaml, method, methods, registry
from prs_methods.values import Point, Reading, is_good, moment, number, point, points, readings, require_good, value
from prs_methods.worker import broker_url, run

__all__ = [
    "MethodError",
    "Parameter",
    "Point",
    "Reading",
    "broker_url",
    "description",
    "description_yaml",
    "fail",
    "is_good",
    "method",
    "methods",
    "moment",
    "number",
    "param",
    "point",
    "points",
    "readings",
    "registry",
    "require_good",
    "run",
    "value",
]
