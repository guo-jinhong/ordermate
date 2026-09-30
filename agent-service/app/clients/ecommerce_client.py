from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.tracing import get_trace_id


logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = [0.5, 1.0, 2.0]

_NON_RETRYABLE_STATUSES = {400, 401, 403, 404, 422, 409}


class EcommerceApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "ECOMMERCE_API_ERROR",
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class EcommerceClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: list[float] | None = None,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        hostname = (urlsplit(normalized_base_url).hostname or "").lower()
        # 本机 Java 服务不应经过系统 HTTP(S)_PROXY，否则部分开发环境会把
        # localhost 请求送到代理并返回 502，表现为“Agent 连不上后端”。
        trust_env = hostname not in {"localhost", "127.0.0.1", "::1"}
        # 细粒度超时：连接阶段 5s，读写阶段按传入值，避免慢连接长期占用连接池
        self._client = httpx.AsyncClient(
            base_url=normalized_base_url,
            trust_env=trust_env,
            timeout=httpx.Timeout(
                connect=5.0,
                read=timeout_seconds,
                write=timeout_seconds,
                pool=5.0,
            ),
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

    async def get_addresses(self, access_token: str | None) -> Any:
        return await self._request("GET", "/addresses", access_token=access_token)

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

    async def refund_order(
        self, order_id: int, access_token: str | None, reason: str | None = None
    ) -> Any:
        """U1-1: 申请售后退款。"""
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return await self._request(
            "POST", f"/orders/{order_id}/refund", access_token=access_token, json=body
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
        # O1-2: 传播 trace_id 到后端，实现全链路追踪
        trace_id = get_trace_id()
        if trace_id and trace_id != "-":
            headers["X-Trace-Id"] = trace_id

        last_error: Exception | None = None
        last_status: int | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method, path, headers=headers, params=params, json=json
                )
                if response.status_code in _NON_RETRYABLE_STATUSES:
                    return self._parse_response(response)
                if response.status_code >= 500:
                    last_status = response.status_code
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
                "业务服务暂时不可用，请稍后重试。",
                code="ECOMMERCE_BACKEND_UNAVAILABLE",
                retryable=True,
            ) from last_error
        raise EcommerceApiError(
            "业务服务暂时异常，请稍后重试。",
            code="ECOMMERCE_BACKEND_5XX",
            status_code=last_status,
            retryable=True,
        )

    def _parse_response(self, response: httpx.Response) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise EcommerceApiError(
                f"业务服务返回了无法识别的数据（HTTP {response.status_code}）。",
                code="ECOMMERCE_BACKEND_INVALID_RESPONSE",
                status_code=response.status_code,
            ) from exc

        if response.is_error:
            message = payload.get("message") if isinstance(payload, dict) else None
            raise EcommerceApiError(
                message or f"业务服务请求失败（HTTP {response.status_code}）。",
                code=f"ECOMMERCE_BACKEND_HTTP_{response.status_code}",
                status_code=response.status_code,
            )

        if isinstance(payload, dict) and "code" in payload and "message" in payload:
            return payload.get("data")
        return payload
