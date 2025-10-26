## ДЗ

За каждый пункт - 1 балл

Внедрить во вторую домашку хранение данных в БД, для этого надо:
1) Добавить БД в docket-compose.yml (если БД - это отдельный сервис, если хотите использовать sqlite, то можно скипнуть этот шаг)
2) Переписать код на взаимодействие с вашей БД (если вы еще этого не сделали, если вы уже написали код с БД, подзравляю, вам остался только 3 пункт)
3) В свободной форме, напишите скрипты, которые просимулируют разные "проблемы" которые могут возникнуть в транзакциях (dirty read, not-repeatable read, serialize) и настраивая уровне изоляции покажите, что они действительно решаются (через SQLAlchemy например), то есть:
показать dirty read при read uncommited
показать что нет dirty read при read commited
показать non-repeatable read при read commited
показать что нет non-repeatable read при repeatable read
показать  phantom reads при repeatable read
показать что нет phantom reads при serializable
*Тут зависит от того какую БД вы выбрали, разные БД могут поддерживать разные уровни изоляции

Скрипты для демонстрации уровней изоляции находятся в `scripts/`:

	- scripts/dirty_read_read_committed.py — отсутствие dirty read при READ COMMITTED (в PostgreSQL READ UNCOMMITTED не поддерживается)
	- scripts/non_repeatable_read_read_committed.py — non-repeatable read при READ COMMITTED
	- scripts/non_repeatable_read_repeatable_read_no.py — отсутствие non-repeatable read при REPEATABLE READ
	- scripts/phantom_read_read_committed.py — phantom read при READ COMMITTED
	- scripts/serializable_no_phantom.py — отсутствие phantom read при SERIALIZABLE (возможен serialization error при коммите)

Моменты по PostgreSQL:
- Уровень READ UNCOMMITTED обрабатывается как READ COMMITTED, поэтому dirty read воспроизвести нельзя; соответствующий скрипт демонстрирует именно отсутствие грязного чтения.
- На уровне REPEATABLE READ PostgreSQL использует snapshot isolation — фантомные чтения отсутствуют. Фантомы показаны на READ COMMITTED, а отсутствие фантомов — на SERIALIZABLE.

Подробный разбор результатов запусков см. в `scripts/report.md`.