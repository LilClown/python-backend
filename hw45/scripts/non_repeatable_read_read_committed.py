#!/usr/bin/env python3
"""
Demonstrate non-repeatable read under READ COMMITTED in PostgreSQL using SQLAlchemy.

PostgreSQL treats READ UNCOMMITTED as READ COMMITTED, so dirty reads cannot be shown,
but non-repeatable reads are possible at READ COMMITTED.
"""
import os
import threading
import time
from decimal import Decimal
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/shop")
engine = create_engine(DATABASE_URL, future=True)


def ensure_demo_row():
    with engine.begin() as conn:
        conn.execute(text(
            """
            INSERT INTO items (id, name, price, deleted)
            VALUES (1, 'demo', 100.00, FALSE)
            ON CONFLICT (id) DO NOTHING
            """
        ))


def t1_read_committed():
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="READ COMMITTED")
        trans = conn.begin()
        print("T1: BEGIN (READ COMMITTED)")
        price1 = conn.execute(text("SELECT price FROM items WHERE id=1")).scalar_one()
        print(f"T1: first read price={float(price1)}")
        time.sleep(2)
        price2 = conn.execute(text("SELECT price FROM items WHERE id=1")).scalar_one()
        print(f"T1: second read price={float(price2)} (non-repeatable if changed)")
        trans.commit()
        print("T1: COMMIT")


def t2_updater():
    time.sleep(0.8)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="READ COMMITTED")
        trans = conn.begin()
        print("T2: BEGIN (READ COMMITTED)")
        conn.execute(text("UPDATE items SET price = price + 1 WHERE id=1"))
        print("T2: UPDATE price = price + 1")
        time.sleep(0.5)
        trans.commit()
        print("T2: COMMIT")


if __name__ == "__main__":
    ensure_demo_row()
    th1 = threading.Thread(target=t1_read_committed)
    th2 = threading.Thread(target=t2_updater)
    th1.start(); th2.start()
    th1.join(); th2.join()
    with engine.connect() as conn:
        final_price = conn.execute(text("SELECT price FROM items WHERE id=1")).scalar_one()
        print(f"Final price in DB: {float(final_price)}")
