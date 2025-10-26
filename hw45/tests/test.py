from __future__ import annotations

import os
from http import HTTPStatus
from typing import Any

import pytest
from fastapi.testclient import TestClient
import sys
import pathlib


if "DATABASE_URL" not in os.environ:
	os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_shop_api.db"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from shop_api import main as app_module  

@pytest.fixture(autouse=True)
def _clean_db():
	db_url = os.environ.get("DATABASE_URL", "")
	if db_url.startswith("sqlite"):
		app_module.Base.metadata.drop_all(bind=app_module.engine)
		app_module.Base.metadata.create_all(bind=app_module.engine)
	yield


from typing import Iterator


@pytest.fixture()
def client() -> Iterator[TestClient]:
	with TestClient(app_module.app) as c:
		yield c


def create_item(client: TestClient, name: str, price: float, deleted: bool = False) -> dict[str, Any]:
	resp = client.post("/item", json={"name": name, "price": price, "deleted": deleted})
	assert resp.status_code == HTTPStatus.CREATED
	return resp.json()


def create_cart(client: TestClient) -> int:
	resp = client.post("/cart")
	assert resp.status_code == HTTPStatus.CREATED
	return resp.json()["id"]


def test_item_crud_and_filters(client: TestClient) -> None:
	i1 = create_item(client, "apple", 10.0)
	i2 = create_item(client, "banana", 5.0)
	i3 = create_item(client, "cherry", 20.0)

	r = client.delete(f"/item/{i2['id']}")
	assert r.status_code == HTTPStatus.OK

	r = client.get(f"/item/{i1['id']}")
	assert r.status_code == HTTPStatus.OK
	assert r.json()["name"] == "apple"

	r = client.get("/item/999999")
	assert r.status_code == HTTPStatus.NOT_FOUND

	r = client.get("/item")
	assert r.status_code == HTTPStatus.OK
	names = [x["name"] for x in r.json()]
	assert set(names) == {"apple", "cherry"}

	r = client.get("/item", params={"show_deleted": True})
	names = [x["name"] for x in r.json()]
	assert set(names) == {"apple", "banana", "cherry"}

	r = client.get("/item", params={"min_price": 9.99})
	assert {x["name"] for x in r.json()} <= {"apple", "cherry"}
	r = client.get("/item", params={"max_price": 10.0})
	assert {x["name"] for x in r.json()} <= {"apple"}

	r = client.get("/item", params={"offset": 1, "limit": 1, "show_deleted": True})
	assert r.status_code == HTTPStatus.OK
	assert len(r.json()) == 1

	r = client.patch(f"/item/{i1['id']}", json={"name": "apple-new"})
	assert r.status_code == HTTPStatus.OK
	assert r.json()["name"] == "apple-new"

	r = client.patch("/item/123456", json={"price": 42.0})
	assert r.status_code == HTTPStatus.NOT_MODIFIED

	r = client.put(
		f"/item/{i3['id']}",
		json={"name": "cherry-2", "price": 21.0, "deleted": False},
	)
	assert r.status_code == HTTPStatus.OK
	assert r.json()["name"] == "cherry-2"

	r = client.put("/item/9999", json={"name": "new", "price": 1.0, "deleted": False})
	assert r.status_code == HTTPStatus.NOT_MODIFIED

	r = client.put(
		"/item/5555",
		params={"upsert": True},
		json={"name": "upserted", "price": 2.5, "deleted": False},
	)
	assert r.status_code == HTTPStatus.OK
	assert r.json()["id"] == 5555

	iid = i1["id"]
	assert client.delete(f"/item/{iid}").status_code == HTTPStatus.OK
	assert client.get(f"/item/{iid}").status_code == HTTPStatus.NOT_FOUND
	data = client.get("/item").json()
	assert all(x["id"] != iid for x in data)


def test_item_validation_errors(client: TestClient) -> None:
	assert client.get("/item", params={"limit": 0}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY

	itm = create_item(client, "x", 1.0)
	r = client.patch(
		f"/item/{itm['id']}",
		json={"name": "y", "odd": "field"},
	)
	assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_patch_deleted_item_returns_not_modified(client: TestClient) -> None:
	itm = create_item(client, "tmp", 3.14)
	assert client.delete(f"/item/{itm['id']}").status_code == HTTPStatus.OK
	r = client.patch(f"/item/{itm['id']}", json={"price": 1.0})
	assert r.status_code == HTTPStatus.NOT_MODIFIED

	r = client.put(f"/item/{itm['id']}", json={"name": "x", "price": 1.0, "deleted": False})
	assert r.status_code == HTTPStatus.NOT_MODIFIED


def test_cart_crud_recalc_and_filters(client: TestClient) -> None:
	a = create_item(client, "A", 10.0)
	b = create_item(client, "B", 5.0)
	c = create_item(client, "C", 2.0)

	assert client.delete(f"/item/{b['id']}").status_code == HTTPStatus.OK

	cart_id = create_cart(client)
	body = {
		"items": [
			{"id": a["id"], "name": a["name"], "quantity": 2, "available": True},
			{"id": b["id"], "name": b["name"], "quantity": 3, "available": False},
		],
		"price": 0.0,
	}
	r = client.put(f"/cart/{cart_id}", json=body)
	assert r.status_code == HTTPStatus.OK
	data = r.json()
	assert data["price"] == pytest.approx(20.0, 1e-8)
	items = {i["id"]: i for i in data["items"]}
	assert items[b["id"]]["available"] is False

	r = client.post(f"/cart/{cart_id}/add/{a['id']}")
	assert r.status_code == HTTPStatus.OK
	data = client.get(f"/cart/{cart_id}").json()
	items = {i["id"]: i for i in data["items"]}
	assert items[a["id"]]["quantity"] == 3
	assert data["price"] == pytest.approx(30.0, 1e-8)

	r = client.patch(
		f"/cart/{cart_id}",
		json={
			"items": [
				{"id": c["id"], "name": c["name"], "quantity": 5, "available": True}
			]
		},
	)
	assert r.status_code == HTTPStatus.OK
	assert r.json()["price"] == pytest.approx(10.0, 1e-8)

	r = client.put(
		"/cart/9876",
		params={"upsert": True},
		json={
			"items": [
				{"id": a["id"], "name": a["name"], "quantity": 1, "available": True},
				{"id": c["id"], "name": c["name"], "quantity": 2, "available": True},
			],
			"price": 0.0,
		},
	)
	assert r.status_code == HTTPStatus.OK
	assert r.json()["id"] == 9876

	c1 = create_cart(client)
	client.put(
		f"/cart/{c1}",
		json={
			"items": [{"id": a["id"], "name": a["name"], "quantity": 1, "available": True}],
			"price": 0.0,
		},
	)  
	c2 = create_cart(client)
	client.put(
		f"/cart/{c2}",
		json={
			"items": [{"id": c["id"], "name": c["name"], "quantity": 4, "available": True}],
			"price": 0.0,
		},
	)  
	r = client.get("/cart", params={"min_price": 9.0})
	assert all(cart["price"] >= 9.0 for cart in r.json())
	r = client.get("/cart", params={"max_price": 9.0})
	assert all(cart["price"] <= 9.0 for cart in r.json())
	r = client.get("/cart", params={"min_quantity": 2})
	assert all(sum(i["quantity"] for i in cart["items"]) >= 2 for cart in r.json())
	r = client.get("/cart", params={"max_quantity": 2})
	assert all(sum(i["quantity"] for i in cart["items"]) <= 2 for cart in r.json())

	assert client.get("/cart/424242").status_code == HTTPStatus.NOT_FOUND
	assert client.post("/cart/424242/add/1").status_code == HTTPStatus.NOT_FOUND


def test_cart_validation_errors(client: TestClient) -> None:
	assert client.get("/cart", params={"limit": 0}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY

	cid = create_cart(client)
	r = client.patch(
		f"/cart/{cid}",
		json={"items": [], "price": 0.0, "extra": "forbidden"},
	)
	assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_internal_id_generator_covered() -> None:
	gen = app_module._int_id_generator()
	assert [next(gen), next(gen), next(gen)] == [0, 1, 2]
