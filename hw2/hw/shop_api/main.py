from fastapi import FastAPI

from hw2.hw.shop_api.api.cart.cart_routes import cart_router
from hw2.hw.shop_api.api.item.item_routes import item_router

app = FastAPI(title="Shop API")

app.include_router(cart_router)
app.include_router(item_router)