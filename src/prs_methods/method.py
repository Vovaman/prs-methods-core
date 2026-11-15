"""Декоратор ``@method``: объявляет функцию методом платформы.

Как платформа вызывает метод:

1. В модели под тегом есть узел метода. В нём записан адрес (например,
   ``acme.energy.sum``) и откуда брать каждый аргумент.
2. Когда срабатывает событие (новое значение тега-инициатора, расписание,
   чтение или запись тега), платформа собирает значения аргументов
   и отправляет вызов по адресу через RabbitMQ.
3. Исполнитель (см. ``run``) находит функцию с этим адресом и вызывает её.
   Аргументы передаются позиционно, в порядке параметров метода.
4. То, что вернула функция, становится значением тега. ``fail(...)``
   или исключение — значение тега не меняется, причина попадает в журнал.

Функция может быть обычной или ``async``. Декоратор возвращает её
без изменений, поэтому в тестах её можно вызывать напрямую: ``sum_energy(2, 3)``.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from patio import Registry

from prs_methods.catalog import MethodSpec, Parameter, catalog_document, catalog_yaml, normalize_type
from prs_methods.errors import MethodError

# Сервис методов платформы вызывает функции только из проекта "methods_app".
# auto_naming выключен: адрес задаёт автор в @method, а не patio по имени функции.
registry = Registry(project="methods_app", auto_naming=False)

_specs: list[MethodSpec] = []


def method(
    address: str,
    *,
    cn: str | None = None,
    description: str = "",
    parameters: tuple[Parameter, ...] | list[Parameter] = (),
    variadic: bool = False,
    probe: tuple[Any, ...] | list[Any] | None = None,
    folder: str | None = None,
    folder_description: str = "",
) -> Callable:
    """Объявить функцию методом платформы.

    Метод с фиксированным списком параметров::

        @method(
            "acme.energy.sum",
            cn="Сумма",
            folder="Энергия",
            parameters=(param("a", "float"), param("b", "float")),
            probe=(2, 3),
        )
        def sum_energy(a, b):
            return number(a) + number(b)

    Метод с произвольным числом параметров::

        @method("acme.energy.total", variadic=True, probe=(1, 2, 3))
        def total(*args):
            return sum(number(arg) for arg in args)

    Обязателен только ``address``. Остальные аргументы нужны, чтобы
    загрузить метод в каталог платформы (см. ``description_yaml``).

    Аргументы:
        address: адрес вызова. Его же указывают в узле метода на платформе
            (атрибут ``prsMethodAddress``). Адрес должен быть уникальным
            среди всех исполнителей. Удобно начинать его с имени
            организации: ``acme.<область>.<метод>``.
        cn: название метода в каталоге. По умолчанию — имя функции.
        description: описание для каталога. По умолчанию — docstring функции.
        parameters: параметры метода, по одному ``param(...)`` на каждый
            аргумент функции, в том же порядке. Платформа сверяет с этим
            списком число параметров у каждой ссылки на метод.
        variadic: ``True`` — число параметров задаёт каждая ссылка на метод
            сама, а ``parameters`` не указываются. Функция принимает ``*args``.
        probe: аргументы пробного вызова, который платформа делает после
            загрузки описания, например ``(2, 3)``. Если не задано,
            платформа подставит значения по типам параметров, а методу
            с ``variadic=True`` не передаст ни одного аргумента.
        folder: папка внутри каталога «Методы». Без неё метод попадёт в корень.
        folder_description: описание папки. Достаточно указать у одного метода.

    Ошибки:
        ValueError: пустой адрес, неизвестный тип параметра или
            ``parameters`` вместе с ``variadic=True``.
        RuntimeError: метод с таким адресом уже объявлен в этом процессе.
    """
    call_address = str(address).strip()
    if not call_address:
        raise ValueError("Адрес метода пуст.")
    declared = tuple(parameters)
    if variadic and declared:
        raise ValueError("У метода с variadic=True список parameters не задаётся.")

    def decorate(func: Callable) -> Callable:
        text = description.strip() or inspect.getdoc(func) or ""
        for item in declared:
            normalize_type(item.type)
        spec = MethodSpec(
            address=call_address,
            cn=(cn or func.__name__).strip() or func.__name__,
            description=text,
            parameters=declared,
            variadic=bool(variadic),
            probe=None if probe is None else tuple(probe),
            folder=folder.strip() if isinstance(folder, str) and folder.strip() else None,
            folder_description=folder_description.strip(),
        )
        # Сначала реестр: если адрес уже занят, метод не попадёт и в описание каталога.
        registry.register(_guard(func), call_address)
        _specs.append(spec)
        return func

    return decorate


def methods() -> tuple[MethodSpec, ...]:
    """Все объявленные методы в порядке объявления."""
    return tuple(_specs)


def description() -> dict[str, Any]:
    """Описание каталога словарём (ключи ``folders`` и ``methods``)."""
    return catalog_document(list(_specs))


def description_yaml() -> str:
    """Описание всех объявленных методов в формате YAML для каталога платформы.

    Вызывайте после импорта файлов с методами. Текст загружают
    в конфигураторе командой «Загрузка описания» в меню папки «Методы»
    или запросом ``POST /v1/methods/description``.
    """
    return catalog_yaml(list(_specs))


def _guard(func: Callable) -> Callable:
    """Обёртка, которую исполнитель вызывает вместо функции автора.

    patio выполняет только корутины, поэтому обычная функция тоже
    вызывается из ``async def``. ``fail`` превращается в ``{"error": текст}``,
    другое исключение — в ``{"error": "ИмяКласса: текст"}``: по журналу
    видно, что это сбой в коде, а не намеренный отказ.
    """
    if inspect.iscoroutinefunction(func):
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except MethodError as ex:
                return {"error": str(ex)}
            except Exception as ex:
                return {"error": f"{type(ex).__name__}: {ex}"}
    else:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except MethodError as ex:
                return {"error": str(ex)}
            except Exception as ex:
                return {"error": f"{type(ex).__name__}: {ex}"}

    wrapped.__name__ = func.__name__
    wrapped.__doc__ = func.__doc__
    wrapped.__wrapped__ = func
    return wrapped
