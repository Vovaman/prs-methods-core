"""Описание методов для каталога платформы.

Каталог — папка «Методы» в конфигураторе Peresvet. В нём хранятся
определения методов: адрес, название, параметры. Под тегом создают
ссылку на определение и задают, откуда брать значение каждого параметра.

Описание собирается из аргументов ``@method`` и выдаётся
функцией ``description_yaml()``. Результат выглядит так::

    folders:
      -
        cn: "Энергия"
        description: ""
        methods:
          -
            cn: "Сумма"
            address: "acme.energy.sum"
            description: "Складывает последние значения двух аргументов."
            parameters:
              -
                cn: "a"
                index: 1
                type: "float"
              ...
            probe: [2, 3]
    methods: []

У метода с ``variadic=True`` вместо ``parameters`` пишется ``variadic: true``.

Загрузить описание можно в конфигураторе (команда «Загрузка описания»
в меню папки «Методы», флажок «Проверить методы» включает пробный вызов)
или запросом ``POST /v1/methods/description``.
Метод с адресом, который уже есть в каталоге, повторно не создаётся.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# Подписи типов, которые можно указать в param(), и имена, которые понимает платформа.
TYPE_NAMES = {
    "int": "int",
    "integer": "int",
    "целый": "int",
    "float": "float",
    "double": "float",
    "number": "float",
    "вещественный": "float",
    "str": "string",
    "string": "string",
    "строка": "string",
    "json": "json",
}


@dataclass(frozen=True)
class Parameter:
    """Параметр метода в каталоге. Создаётся функцией ``param``."""

    cn: str
    type: str = "float"
    description: str = ""
    index: int | None = None


def param(
    cn: str,
    type: str = "float",
    description: str = "",
    index: int | None = None,
) -> Parameter:
    """Описать параметр метода для каталога.

    Пример: ``param("a", "float", "Энергия освещения")``.

    Аргументы:
        cn: название параметра в конфигураторе.
        type: ``int``, ``float``, ``string`` или ``json``. Платформа тип
            не проверяет: он подсказывает человеку, что подставить,
            и задаёт пробное значение, если ``probe`` в ``@method`` не указан
            (``1``, ``1.0``, ``"probe"``, ``{}``).
        description: пояснение к параметру.
        index: позиция аргумента, с единицы. По умолчанию — порядок в списке
            ``parameters``. Платформа передаёт аргументы в порядке ``index``.
    """
    return Parameter(cn=cn, type=type, description=description, index=index)


@dataclass(frozen=True)
class MethodSpec:
    """Данные одного метода для каталога, собранные из аргументов ``@method``."""

    address: str
    cn: str
    description: str
    parameters: tuple[Parameter, ...]
    probe: tuple[Any, ...] | None
    folder: str | None
    folder_description: str
    variadic: bool = False


def normalize_type(value: str) -> str:
    """Привести подпись типа к ``int``, ``float``, ``string`` или ``json``.

    Неизвестный тип вызывает ``ValueError`` при объявлении метода,
    то есть сразу при импорте файла.
    """
    name = TYPE_NAMES.get(str(value).strip().lower())
    if name is None:
        fail_type = ", ".join(("int", "float", "string", "json"))
        raise ValueError(f"Неизвестный тип параметра '{value}'. Ожидается {fail_type}.")
    return name


def catalog_document(specs: list[MethodSpec]) -> dict[str, Any]:
    """Собрать описание каталога: методы с папкой — в ``folders``, без папки — в ``methods``.

    Методы одной папки идут в порядке объявления. Описанием папки
    становится первое непустое ``folder_description``.
    """
    folders: dict[str, dict[str, Any]] = {}
    root: list[dict[str, Any]] = []
    for spec in specs:
        row = _method_row(spec)
        if spec.folder:
            bucket = folders.get(spec.folder)
            if bucket is None:
                bucket = {
                    "cn": spec.folder,
                    "description": spec.folder_description,
                    "methods": [],
                }
                folders[spec.folder] = bucket
            elif spec.folder_description and not bucket["description"]:
                bucket["description"] = spec.folder_description
            bucket["methods"].append(row)
        else:
            root.append(row)
    document: dict[str, Any] = {}
    if folders:
        document["folders"] = list(folders.values())
    document["methods"] = root
    return document


def catalog_yaml(specs: list[MethodSpec]) -> str:
    """То же описание, что и ``catalog_document``, текстом YAML."""
    return _dump(catalog_document(specs))


def _method_row(spec: MethodSpec) -> dict[str, Any]:
    """Запись одного метода в формате загрузчика платформы.

    Загрузчик принимает и короткие имена полей (``address``, ``index``,
    ``type``), и имена атрибутов модели (``prsMethodAddress``, ``prsIndex``,
    ``prsValueTypeCode``). Здесь используются короткие.
    """
    parameters = []
    for offset, item in enumerate(spec.parameters, start=1):
        row: dict[str, Any] = {
            "cn": item.cn,
            "index": item.index or offset,
            "type": normalize_type(item.type),
        }
        if item.description:
            row["description"] = item.description
        parameters.append(row)
    result: dict[str, Any] = {
        "cn": spec.cn,
        "address": spec.address,
        "description": spec.description,
    }
    if parameters:
        result["parameters"] = parameters
    if spec.variadic:
        # Загрузчик платформы пока не читает этот флаг: после загрузки его включают
        # в конфигураторе («Произвольные параметры») или через PUT /v1/methods/.
        result["variadic"] = True
    if spec.probe is not None:
        result["probe"] = list(spec.probe)
    return result


def _dump(document: dict[str, Any]) -> str:
    """Записать описание в YAML без зависимости от PyYAML.

    Поддерживает только то, что собирает этот модуль: вложенные словари,
    списки словарей и однострочные списки простых значений (``probe``).
    """
    lines: list[str] = []
    _write(lines, document, 0)
    return "\n".join(lines) + "\n"


def _write(lines: list[str], value: Any, indent: int) -> None:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            lines.append(pad + "{}")
            return
        for key, item in value.items():
            if _is_flow(item):
                lines.append(f"{pad}{key}: {_flow(item)}")
            else:
                lines.append(f"{pad}{key}:")
                _write(lines, item, indent + 1)
        return
    if isinstance(value, list):
        if not value:
            lines.append(pad + "[]")
            return
        for item in value:
            if _is_flow(item):
                lines.append(f"{pad}- {_flow(item)}")
                continue
            # Словарь внутри списка начинается с "-" на отдельной строке.
            lines.append(f"{pad}-")
            _write(lines, item, indent + 1)
        return
    lines.append(pad + _flow(value))


def _is_flow(value: Any) -> bool:
    """Можно ли записать значение в одну строку YAML."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    if isinstance(value, list):
        return all(not isinstance(item, (dict, list)) for item in value)
    if isinstance(value, dict):
        return not value
    return False


def _flow(value: Any) -> str:
    # Вывод json.dumps — корректный YAML, в том числе для строк с двоеточием и кириллицей.
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return "{}"
    return json.dumps(str(value), ensure_ascii=False)
