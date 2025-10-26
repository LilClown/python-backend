#!/usr/bin/env python3
"""
Attempt to demonstrate dirty read and show that PostgreSQL prevents it at READ COMMITTED.

PostgreSQL does not support READ UNCOMMITTED; it is treated as READ COMMITTED.
So an uncommitted change in T1 must NOT be visible to T2.

This script:
- T1 starts a transaction, updates an item's price, FLUSHes (but does not COMMIT), sleeps, then ROLLBACKs
- T2 (READ COMMITTED) reads the item's price while T1 is sleeping
Expected: T2 sees only the last committed value (no dirty read)
"""
import os
import sys
import time
import threading
from decimal import Decimal

# Allow importing shop_api package from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shop_api.main import ItemOrm, Base, engine, SessionLocal  # type: ignore


def _ensure_schema_and_seed():
    # Create tables if not exist and seed a known row
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        it = db.get(ItemOrm, 1)
        if it is None:
            it = ItemOrm(id=1, name="Apple", price=Decimal("150.00"), deleted=False)
            db.add(it)
        else:
            it.price = Decimal("150.00")
            it.deleted = False
        db.flush()


def transaction_1():
    print("T1: BEGIN (READ COMMITTED)")
    db = SessionLocal()
    try:
        db.begin()
        item = db.get(ItemOrm, 1)
        if item is None:
            item = ItemOrm(id=1, name="Apple", price=Decimal("150.00"), deleted=False)
            db.add(item)
            db.flush()
            print("T1: Created item id=1 price=150.00")
        else:
            print(f"T1: Loaded item id=1 price={float(item.price)}")

        item.price = Decimal("200.00")
        db.flush()  # write uncommitted change
        print("T1: Changed price to 200 (NOT committed)")

        time.sleep(5)  # let T2 read while T1 is uncommitted

        print("T1: ROLLBACK")
        db.rollback()
    except Exception as e:
        print(f"T1: Error: {e}")
        db.rollback()
    finally:
        db.close()


def transaction_2():
    time.sleep(2)  # wait until T1 has flushed its uncommitted change
    print("T2: BEGIN (READ COMMITTED)")
    db = SessionLocal()
    try:
        db.begin()
        item = db.get(ItemOrm, 1)
        if item is None:
            print("T2: Item id=1 not found")
        else:
            print(f"T2: Read price={float(item.price)} (should be 150.0, NOT 200.0)")
        db.commit()
        print("T2: COMMIT")
    except Exception as e:
        print(f"T2: Error: {e}")
        db.rollback()
    finally:
        db.close()


def run_dirty_read_demo():
    _ensure_schema_and_seed()

    print("\n===== DIRTY READ (EXPECTED: PREVENTED) =====")
    print("Note: PostgreSQL treats READ UNCOMMITTED as READ COMMITTED, so dirty reads cannot occur.")

    t1 = threading.Thread(target=transaction_1)
    t2 = threading.Thread(target=transaction_2)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Check final value
    with SessionLocal() as db:
        it = db.get(ItemOrm, 1)
        print(f"Final price in DB: {float(it.price) if it else 'N/A'} (should be 150.0 after rollback)")


if __name__ == "__main__":
    run_dirty_read_demo()
