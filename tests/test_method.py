"""Проверки регистрации: платформа вызывает обёртку, тест — саму функцию.

Обёртка в реестре patio всегда асинхронная. Отказ fail и случайный
сбой становятся {"error": ...}. Прямой вызов sum_energy исключение не прячет.

Описание YAML должно загружаться тем же разбором, что и файл каталога
платформы: папка, адрес, порядок параметров и пробные аргументы.
"""
import asyncio
import os

import pytest
import yaml

from prs_methods import description_yaml, fail, method, number, param, registry
from prs_methods.worker import broker_url, run


@method(
    "acme.test.sum",
    cn="Сумма",
    description="Складывает",
    folder="Энергия",
    folder_description="Расчёты",
    parameters=(param("a", "float"), param("b", "float", "второе")),
    probe=(2, 3),
)
def sum_energy(a, b):
    return number(a) + number(b)


@method("acme.test.echo", cn="Эхо")
async def echo(text):
    """Возвращает аргумент как есть."""
    return text


@method("acme.test.boom")
def boom():
    # Ожидаемый отказ: текст должен дойти до платформы без имени класса.
    fail("своими словами")


@method("acme.test.crash")
def crash():
    # Неожиданный сбой: в тексте ошибки остаётся имя исключения.
    raise RuntimeError("сломалось")


def test_registered_call_understands_numbers_and_tag_responses():
    # Из реестра берётся обёртка, а не исходная функция. Её и вызывает платформа.
    call = registry["acme.test.sum"]
    assert asyncio.run(call(2, 3)) == 5
    # Один аргумент — ответ чтения, второй — числовая строка. Сумма 4 + 3.
    tag = {"data": [{"tagId": "lamp", "data": [[10, 4, None]]}]}
    assert asyncio.run(call(tag, "3")) == 7
    # Словарь без ключа error — обычный результат, его не нужно прятать.
    assert asyncio.run(registry["acme.test.echo"]({"value": 1})) == {"value": 1}
    assert asyncio.run(registry["acme.test.boom"]()) == {"error": "своими словами"}
    assert asyncio.run(registry["acme.test.crash"]()) == {"error": "RuntimeError: сломалось"}
    # Прямой вызов нужен автору для своей проверки и обёртку не включает.
    assert sum_energy(2, 3) == 5


def test_description_is_ready_for_the_catalog():
    # safe_load проверяет, что собственный вывод YAML вообще разбирается.
    loaded = yaml.safe_load(description_yaml())
    folder = loaded["folders"][0]
    assert folder["cn"] == "Энергия"
    assert folder["description"] == "Расчёты"
    spec = next(item for item in folder["methods"] if item["address"] == "acme.test.sum")
    assert spec["cn"] == "Сумма"
    # Индекс 2 — позиция параметра, с единицы. Описание есть только у второго.
    assert spec["parameters"][1] == {
        "cn": "b",
        "index": 2,
        "type": "float",
        "description": "второе",
    }
    assert spec["probe"] == [2, 3]
    # У метода без папки место в корне. Пустой docstring не затирает заданный,
    # а отсутствующее описание берётся из справки функции.
    echo_spec = next(item for item in loaded["methods"] if item["address"] == "acme.test.echo")
    assert echo_spec["description"] == "Возвращает аргумент как есть."
    assert "parameters" not in echo_spec


def test_broker_url_comes_from_the_environment(monkeypatch):
    # Очищаются оба имени: модуль читает сначала amqp_url, затем AMQP_URL.
    monkeypatch.delenv("amqp_url", raising=False)
    monkeypatch.delenv("AMQP_URL", raising=False)
    with pytest.raises(Exception, match="amqp_url"):
        broker_url()
    monkeypatch.setenv("AMQP_URL", "amqp://platform/")
    assert broker_url() == "amqp://platform/"
    # Явный аргумент важнее окружения, чтобы стенд не зависел от оболочки.
    assert broker_url("amqp://explicit/") == "amqp://explicit/"


def test_run_refuses_to_start_without_an_address(monkeypatch):
    # Методы в реестре уже есть, поэтому отказ именно из-за пустого адреса.
    # Процесс завершается кодом 1 и не начинает слушать брокер.
    monkeypatch.delenv("amqp_url", raising=False)
    monkeypatch.delenv("AMQP_URL", raising=False)
    with pytest.raises(SystemExit):
        run()
    assert os.environ.get("amqp_url") is None


def test_variadic_method_has_no_parameter_list():
    @method("acme.test.variadic", variadic=True, probe=(1, 2))
    def many(*args):
        return len(args)

    loaded = yaml.safe_load(description_yaml())
    spec = next(item for item in loaded["methods"] if item["address"] == "acme.test.variadic")
    assert spec["variadic"] is True
    assert "parameters" not in spec
    assert asyncio.run(registry["acme.test.variadic"](1, 2, 3)) == 3
    with pytest.raises(ValueError, match="variadic"):
        method("acme.test.variadic_bad", variadic=True, parameters=(param("a"),))


def test_main_prints_description_with_yaml_flag(capsys):
    from prs_methods import main

    main(["--yaml"])
    assert "acme.test.sum" in capsys.readouterr().out


def test_unknown_parameter_type_is_rejected():
    # Ошибка типа возникает при объявлении, до записи адреса в реестр.
    with pytest.raises(ValueError, match="Неизвестный тип"):
        method("acme.test.bad", parameters=(param("a", "bytes"),))(lambda a: a)
