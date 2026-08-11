from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = [0.5, 1.0, 2.0]

_NON_RETRYABLE_STATUSES = {400, 401, 403, 404, 422, 409}


class EcommerceApiError(RuntimeError):
    pass


class EcommerceClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: list[float] | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds or list(DEFAULT_BACKOFF_SECONDS)

    async def close(self) -> None:
        await self._client.aclose()

    async def search_products(
        self, 
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {"size": 50}
        if keyword:
            params["keyword"] = keyword
        if min_price is not None:
            params["minPrice"] = min_price
        if max_price is not None:
            params["maxPrice"] = max_price
        if in_stock is not None:
            params["inStock"] = in_stock
        if created_after:
            params["createdAfter"] = created_after
            
        data = await self._request(
            "GET",
            "/products/search",
            params=params,
        )
        if isinstance(data, dict) and isinstance(data.get("content"), list):
            return data["content"]
        return data

    async def login(self, username: str, password: str) -> str:
        data = await self._request(
            "POST",
            "/users/login",
            json={"username": username, "password": password},
        )
        if not isinstance(data, str) or not data:
            raise EcommerceApiError("Login response did not contain an access token.")
        return data

    async def get_current_user(self, access_token: str) -> Any:
        return await self._request("GET", "/users/info", access_token=access_token)

    async def get_product_detail(self, product_id: int) -> Any:
        return await self._request("GET", f"/products/{product_id}")

    async def get_cart(self, access_token: str | None) -> Any:
        return await self._request("GET", "/shopping-cart", access_token=access_token)

    async def add_to_cart(
        self, product_id: int, quantity: int, access_token: str | None
    ) -> Any:
        return await self._request(
            "POST",
            "/shopping-cart/add",
            access_token=access_token,
            json={"productId": product_id, "quantity": quantity},
        )

    async def update_cart(
        self, cart_id: int, quantity: int, access_token: str | None
    ) -> Any:
        return await self._request(
            "PUT",
            f"/shopping-cart/{cart_id}",
            access_token=access_token,
            params={"quantity": quantity},
        )

    async def remove_from_cart(self, cart_id: int, access_token: str | None) -> Any:
        return await self._request(
            "DELETE", f"/shopping-cart/{cart_id}", access_token=access_token
        )

    async def clear_cart(self, access_token: str | None) -> Any:
        return await self._request("DELETE", "/shopping-cart", access_token=access_token)

    async def get_my_orders(self, access_token: str | None) -> Any:
        return await self._request("GET", "/orders", access_token=access_token)

    async def get_order_detail(self, order_id: int, access_token: str | None) -> Any:
        return await self._request(
            "GET", f"/orders/{order_id}", access_token=access_token
        )

    async def cancel_order(self, order_id: int, access_token: str | None) -> Any:
        return await self._request(
            "POST", f"/orders/{order_id}/cancel", access_token=access_token
        )

    async def create_order(
        self,
        product_id: int,
        quantity: int,
        address_id: int,
        payment_method: str,
        access_token: str | None,
    ) -> Any:
        return await self._request(
            "POST",
            "/orders",
            access_token=access_token,
            json={
                "addressId": address_id,
                "paymentMethod": payment_method,
                "items": [{"productId": product_id, "quantity": quantity}],
            },
        )

    async def pay_order(self, order_id: int, access_token: str | None) -> Any:
        return await self._request(
            "POST", f"/orders/{order_id}/pay", access_token=access_token
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method, path, headers=headers, params=params, json=json
                )
                if response.status_code in _NON_RETRYABLE_STATUSES:
                    return self._parse_response(response)
                if response.status_code >= 500:
                    if attempt >= self._max_retries:
                        break
                    delay = self._backoff_seconds[min(attempt, len(self._backoff_seconds) - 1)]
                    logger.warning(
                        "HTTP %d on %s %s (attempt %d), retrying in %.1fs",
                        response.status_code, method, path, attempt + 1, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return self._parse_response(response)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = self._backoff_seconds[min(attempt, len(self._backoff_seconds) - 1)]
                logger.warning(
                    "%s on %s %s (attempt %d), retrying in %.1fs",
                    type(exc).__name__, method, path, attempt + 1, delay,
                )
                await asyncio.sleep(delay)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                delay = self._backoff_seconds[min(attempt, len(self._backoff_seconds) - 1)]
                logger.warning(
                    "HTTPError on %s %s (attempt %d), retrying in %.1fs: %s",
                    method, path, attempt + 1, delay, exc,
                )
                await asyncio.sleep(delay)

        if last_error is not None:
            raise EcommerceApiError(
                f"E-commerce API is unavailable: {last_error}"
            ) from last_error
        raise EcommerceApiError(
            f"E-commerce API request failed after {self._max_retries + 1} attempts"
        )

    def _parse_response(self, response: httpx.Response) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise EcommerceApiError(
                f"E-commerce API returned invalid JSON (HTTP {response.status_code})"
            ) from exc

        if response.is_error:
            message = payload.get("message") if isinstance(payload, dict) else None
            raise EcommerceApiError(
                message or f"E-commerce API request failed (HTTP {response.status_code})"
            )

        if isinstance(payload, dict) and "code" in payload and "message" in payload:
            return payload.get("data")
        return payload
