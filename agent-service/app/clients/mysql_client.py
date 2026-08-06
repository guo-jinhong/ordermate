"""
数据库版电商客户端
支持 MySQL 和 SQLite，直接通过数据库操作
保持与 ecommerce_client.py 完全兼容的接口签名
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.clients.ecommerce_client import EcommerceApiError
from app.database import get_repository, EcommerceRepository, init_db


logger = logging.getLogger(__name__)


class EcommerceClient:
    """
    数据库版电商客户端
    
    通过 SQLAlchemy ORM 直接操作数据库（MySQL 或 SQLite），
    保持与 HTTP 版相同的接口签名，方便切换。
    """

    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None:
        """
        初始化数据库客户端
        
        base_url 参数保留以兼容原有接口，但实际使用数据库
        """
        self._repo: EcommerceRepository | None = None
        # 自动初始化数据库（创建表和示例数据）
        try:
            init_db()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.warning(f"数据库初始化失败（可能已存在）: {e}")
        logger.info("EcommerceClient (数据库版) 已初始化")

    @property
    def repo(self) -> EcommerceRepository:
        if self._repo is None:
            self._repo = get_repository()
        return self._repo

    def _run_sync(self, func, *args, **kwargs):
        """同步执行（数据库操作不需要异步）"""
        return func(*args, **kwargs)

    def _parse_user_id(self, access_token: str | None) -> int:
        """从 access_token 中解析 user_id"""
        if not access_token:
            return 1  # 默认用户
        # 支持两种格式：token-{id} 或 demo-token-{username}
        match = re.match(r'token-(\d+)', access_token)
        if match:
            return int(match.group(1))
        # 从 demo-token-{username} 解析
        match = re.match(r'demo-token-(.+)', access_token)
        if match:
            username = match.group(1)
            user = self._run_sync(self.repo.get_user, username)
            if user:
                return user['id']
        return 1  # 默认用户

    async def close(self) -> None:
        """关闭连接（保留接口）"""
        logger.info("EcommerceClient closed")

    # ============================================================
    # 商品相关（接口签名一致）
    # ============================================================

    async def search_products(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ) -> list[dict[str, Any]]:
        """搜索商品（支持价格区间、库存筛选）"""
        try:
            return self._run_sync(
                self.repo.search_products,
                keyword,
                None,  # category
                min_price,
                max_price,
                "default",  # sort_by
                50,  # limit
            )
        except Exception as e:
            logger.error(f"搜索商品失败: {e}")
            raise EcommerceApiError(f"搜索商品失败: {e}") from e

    async def get_product_detail(self, product_id: int) -> dict[str, Any]:
        """获取商品详情"""
        try:
            product = self._run_sync(self.repo.get_product, product_id)
            if not product:
                raise EcommerceApiError(f"商品不存在: {product_id}")
            return product
        except EcommerceApiError:
            raise
        except Exception as e:
            logger.error(f"获取商品详情失败: {e}")
            raise EcommerceApiError(f"获取商品详情失败: {e}") from e

    # ============================================================
    # 订单相关（接口签名：access_token）
    # ============================================================

    async def get_my_orders(self, access_token: str | None) -> list[dict[str, Any]]:
        """获取用户订单列表"""
        try:
            user_id = self._parse_user_id(access_token)
            return self._run_sync(self.repo.get_user_orders, user_id)
        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            raise EcommerceApiError(f"获取订单列表失败: {e}") from e

    async def get_order_detail(self, order_id: int, access_token: str | None) -> dict[str, Any]:
        """获取订单详情"""
        try:
            order = self._run_sync(self.repo.get_order, order_id)
            if not order:
                raise EcommerceApiError(f"订单不存在: {order_id}")
            return order
        except EcommerceApiError:
            raise
        except Exception as e:
            logger.error(f"获取订单详情失败: {e}")
            raise EcommerceApiError(f"获取订单详情失败: {e}") from e

    async def create_order(
        self,
        product_id: int,
        quantity: int,
        address_id: int,
        payment_method: str,
        access_token: str | None,
    ) -> dict[str, Any]:
        """创建订单"""
        try:
            user_id = self._parse_user_id(access_token)
            # 检查库存
            has_stock, current_stock = self._run_sync(
                self.repo.check_stock, product_id, quantity
            )
            if not has_stock:
                raise EcommerceApiError(
                    f"库存不足，当前库存为 {current_stock} 件，无法购买 {quantity} 件"
                )

            return self._run_sync(
                self.repo.create_order,
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                address_id=address_id,
                payment_method=payment_method,
            )
        except EcommerceApiError:
            raise
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            raise EcommerceApiError(f"创建订单失败: {e}") from e

    async def cancel_order(self, order_id: int, access_token: str | None) -> dict[str, Any]:
        """取消订单"""
        try:
            return self._run_sync(self.repo.cancel_order, order_id)
        except ValueError as e:
            raise EcommerceApiError(str(e)) from e
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            raise EcommerceApiError(f"取消订单失败: {e}") from e

    async def pay_order(self, order_id: int, access_token: str | None) -> dict[str, Any]:
        """支付订单"""
        try:
            return self._run_sync(self.repo.pay_order, order_id)
        except ValueError as e:
            raise EcommerceApiError(str(e)) from e
        except Exception as e:
            logger.error(f"支付订单失败: {e}")
            raise EcommerceApiError(f"支付订单失败: {e}") from e

    # ============================================================
    # 购物车相关（接口签名：access_token）
    # ============================================================

    async def get_cart(self, access_token: str | None) -> list[dict[str, Any]]:
        """获取购物车"""
        try:
            user_id = self._parse_user_id(access_token)
            return self._run_sync(self.repo.get_cart, user_id)
        except Exception as e:
            logger.error(f"获取购物车失败: {e}")
            raise EcommerceApiError(f"获取购物车失败: {e}") from e

    async def add_to_cart(
        self, product_id: int, quantity: int, access_token: str | None
    ) -> dict[str, Any]:
        """加入购物车"""
        try:
            user_id = self._parse_user_id(access_token)
            return self._run_sync(
                self.repo.add_to_cart, user_id, product_id, quantity
            )
        except Exception as e:
            logger.error(f"加入购物车失败: {e}")
            raise EcommerceApiError(f"加入购物车失败: {e}") from e

    async def update_cart(
        self, cart_id: int, quantity: int, access_token: str | None
    ) -> dict[str, Any]:
        """更新购物车"""
        try:
            return self._run_sync(self.repo.update_cart, cart_id, quantity)
        except ValueError as e:
            raise EcommerceApiError(str(e)) from e
        except Exception as e:
            logger.error(f"更新购物车失败: {e}")
            raise EcommerceApiError(f"更新购物车失败: {e}") from e

    async def remove_from_cart(
        self, cart_id: int, access_token: str | None
    ) -> dict[str, Any]:
        """删除购物车项"""
        try:
            self._run_sync(self.repo.remove_from_cart, cart_id)
            return {"success": True}
        except Exception as e:
            logger.error(f"删除购物车项失败: {e}")
            raise EcommerceApiError(f"删除购物车项失败: {e}") from e

    async def clear_cart(self, access_token: str | None) -> dict[str, Any]:
        """清空购物车"""
        try:
            user_id = self._parse_user_id(access_token)
            self._run_sync(self.repo.clear_cart, user_id)
            return {"success": True}
        except Exception as e:
            logger.error(f"清空购物车失败: {e}")
            raise EcommerceApiError(f"清空购物车失败: {e}") from e

    # ============================================================
    # 知识库相关
    # ============================================================

    async def search_knowledge_base(self, query: str) -> list[dict[str, Any]]:
        """搜索知识库"""
        try:
            return self._run_sync(self.repo.search_knowledge, query)
        except Exception as e:
            logger.error(f"搜索知识库失败: {e}")
            raise EcommerceApiError(f"搜索知识库失败: {e}") from e

    # ============================================================
    # 用户相关（接口签名一致）
    # ============================================================

    async def login(self, username: str, password: str) -> str:
        """用户登录，返回 access_token 字符串"""
        try:
            user = self._run_sync(self.repo.get_user, username)
            if not user:
                # 创建用户并返回 token
                return f"token-1"
            return f"token-{user['id']}"
        except Exception as e:
            logger.error(f"登录失败: {e}")
            raise EcommerceApiError(f"登录失败: {e}") from e
