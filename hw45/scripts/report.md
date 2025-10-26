# Демонстрация уровней изоляции

Среда:
- URL базы данных берётся из переменной окружения `DATABASE_URL`, по умолчанию `postgresql+psycopg2://postgres:postgres@localhost:5432/shop`.
- Все скрипты ориентированы на PostgreSQL
- Используется таблица `items(id, name, price, deleted)`. Скрипт dirty-read инициализирует схему через SQLAlchemy ORM; остальные предполагают, что схема уже существует (например, создана при запуске приложения или одного из скриптов).

PostgreSQL трактует READ UNCOMMITTED как READ COMMITTED. Грязные чтения воспроизвести нельзя; соответствующий скрипт показывает их отсутствие на уровне READ COMMITTED.

## dirty_read_read_committed.py — отсутствие dirty read на уровне READ COMMITTED

- Что делает:
  - T1 начинает транзакцию, обновляет `items(id=1).price` до 200, сбрасывает (без коммита), засыпает, потом откатывается.
  - T2 (READ COMMITTED) читает `items(id=1).price`, пока T1 спит.
- Ожидаемое поведение в PostgreSQL:
  - T2 НЕ видит незафиксированное изменение; читает последнее закоммиченное значение (150.0).
  - После отката T1 финальная цена остаётся 150.0.
- Ключевые моменты из типичного вывода:
  - Фактический вывод:

```
===== DIRTY READ (EXPECTED: PREVENTED) =====
Note: PostgreSQL treats READ UNCOMMITTED as READ COMMITTED, so dirty reads cannot occur.
T1: BEGIN (READ COMMITTED)
T1: Loaded item id=1 price=150.0
T1: Changed price to 200 (NOT committed)
T2: BEGIN (READ COMMITTED)
T2: Read price=150.0 (should be 150.0, NOT 200.0)
T2: COMMIT
T1: ROLLBACK
Final price in DB: 150.0 (should be 150.0 after rollback)
```

- T2 не увидел "грязное" (незакоммиченное) изменение от T1 и прочитал последнюю закоммиченную цену 150.0. После отката T1 цена осталась 150.0. Это подтверждает, что dirty read в PostgreSQL на READ COMMITTED не бывает.

## non_repeatable_read_read_committed.py — non-repeatable read на уровне READ COMMITTED

- Что делает:
  - T1 (READ COMMITTED) читает `items(id=1).price` два раза в одной транзакции.
  - T2 обновляет цену между чтениями T1 и коммитит.
- Ожидаемое поведение:
  - Второе чтение T1 может увидеть закоммиченное изменение от T2 (non-repeatable read).
- Ключевые моменты из типичного вывода:
  - Фактический вывод:

```
T1: BEGIN (READ COMMITTED)
T1: first read price=150.0
T2: BEGIN (READ COMMITTED)
T2: UPDATE price = price + 1
T2: COMMIT
T1: second read price=151.0 (non-repeatable if changed)
T1: COMMIT
Final price in DB: 151.0
```

- Первое чтение T1 дало 150.0, второе — 151.0 после коммита T2. Значение поменялось внутри одной транзакции T1, что и показывает non-repeatable read на READ COMMITTED.

## non_repeatable_read_repeatable_read_no.py — отсутствие non-repeatable read на уровне REPEATABLE READ

- Что делает:
  - T1 работает на REPEATABLE READ; читает ту же строку два раза.
  - T2 обновляет и коммитит между ними.
- Ожидаемое поведение:
  - T1 видит один и тот же снимок оба раза; значения одинаковые, несмотря на коммит T2.
- Ключевые моменты из типичного вывода:
  - Фактический вывод:

```
T1: BEGIN (REPEATABLE READ)
T1: first read price=50.0
T2: BEGIN (READ COMMITTED)
T2: UPDATE price = price + 1
T2: COMMIT
T1: second read price=50.0 (should be same)
T1: COMMIT
Final price in DB: 51.0
```

- Хотя T2 обновил (и цена в БД стала 51.0), T1 во второй раз видит ту же 50.0 — снимок не изменился на REPEATABLE READ. Non-repeatable read предотвращён.

## phantom_read_read_committed.py — phantom read на уровне READ COMMITTED

- Что делает:
  - T1 считает строки по предикату два раза в одной транзакции.
  - T2 вставляет новую подходящую строку и коммитит между чтениями T1.
- Ожидаемое поведение:
  - Второй счёт может быть больше из-за закоммиченной вставки (phantom read).
- Ключевые моменты из типичного вывода:
  - Фактический вывод:

```
T1: BEGIN (READ COMMITTED)
T1: first count=3
T2: BEGIN (READ COMMITTED)
T2: INSERT phantom-1
T2: COMMIT
T1: second count=4 (phantom if increased)
T1: COMMIT
```

- Между двумя подсчётами T1, T2 добавил подходящую строку. Второй подсчёт вырос на 1 — вот это и есть phantom read на READ COMMITTED.

## serializable_no_phantom.py — отсутствие phantom read на уровне SERIALIZABLE (возможна ошибка сериализации)

- Что делает:
  - T1 на SERIALIZABLE повторяет подсчёт.
  - T2 вставляет подходящую строку и коммитит между чтениями T1.
- Ожидаемое поведение:
  - T1 не должен видеть фантомы. Либо:
    - Финальный подсчёт T1 остаётся тем же, и коммит проходит, либо
    - PostgreSQL обнаруживает конфликт, и коммит T1 падает с ошибкой сериализации.
- Ключевые моменты из типичного вывода:
  - Фактический вывод:

```
T1: BEGIN (SERIALIZABLE)
T1: first count=3
T2: BEGIN (READ COMMITTED)
T2: INSERT serial-1
T2: COMMIT
T1: second count (should be same)=3
T1: COMMIT (no serialization failure)
```

- T1 не увидел фантом (счётчик не изменился). На SERIALIZABLE иногда коммит T1 может закончиться ошибкой сериализации — в нашем случае всё прошло гладко, без изменений в снимке.
