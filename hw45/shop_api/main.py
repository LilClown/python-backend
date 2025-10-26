from __future__ import annotations
from http import HTTPStatus

from typing import Annotated, Iterable, List
from dataclasses import dataclass

from fastapi import FastAPI, APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt, NonNegativeFloat


import os
from decimal import Decimal
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    Numeric,
    ForeignKey,
    select,
    func,
    update as sa_update,
)
from sqlalchemy.orm import declarative_base, relationship, Session, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/shop",
)

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()


class ItemOrm(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    deleted = Column(Boolean, nullable=False, default=False)
    cart_items = relationship("CartItemOrm", back_populates="item", cascade="all, delete-orphan")


class CartOrm(Base):
    __tablename__ = "carts"
    id = Column(Integer, primary_key=True)
    items = relationship("CartItemOrm", back_populates="cart", cascade="all, delete-orphan")


class CartItemOrm(Base):
    __tablename__ = "cart_items"
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=1)

    cart = relationship("CartOrm", back_populates="items")
    item = relationship("ItemOrm", back_populates="cart_items")


def init_db() -> None:
    import time
    for attempt in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception:
            time.sleep(1)


# id generator
def _int_id_generator() -> Iterable[int]:
    i = 0
    while True:
        yield i
        i += 1


id_generator = _int_id_generator()


# item models
@dataclass(slots=True)
class ItemInfo:
    name: str
    price: float
    deleted: bool = False


@dataclass(slots=True)
class ItemEntity:
    id: int
    info: ItemInfo


@dataclass(slots=True)
class PatchItemInfo:
    name: str | None = None
    price: float | None = None


# item store (DB-backed)
def _to_item_entity(orm: ItemOrm) -> ItemEntity:
    return ItemEntity(
        id=orm.id,
        info=ItemInfo(name=orm.name, price=float(orm.price), deleted=bool(orm.deleted)),
    )


def item_add(info: ItemInfo) -> ItemEntity:
    with SessionLocal.begin() as session:
        orm = ItemOrm(name=info.name, price=Decimal(str(info.price)), deleted=info.deleted)
        session.add(orm)
        session.flush()
        # Refresh to ensure DB-side numeric scale (e.g., 2 decimals) is reflected
        session.refresh(orm)
        return _to_item_entity(orm)


def item_delete(id: int) -> None:
    with SessionLocal.begin() as session:
        session.execute(
            sa_update(ItemOrm).where(ItemOrm.id == id).values(deleted=True)
        )


def item_get_one(id: int) -> ItemEntity | None:
    with SessionLocal() as session:
        orm = session.get(ItemOrm, id)
        if orm is None or orm.deleted:
            return None
        return _to_item_entity(orm)


def item_get_many(
    offset: int = 0,
    limit: int = 10,
    min_price: float | None = None,
    max_price: float | None = None,
    show_deleted: bool = False,
) -> Iterable[ItemEntity]:
    with SessionLocal() as session:
        stmt = select(ItemOrm)
        if not show_deleted:
            stmt = stmt.where(ItemOrm.deleted.is_(False))
        if min_price is not None:
            stmt = stmt.where(ItemOrm.price >= Decimal(str(min_price)))
        if max_price is not None:
            stmt = stmt.where(ItemOrm.price <= Decimal(str(max_price)))
        stmt = stmt.offset(offset).limit(limit)
        for orm in session.execute(stmt).scalars().all():
            yield _to_item_entity(orm)


def item_update(id: int, info: ItemInfo) -> ItemEntity | None:
    with SessionLocal.begin() as session:
        orm = session.get(ItemOrm, id, with_for_update=False)
        if orm is None or orm.deleted:
            return None
        orm.name = info.name
        orm.price = Decimal(str(info.price))
        orm.deleted = info.deleted
        session.flush()
        session.refresh(orm)
        return _to_item_entity(orm)


def item_upsert(id: int, info: ItemInfo) -> ItemEntity:
    with SessionLocal.begin() as session:
        orm = session.get(ItemOrm, id)
        if orm is None:
            orm = ItemOrm(id=id, name=info.name, price=Decimal(str(info.price)), deleted=info.deleted)
            session.add(orm)
        else:
            orm.name = info.name
            orm.price = Decimal(str(info.price))
            orm.deleted = info.deleted
        session.flush()
        session.refresh(orm)
        return _to_item_entity(orm)


def item_patch(id: int, patch_info: PatchItemInfo) -> ItemEntity | None:
    with SessionLocal.begin() as session:
        orm = session.get(ItemOrm, id)
        if orm is None or orm.deleted:
            return None
        if patch_info.name is not None:
            orm.name = patch_info.name
        if patch_info.price is not None:
            orm.price = Decimal(str(patch_info.price))
        session.flush()
        session.refresh(orm)
        return _to_item_entity(orm)


# cart models
@dataclass(slots=True)
class CartItemInfo:
    id: int
    name: str
    quantity: int
    available: bool


@dataclass(slots=True)
class CartInfo:
    items: List[CartItemInfo]
    price: float


@dataclass(slots=True)
class CartEntity:
    id: int
    info: CartInfo


@dataclass(slots=True)
class PatchCartInfo:
    items: List[CartItemInfo] | None = None
    price: float | None = None


def _cart_recalculate_by_id(session: Session, cart_id: int) -> CartInfo:
    rows = session.execute(
        select(
            CartItemOrm.item_id,
            CartItemOrm.quantity,
            ItemOrm.name,
            ItemOrm.deleted,
            ItemOrm.price,
        ).join(ItemOrm, CartItemOrm.item_id == ItemOrm.id)
        .where(CartItemOrm.cart_id == cart_id)
    ).all()
    items: list[CartItemInfo] = []
    total_price: Decimal = Decimal("0.0")
    for item_id, quantity, name, deleted, price in rows:
        available = not bool(deleted)
        if available:
            total_price += (price or Decimal("0")) * quantity
        items.append(
            CartItemInfo(
                id=item_id,
                name=name,
                quantity=quantity,
                available=available,
            )
        )
    return CartInfo(items=items, price=float(total_price))


def cart_add_empty() -> CartEntity:
    with SessionLocal.begin() as session:
        cart = CartOrm()
        session.add(cart)
        session.flush()
        info = CartInfo(items=[], price=0.0)
        return CartEntity(cart.id, info)


def cart_get_one(id: int) -> CartEntity | None:
    with SessionLocal() as session:
        cart = session.get(CartOrm, id)
        if cart is None:
            return None
        info = _cart_recalculate_by_id(session, id)
        return CartEntity(id=id, info=info)


def cart_get_many(
    offset: int = 0,
    limit: int = 10,
    min_price: float | None = None,
    max_price: float | None = None,
    min_quantity: int | None = None,
    max_quantity: int | None = None,
) -> Iterable[CartEntity]:
    with SessionLocal() as session:
        # scalars().all() returns list[int] of ids already
        cart_ids = session.execute(
            select(CartOrm.id).offset(offset).limit(limit)
        ).scalars().all()
        for cid in cart_ids:
            info = _cart_recalculate_by_id(session, cid)
            total_quantity = sum(i.quantity for i in info.items)
            if min_price is not None and info.price < min_price:
                continue
            if max_price is not None and info.price > max_price:
                continue
            if min_quantity is not None and total_quantity < min_quantity:
                continue
            if max_quantity is not None and total_quantity > max_quantity:
                continue
            yield CartEntity(cid, info)


def _cart_set_items(session: Session, cart_id: int, items: List[CartItemInfo]) -> None:
    session.query(CartItemOrm).filter(CartItemOrm.cart_id == cart_id).delete()
    for it in items:
        session.add(CartItemOrm(cart_id=cart_id, item_id=it.id, quantity=it.quantity))


def cart_update(id: int, info: CartInfo) -> CartEntity | None:
    with SessionLocal.begin() as session:
        cart = session.get(CartOrm, id)
        if cart is None:
            return None
        _cart_set_items(session, id, info.items)
        session.flush()
        recalculated = _cart_recalculate_by_id(session, id)
        return CartEntity(id=id, info=recalculated)


def cart_upsert(id: int, info: CartInfo) -> CartEntity:
    with SessionLocal.begin() as session:
        cart = session.get(CartOrm, id)
        if cart is None:
            cart = CartOrm(id=id)
            session.add(cart)
            session.flush()
        _cart_set_items(session, id, info.items)
        session.flush()
        recalculated = _cart_recalculate_by_id(session, id)
        return CartEntity(id=id, info=recalculated)


def cart_patch(id: int, patch_info: PatchCartInfo) -> CartEntity | None:
    with SessionLocal.begin() as session:
        cart = session.get(CartOrm, id)
        if cart is None:
            return None
        if patch_info.items is not None:
            _cart_set_items(session, id, patch_info.items)
        session.flush()
        recalculated = _cart_recalculate_by_id(session, id)
        return CartEntity(id=id, info=recalculated)


def cart_add_item(cart_id: int, item_id: int) -> CartEntity | None:
    with SessionLocal.begin() as session:
        cart = session.get(CartOrm, cart_id)
        if cart is None:
            return None
        ci = session.get(CartItemOrm, {"cart_id": cart_id, "item_id": item_id})
        if ci is None:
            session.add(CartItemOrm(cart_id=cart_id, item_id=item_id, quantity=1))
        else:
            ci.quantity += 1
        session.flush()
        recalculated = _cart_recalculate_by_id(session, cart_id)
        return CartEntity(id=cart_id, info=recalculated)


# item contracts
class ItemResponse(BaseModel):
    id: int
    name: str
    price: float
    deleted: bool

    @staticmethod
    def from_entity(entity: ItemEntity) -> ItemResponse:
        return ItemResponse(
            id=entity.id,
            name=entity.info.name,
            price=entity.info.price,
            deleted=entity.info.deleted,
        )


class ItemRequest(BaseModel):
    name: str
    price: float
    deleted: bool = False

    def as_item_info(self) -> ItemInfo:
        return ItemInfo(name=self.name, price=self.price, deleted=self.deleted)


class PatchItemRequest(BaseModel):
    name: str | None = None
    price: float | None = None

    model_config = ConfigDict(extra="forbid")

    def as_patch_item_info(self) -> PatchItemInfo:
        return PatchItemInfo(name=self.name, price=self.price)


# cart contracts
class CartItemResponse(BaseModel):
    id: int
    name: str
    quantity: int
    available: bool

    @staticmethod
    def from_cart_item_info(cart_item: CartItemInfo) -> CartItemResponse:
        return CartItemResponse(
            id=cart_item.id,
            name=cart_item.name,
            quantity=cart_item.quantity,
            available=cart_item.available,
        )


class CartResponse(BaseModel):
    id: int
    items: List[CartItemResponse]
    price: float

    @staticmethod
    def from_entity(entity: CartEntity) -> CartResponse:
        return CartResponse(
            id=entity.id,
            items=[CartItemResponse.from_cart_item_info(item) for item in entity.info.items],
            price=entity.info.price,
        )


class CartItemRequest(BaseModel):
    id: int
    name: str
    quantity: int
    available: bool

    def as_cart_item_info(self) -> CartItemInfo:
        return CartItemInfo(
            id=self.id,
            name=self.name,
            quantity=self.quantity,
            available=self.available,
        )


class CartRequest(BaseModel):
    items: List[CartItemRequest]
    price: float

    def as_cart_info(self) -> CartInfo:
        return CartInfo(
            items=[item.as_cart_item_info() for item in self.items],
            price=self.price,
        )


class PatchCartItemRequest(BaseModel):
    id: int | None = None
    name: str | None = None
    quantity: int | None = None
    available: bool | None = None

    model_config = ConfigDict(extra="forbid")


class PatchCartRequest(BaseModel):
    items: List[CartItemRequest] | None = None
    price: float | None = None

    model_config = ConfigDict(extra="forbid")

    def as_patch_cart_info(self) -> PatchCartInfo:
        return PatchCartInfo(
            items=[item.as_cart_item_info() for item in self.items] if self.items else None,
            price=self.price,
        )


# item router
item_router = APIRouter(prefix="/item")


@item_router.get("/")
async def get_item_list(
    offset: Annotated[NonNegativeInt, Query()] = 0,
    limit: Annotated[PositiveInt, Query()] = 10,
    min_price: Annotated[NonNegativeFloat | None, Query()] = None,
    max_price: Annotated[NonNegativeFloat | None, Query()] = None,
    show_deleted: Annotated[bool, Query()] = False,
) -> list[ItemResponse]:
    return [
        ItemResponse.from_entity(e)
        for e in item_get_many(
            offset=offset,
            limit=limit,
            min_price=min_price,
            max_price=max_price,
            show_deleted=show_deleted,
        )
    ]


@item_router.get(
    "/{id}",
    responses={
        HTTPStatus.OK: {"description": "Successfully returned requested item"},
        HTTPStatus.NOT_FOUND: {"description": "Failed to return requested item as one was not found"},
    },
)
async def get_item_by_id(id: int) -> ItemResponse:
    entity = item_get_one(id)
    if not entity:
        raise HTTPException(HTTPStatus.NOT_FOUND, f"Request resource /item/{id} was not found")
    return ItemResponse.from_entity(entity)


@item_router.post(
    "/",
    status_code=HTTPStatus.CREATED,
)
async def post_item(info: ItemRequest, response: Response) -> ItemResponse:
    entity = item_add(info.as_item_info())
    response.headers["location"] = f"/item/{entity.id}"
    return ItemResponse.from_entity(entity)


@item_router.patch(
    "/{id}",
    responses={
        HTTPStatus.OK: {"description": "Successfully patched item"},
        HTTPStatus.NOT_MODIFIED: {"description": "Failed to modify item as one was not found"},
    },
)
async def patch_item(id: int, info: PatchItemRequest) -> ItemResponse:
    entity = item_patch(id, info.as_patch_item_info())
    if entity is None:
        raise HTTPException(HTTPStatus.NOT_MODIFIED, f"Requested resource /item/{id} was not found")
    return ItemResponse.from_entity(entity)


@item_router.put(
    "/{id}",
    responses={
        HTTPStatus.OK: {"description": "Successfully updated or upserted item"},
        HTTPStatus.NOT_MODIFIED: {"description": "Failed to modify item as one was not found"},
    },
)
async def put_item(
    id: int,
    info: ItemRequest,
    upsert: Annotated[bool, Query()] = False,
) -> ItemResponse:
    entity = item_upsert(id, info.as_item_info()) if upsert else item_update(id, info.as_item_info())
    if entity is None:
        raise HTTPException(HTTPStatus.NOT_MODIFIED, f"Requested resource /item/{id} was not found")
    return ItemResponse.from_entity(entity)


@item_router.delete("/{id}")
async def delete_item(id: int) -> Response:
    item_delete(id)
    return Response("")


# cart router
cart_router = APIRouter(prefix="/cart")


@cart_router.get("/")
async def get_cart_list(
    offset: Annotated[NonNegativeInt, Query()] = 0,
    limit: Annotated[PositiveInt, Query()] = 10,
    min_price: Annotated[NonNegativeFloat | None, Query()] = None,
    max_price: Annotated[NonNegativeFloat | None, Query()] = None,
    min_quantity: Annotated[NonNegativeInt | None, Query()] = None,
    max_quantity: Annotated[NonNegativeInt | None, Query()] = None,
) -> list[CartResponse]:
    return [
        CartResponse.from_entity(e)
        for e in cart_get_many(
            offset=offset,
            limit=limit,
            min_price=min_price,
            max_price=max_price,
            min_quantity=min_quantity,
            max_quantity=max_quantity,
        )
    ]


@cart_router.get(
    "/{id}",
    responses={
        HTTPStatus.OK: {"description": "Successfully returned requested cart"},
        HTTPStatus.NOT_FOUND: {"description": "Failed to return requested cart as one was not found"},
    },
)
async def get_cart_by_id(id: int) -> CartResponse:
    entity = cart_get_one(id)
    if not entity:
        raise HTTPException(HTTPStatus.NOT_FOUND, f"Request resource /cart/{id} was not found")
    return CartResponse.from_entity(entity)


@cart_router.post(
    "/",
    status_code=HTTPStatus.CREATED,
)
async def post_cart(response: Response) -> dict[str, int]:
    entity = cart_add_empty()
    response.headers["location"] = f"/cart/{entity.id}"
    return {"id": entity.id}


@cart_router.patch(
    "/{id}",
    responses={
        HTTPStatus.OK: {"description": "Successfully patched cart"},
        HTTPStatus.NOT_MODIFIED: {"description": "Failed to modify cart as one was not found"},
    },
)
async def patch_cart(id: int, info: PatchCartRequest) -> CartResponse:
    entity = cart_patch(id, info.as_patch_cart_info())
    if entity is None:
        raise HTTPException(HTTPStatus.NOT_MODIFIED, f"Requested resource /cart/{id} was not found")
    return CartResponse.from_entity(entity)


@cart_router.put(
    "/{id}",
    responses={
        HTTPStatus.OK: {"description": "Successfully updated or upserted cart"},
        HTTPStatus.NOT_MODIFIED: {"description": "Failed to modify cart as one was not found"},
    },
)
async def put_cart(
    id: int,
    info: CartRequest,
    upsert: Annotated[bool, Query()] = False,
) -> CartResponse:
    entity = cart_upsert(id, info.as_cart_info()) if upsert else cart_update(id, info.as_cart_info())
    if entity is None:
        raise HTTPException(HTTPStatus.NOT_MODIFIED, f"Requested resource /cart/{id} was not found")
    return CartResponse.from_entity(entity)


@cart_router.post("/{cart_id}/add/{item_id}")
async def add_item(cart_id: int, item_id: int) -> Response:
    entity = cart_add_item(cart_id, item_id)
    if entity is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, f"/cart/{cart_id} not found")
    return Response("")


# app
app = FastAPI(title="Shop API")


@app.on_event("startup")
def _on_startup() -> None:
    init_db()
app.include_router(cart_router)
app.include_router(item_router)