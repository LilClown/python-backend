#!/usr/bin/env python3
"""
Demonstrate phantom reads under READ COMMITTED in PostgreSQL using SQLAlchemy.
"""
import os
import threading
import time
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/shop")
engine = create_engine(DATABASE_URL, future=True)


def prepare_table():
    # clean demo rows with name like 'phantom%'
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM items WHERE name LIKE 'phantom%'"))


def t1_counter():
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="READ COMMITTED")
        trans = conn.begin()
        print("T1: BEGIN (READ COMMITTED)")
        cnt1 = conn.execute(text("SELECT COUNT(*) FROM items WHERE price >= 50 AND deleted = FALSE")).scalar_one()
        print(f"T1: first count={cnt1}")
        time.sleep(2)
        cnt2 = conn.execute(text("SELECT COUNT(*) FROM items WHERE price >= 50 AND deleted = FALSE")).scalar_one()
        print(f"T1: second count={cnt2} (phantom if increased)")
        trans.commit()
        print("T1: COMMIT")


def t2_inserter():
    time.sleep(0.8)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="READ COMMITTED")
        trans = conn.begin()
        print("T2: BEGIN (READ COMMITTED)")
        conn.execute(text("INSERT INTO items (name, price, deleted) VALUES ('phantom-1', 100.00, FALSE)"))
        print("T2: INSERT phantom-1")
        trans.commit()
        print("T2: COMMIT")


if __name__ == "__main__":
    prepare_table()
    th1 = threading.Thread(target=t1_counter)
    th2 = threading.Thread(target=t2_inserter)
    th1.start(); th2.start()
    th1.join(); th2.join()
