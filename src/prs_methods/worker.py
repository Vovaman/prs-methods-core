"""Исполнитель: процесс, который принимает вызовы методов от платформы.

Платформа не запускает код метода сама. Нужно запустить исполнитель —
файл с методами, в конце которого вызывается ``main()`` или ``run()``::

    amqp_url=amqp://пользователь:пароль@сервер/ python my_methods.py

Исполнитель подключается к RabbitMQ платформы (порт 5672) и работает,
пока его не остановят (Ctrl+C или сигнал службы). При обрыве связи
он переподключается сам.

Исполнитель можно запускать на любой машине, откуда доступен RabbitMQ.
Исполнителей может быть несколько, у каждого свои адреса. Если один и тот же
адрес объявлен в двух исполнителях, каждый вызов выполнит только один из них.
"""
from __future__ import annotations

import asyncio
import os
import sys

from prs_methods.errors import MethodError, fail
from prs_methods.method import description_yaml, registry


def broker_url(explicit: str | None = None) -> str:
    """Адрес RabbitMQ: аргумент ``explicit``, иначе переменная окружения ``amqp_url`` или ``AMQP_URL``.

    Если адрес нигде не задан, вызывает ``fail``.
    """
    url = explicit or os.environ.get("amqp_url") or os.environ.get("AMQP_URL") or ""
    url = url.strip()
    if not url:
        fail("Не задан адрес RabbitMQ. Укажите переменную окружения amqp_url.")
    return url


def main(argv: list[str] | None = None) -> None:
    """Точка входа файла с методами: ``python my_methods.py [--yaml]``.

    С ключом ``--yaml`` печатает описание методов для каталога платформы,
    без ключа запускает исполнитель (``run``). Вызывайте в конце файла::

        if __name__ == "__main__":
            main()
    """
    args = sys.argv[1:] if argv is None else argv
    if "--yaml" in args:
        print(description_yaml(), end="")
        return
    run()


def run(amqp_url: str | None = None, *, workers: int = 4) -> None:
    """Подключиться к RabbitMQ и выполнять вызовы всех объявленных методов.

    Вызывайте в конце файла, после всех ``@method``: метод становится
    доступен в момент объявления.

    Аргументы:
        amqp_url: адрес RabbitMQ, например ``amqp://prs:пароль@сервер/``.
            По умолчанию берётся из переменной окружения ``amqp_url``.
        workers: сколько вызовов выполняется одновременно.

    Если адрес не задан или нет ни одного метода, функция печатает
    причину и завершает процесс с кодом 1.
    """
    try:
        if workers < 1:
            fail("Число workers должно быть больше нуля.")
        if len(registry) == 0:
            fail("Нет ни одного метода. Пометьте функции декоратором @method.")
        url = broker_url(amqp_url)
    except MethodError as ex:
        print(ex, file=sys.stderr)
        raise SystemExit(1) from ex
    try:
        asyncio.run(_serve(url, workers))
    except KeyboardInterrupt:
        return


async def _serve(url: str, workers: int) -> None:
    """Слушать брокер и переподключаться раз в секунду, если связь пропала."""
    # Транспорт импортируется только здесь: для тестов и description_yaml() он не нужен.
    from patio import AsyncExecutor
    from patio_rabbitmq import RabbitMQBroker

    async with AsyncExecutor(registry, max_workers=workers) as executor:
        while True:
            try:
                async with RabbitMQBroker(executor, amqp_url=url) as broker:
                    await broker.join()
            except KeyboardInterrupt:
                return
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                print(
                    f"Нет соединения с RabbitMQ ({ex}). Повтор через 1 с.",
                    file=sys.stderr,
                )
                await asyncio.sleep(1)
