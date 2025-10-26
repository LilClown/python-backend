#!/usr/bin/env python3
"""
Show that phantom reads are prevented at SERIALIZABLE isolation in PostgreSQL.
T1: SERIALIZABLE, counts rows; T2 inserts a matching row and commits; T1 repeats count (no change) and on commit may raise a serialization error.
"""
import os
import threading
import time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/shop")
engine = create_engine(DATABASE_URL, future=True)


def cleanup():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM items WHERE name LIKE 'serial-%'"))


def t1_serializable():
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="SERIALIZABLE")
        trans = conn.begin()
        print("T1: BEGIN (SERIALIZABLE)")
        cnt1 = conn.execute(text("SELECT COUNT(*) FROM items WHERE price >= 50 AND deleted = FALSE")).scalar_one()
        print(f"T1: first count={cnt1}")
        time.sleep(2)
        cnt2 = conn.execute(text("SELECT COUNT(*) FROM items WHERE price >= 50 AND deleted = FALSE")).scalar_one()
        print(f"T1: second count (should be same)={cnt2}")
        try:
            trans.commit()
            print("T1: COMMIT (no serialization failure)")
        except OperationalError as e:
            print(f"T1: COMMIT failed with serialization error: {e}")


def t2_inserter():
    time.sleep(0.8)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="READ COMMITTED")
        trans = conn.begin()
        print("T2: BEGIN (READ COMMITTED)")
        conn.execute(text("INSERT INTO items (name, price, deleted) VALUES ('serial-1', 100.00, FALSE)"))
        print("T2: INSERT serial-1")
        trans.commit()
        print("T2: COMMIT")


if __name__ == "__main__":
    cleanup()
    th1 = threading.Thread(target=t1_serializable)
    th2 = threading.Thread(target=t2_inserter)
    th1.start(); th2.start()
    th1.join(); th2.join()
