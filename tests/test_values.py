"""Проверки разбора аргумента так, как его присылает платформа.

Конверт чтения повторяет ответ GET /v1/data: снаружи data, внутри
объект тега, в нём точки [x, y, q]. Числа и произвольный JSON —
это литерал, пробный вызов и результат JSONata. Их разбор не трогает.
"""
from datetime import datetime, timezone

import pytest

from prs_methods import MethodError, is_good, moment, number, point, points, readings, require_good, value


def envelope(*series, **extra):
    """Собрать ответ чтения из пар (идентификатор тега, список точек)."""
    return {"data": [{"tagId": tag_id, "data": list(items), **extra} for tag_id, items in series]}


def test_value_reads_the_last_point_and_leaves_ready_values_alone():
    # Готовое значение возвращается само. Словарь без конверта data_get
    # тоже значение, а не ошибка разбора: так приходит JSON-параметр.
    assert value(2) == 2
    assert value("готово") == "готово"
    assert value({"rate": 1.5}) == {"rate": 1.5}
    # Из двух точек берётся последняя: это актуальное значение тега.
    assert value(envelope(("lamp", [[10, 1, None], [20, 4, 0]]))) == 4
    # Контекст инициатора, когда параметру нужен запрос клиента, а запуска
    # чтением не было. y лежит в объекте point, не в списке.
    assert value({"finish": 20, "start": None, "point": {"x": 20, "y": 4, "q": None}}) == 4
    # Полная точка, пакет записи и старая форма из одного значения.
    assert value([20, 4, None]) == 4
    assert value([[10, 1, None], [20, 4, 0]]) == 4
    assert value([4]) == 4
    # Тег в ответе есть, точек нет: это отсутствие данных, не ноль.
    assert value(envelope(("lamp", []))) is None


def test_number_accepts_a_tag_response_and_rejects_missing_data():
    assert number(envelope(("lamp", [[10, 4, None]]))) == 4
    # Строка с точкой — вещественное, без точки — целое.
    assert number("2.5") == 2.5
    assert number("2") == 2
    # Ноль — настоящее значение тега, его нельзя принять за отсутствие данных.
    assert number(0) == 0
    with pytest.raises(MethodError, match="отсутствует"):
        number(None)
    # True не единица, хотя в Python bool является int.
    with pytest.raises(MethodError, match="нечисловое"):
        number(True)
    # Ошибка сервиса вложена в message. В журнал метода должен попасть текст.
    with pytest.raises(MethodError, match="не прочитан"):
        number({"error": {"message": "тег не прочитан"}})


def test_several_tags_stay_separate_and_one_series_is_ordered():
    raw = envelope(("lamp", [[10, 1, None]]), ("tv", [[10, 3, 100]]))
    found = readings(raw)
    # Порядок тегов — порядок в ответе. Складывать их точки в один ряд нельзя.
    assert [item.tag_id for item in found] == ["lamp", "tv"]
    assert found[1].points[-1] == point([[10, 3, 100]])
    with pytest.raises(MethodError, match="несколько тегов"):
        value(raw)
    # Ряд сохраняет порядок и качество. У [20, 4, 0] качество ноль, не пустое.
    assert points(envelope(("lamp", [[10, 1, None], [20, 4, 0]]))) == (
        point([10, 1, None]),
        point([20, 4, 0]),
    )
    # Пустой пакет записи — пустой ряд, а не ошибка разбора.
    assert points([]) == ()


def test_quality_and_time():
    # Пустое качество и ноль платформа считает годными. 100 — потеря связи.
    assert is_good(None) and is_good(0)
    assert not is_good(100)
    # Литерал 2 качества не имеет и проверку проходит. Точка с нулём тоже.
    require_good(2, envelope(("lamp", [[10, 4, 0]])))
    with pytest.raises(MethodError, match="плохое качество"):
        require_good(envelope(("lamp", [[10, 4, 103]])))
    with pytest.raises(MethodError, match="отсутствует"):
        require_good([])
    # 1 545 288 780 секунд — те же микросекунды, делённые на 1 000 000.
    assert moment(1_545_288_780_000_000) == datetime.fromtimestamp(1_545_288_780, timezone.utc)
    # Полночь +03:00 — 21:00 предыдущих суток по UTC.
    assert moment("2018-12-31T00:00:00+03:00").hour == 21
