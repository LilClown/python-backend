#!/usr/bin/env python3
"""
Show that non-repeatable reads are prevented under REPEATABLE READ in PostgreSQL.
T1: REPEATABLE READ reads same value twice even if T2 updates and commits in between.
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
        # Reset to a known price for stable demo
        conn.execute(text(
            """
            INSERT INTO items (id, name, price, deleted)
            VALUES (100, 'rr-demo', 50.00, FALSE)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, price=EXCLUDED.price, deleted=EXCLUDED.deleted
            """
        ))


def t1_repeatable_read():
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="REPEATABLE READ")
        trans = conn.begin()
        print("T1: BEGIN (REPEATABLE READ)")
        price1 = conn.execute(text("SELECT price FROM items WHERE id=100")).scalar_one()
        print(f"T1: first read price={float(price1)}")
        time.sleep(2)
        price2 = conn.execute(text("SELECT price FROM items WHERE id=100")).scalar_one()
        print(f"T1: second read price={float(price2)} (should be same)")
        trans.commit()
        print("T1: COMMIT")


def t2_updater():
    time.sleep(0.8)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="READ COMMITTED")
        trans = conn.begin()
        print("T2: BEGIN (READ COMMITTED)")
        conn.execute(text("UPDATE items SET price = price + 1 WHERE id=100"))
        print("T2: UPDATE price = price + 1")
        trans.commit()
        print("T2: COMMIT")


if __name__ == "__main__":
    ensure_demo_row()
    th1 = threading.Thread(target=t1_repeatable_read)
    th2 = threading.Thread(target=t2_updater)
    th1.start(); th2.start()
    th1.join(); th2.join()
    with engine.connect() as conn:
        final_price = conn.execute(text("SELECT price FROM items WHERE id=100")).scalar_one()
        print(f"Final price in DB: {float(final_price)}")
