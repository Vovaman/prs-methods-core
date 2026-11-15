"""Функции, которые достают значение из аргумента метода.

Форма аргумента зависит от того, как параметр настроен на платформе.
Функции этого модуля понимают все формы, поэтому в типичном методе
достаточно написать ``number(a)``.

Что может прийти в аргумент:

* **Готовое значение** — число, строка или JSON. Так приходят литерал,
  константа, результат выражения JSONata и аргументы пробного вызова.
* **Ответ чтения тега** — параметр «данные тега» или привязка ``binding: tag``::

      {"data": [{"tagId": "...", "data": [[x, y, q], ...]}]}

* **Контекст события** — параметр «запрос клиента», если метод запущен
  не чтением, а новым значением тега или расписанием::

      {"finish": ..., "start": None, "point": {"x": ..., "y": ..., "q": ...}}

* **Записываемые точки** — последний аргумент метода записи (тип 2)
  и действия при записи (тип 4)::

      [[x, y, q], ...]

Точка тега — это ``[x, y, q]``:

* ``x`` — метка времени: целое число микросекунд от 1970-01-01 UTC
  (или строка ISO 8601, если в запросе чтения указан ``format``);
* ``y`` — значение;
* ``q`` — код качества. ``None`` или ``0`` — значение годное.
  ``100`` — нет связи платформы с коннектором, ``101`` — связь восстановлена,
  ``102`` — коннектор потерял источник данных, ``103`` — источник прислал
  плохие данные.

Какую функцию взять:

=========================  ===================================================
``number(arg)``            последнее значение как число, иначе ``fail``
``value(arg)``             последнее значение любого типа
``point(arg)``             последняя точка целиком: ``Point(x, y, q)``
``points(arg)``            все точки одного тега, от старых к новым
``readings(arg)``          точки по каждому тегу, если параметр читает несколько
``moment(x)``              метка времени как ``datetime`` в UTC
``is_good(q)``             годится ли код качества для расчёта
``require_good(*args)``    ``fail``, если в аргументах нет данных или плохое качество
=========================  ===================================================

Если вместо данных пришёл ответ платформы с ошибкой (``{"error": ...}``),
любая из функций вызовет ``fail`` с текстом этой ошибки.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NamedTuple

from prs_methods.errors import fail

_MICROSECONDS = 1_000_000


class Point(NamedTuple):
    """Точка тега.

    ``x`` — метка времени (микросекунды или строка ISO), ``y`` — значение,
    ``q`` — код качества или ``None``.
    """

    x: Any
    y: Any
    q: Any


class Reading(NamedTuple):
    """Точки одного тега.

    ``tag_id`` известен, только если аргумент — ответ чтения тега.
    У записываемых точек и контекста события он равен ``None``.
    """

    tag_id: str | None
    points: tuple[Point, ...]


def is_good(quality: Any) -> bool:
    """``True``, если код качества ``None`` или ``0``.

    Пример: ``[p for p in points(a) if is_good(p.q)]`` — только годные точки.
    """
    return quality is None or quality == 0


def moment(mark: Any) -> datetime:
    """Метка времени точки как ``datetime`` в UTC.

    Принимает микросекунды платформы, строку ISO 8601 или ``datetime``.
    Строка и ``datetime`` без часового пояса считаются временем UTC.

    Пример: ``moment(point(a).x).hour`` — час, к которому относится значение.
    """
    if isinstance(mark, datetime):
        if mark.tzinfo is None:
            return mark.replace(tzinfo=timezone.utc)
        return mark.astimezone(timezone.utc)
    # bool в Python тоже int, но меткой времени не бывает.
    if isinstance(mark, int) and not isinstance(mark, bool):
        return datetime.fromtimestamp(mark / _MICROSECONDS, timezone.utc)
    if isinstance(mark, str) and mark.strip():
        parsed = datetime.fromisoformat(mark.strip())
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    fail("метка времени не распознана")


def value(argument: Any) -> Any:
    """Последнее значение аргумента, любого типа.

    * Число, строка, ``None`` и словарь без точек возвращаются как есть.
    * Из ответа чтения, списка точек и контекста события берётся ``y``
      последней точки.
    * Если точек нет, возвращается ``None``.

    Если параметр читает несколько тегов, используйте ``readings``:
    ``value`` в этом случае вызывает ``fail``.
    """
    _reject_platform_error(argument)
    if _is_scalar(argument) or not _is_readable(argument):
        return argument
    found = readings(argument)
    if len(found) > 1:
        fail("в ответе несколько тегов; разберите его функцией readings()")
    if not found or not found[0].points:
        return None
    return found[0].points[-1].y


def number(argument: Any) -> int | float:
    """Последнее значение аргумента как число.

    Работает как ``value``, но результат обязан быть числом.
    Строки ``"2"`` и ``"2.5"`` превращаются в ``2`` и ``2.5``.
    Если значения нет, вызывает ``fail("значение отсутствует")``.
    Если значение не число (в том числе ``True``/``False``) —
    ``fail("нечисловое значение")``.
    """
    got = value(argument)
    if got is None:
        fail("значение отсутствует")
    if isinstance(got, bool) or not isinstance(got, (int, float, str)):
        fail("нечисловое значение")
    if isinstance(got, str):
        text = got.strip()
        try:
            if any(ch in text for ch in ".eE"):
                return float(text)
            return int(text)
        except ValueError:
            fail("нечисловое значение")
    return got


def point(argument: Any) -> Point:
    """Последняя точка аргумента: ``Point(x, y, q)``.

    Нужна, когда кроме значения важны метка времени или качество.
    Если точек нет, вызывает ``fail("значение отсутствует")``.
    """
    series = points(argument)
    if not series:
        fail("значение отсутствует")
    return series[-1]


def points(argument: Any) -> tuple[Point, ...]:
    """Все точки одного тега, от старых к новым.

    Подходит для ответа чтения за период и для записываемых точек
    метода записи. Пустой список точек даёт ``()``.
    Если параметр читает несколько тегов, используйте ``readings``.
    """
    found = readings(argument)
    if len(found) > 1:
        fail("в ответе несколько тегов; разберите его функцией readings()")
    if not found:
        return ()
    return found[0].points


def readings(argument: Any) -> tuple[Reading, ...]:
    """Точки по каждому тегу, в порядке ответа платформы.

    Пример для параметра, который читает сразу несколько тегов::

        total = sum(r.points[-1].y for r in readings(a) if r.points)

    Тег без точек тоже попадает в результат, с пустым ``points``.
    """
    _reject_platform_error(argument)
    if isinstance(argument, (list, tuple)) and len(argument) == 0:
        return (Reading(None, ()),)
    if _is_data_envelope(argument):
        result = []
        for item in argument.get("data") or []:
            if not isinstance(item, dict):
                continue
            tag_id = item.get("tagId")
            result.append(Reading(
                str(tag_id) if tag_id is not None else None,
                _points_of(item.get("data")),
            ))
        return tuple(result)
    if _is_initiator(argument):
        return (Reading(None, (_point_from_mapping(argument["point"]),)),)
    if _is_point(argument):
        return (Reading(None, (_point_from_sequence(argument),)),)
    if _is_point_list(argument):
        return (Reading(None, tuple(_point_from_sequence(item) for item in argument)),)
    fail("ожидались точки тега")


def require_good(*arguments: Any) -> None:
    """Прервать метод, если данным нельзя доверять.

    Вызывает ``fail``, если у аргумента нет точек или хотя бы у одной
    точки плохое качество. Готовые числа и строки (литералы, пробный вызов)
    проверку проходят: у них нет качества.

    Пример::

        @method("acme.energy.sum")
        def sum_energy(a, b):
            require_good(a, b)
            return number(a) + number(b)
    """
    for argument in arguments:
        if _is_scalar(argument):
            continue
        series = points(argument)
        if not series:
            fail("значение отсутствует")
        for item in series:
            if not is_good(item.q):
                fail("плохое качество")


def _reject_platform_error(argument: Any) -> None:
    """``fail`` с текстом ошибки, если вместо данных пришёл ответ ``{"error": ...}``.

    Ошибка бывает строкой или объектом ``{"code": ..., "message": ...}``.
    """
    if not isinstance(argument, dict) or "data" in argument or "error" not in argument:
        return
    error = argument["error"]
    if isinstance(error, dict):
        fail(str(error.get("message") or error))
    fail(str(error))


def _is_readable(argument: Any) -> bool:
    """Похож ли аргумент на точки тега. Остальные словари считаются готовым JSON."""
    return (
        _is_data_envelope(argument)
        or _is_initiator(argument)
        or _is_point(argument)
        or _is_point_list(argument)
        or (isinstance(argument, (list, tuple)) and len(argument) == 0)
    )


def _is_scalar(argument: Any) -> bool:
    return argument is None or isinstance(argument, (str, bool, int, float))


def _is_data_envelope(argument: Any) -> bool:
    """Ответ ``GET /v1/data/``: ``{"data": [{"tagId": ..., "data": [...]}, ...]}``."""
    if not isinstance(argument, dict) or "data" not in argument:
        return False
    data = argument["data"]
    if not isinstance(data, list):
        return False
    if not data:
        return True
    first = data[0]
    return isinstance(first, dict) and "data" in first


def _is_initiator(argument: Any) -> bool:
    """Контекст события: словарь с объектом ``point``."""
    return (
        isinstance(argument, dict)
        and "data" not in argument
        and isinstance(argument.get("point"), dict)
    )


def _is_point(argument: Any) -> bool:
    """Точка ``[x, y, q]``, а также устаревшие формы ``[x, y]`` и ``[y]``."""
    if not isinstance(argument, (list, tuple)) or not 1 <= len(argument) <= 3:
        return False
    return all(not isinstance(part, (list, tuple, dict)) for part in argument)


def _is_point_list(argument: Any) -> bool:
    return (
        isinstance(argument, (list, tuple))
        and len(argument) > 0
        and all(_is_point(item) for item in argument)
    )


def _points_of(raw: Any) -> tuple[Point, ...]:
    """Точки из поля ``data`` одного тега. Нераспознанные элементы пропускаются."""
    if not isinstance(raw, (list, tuple)):
        return ()
    if _is_point(raw):
        return (_point_from_sequence(raw),)
    return tuple(_point_from_sequence(item) for item in raw if _is_point(item))


def _point_from_sequence(raw: Any) -> Point:
    if len(raw) == 1:
        return Point(None, raw[0], None)
    if len(raw) == 2:
        return Point(raw[0], raw[1], None)
    return Point(raw[0], raw[1], raw[2])


def _point_from_mapping(raw: dict) -> Point:
    return Point(raw.get("x"), raw.get("y"), raw.get("q"))
