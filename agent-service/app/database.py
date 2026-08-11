"""
数据库模型和连接配置
支持 MySQL 和 SQLite 两种数据库
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    create_engine,
    desc,
    or_,
    text,
)
from sqlalchemy.orm import (
    Session,
    declarative_base,
    relationship,
    sessionmaker,
)


# ============================================================
# 数据库连接配置
# ============================================================

def _detect_db_type() -> str:
    """检测数据库类型"""
    return os.getenv("DB_TYPE", "sqlite").lower()


def get_database_url() -> str:
    """获取数据库连接 URL"""
    db_type = _detect_db_type()
    
    if db_type == "mysql":
        host = os.getenv("MYSQL_HOST", "127.0.0.1")
        port = os.getenv("MYSQL_PORT", "3306")
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "123456")
        database = os.getenv("MYSQL_DATABASE", "ecommerce_db")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    else:
        # SQLite 模式
        db_path = os.getenv("SQLITE_PATH", "agent_service_dev.db")
        return f"sqlite:///{db_path}"


# 创建引擎
db_type = _detect_db_type()

if db_type == "mysql":
    engine = create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )
else:
    # SQLite 不需要连接池参数
    engine = create_engine(
        get_database_url(),
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        connect_args={"check_same_thread": False},  # 允许多线程访问
    )

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()
ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


# ============================================================
# ORM 模型定义
# ============================================================

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    nickname = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    orders = relationship("Order", back_populates="user")
    cart_items = relationship("CartItem", back_populates="user")
    addresses = relationship("Address", back_populates="user")


class Product(Base):
    """商品表"""
    __tablename__ = "products"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category = Column(String(64), nullable=False, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class Order(Base):
    """订单表"""
    __tablename__ = "orders"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    order_no = Column(String(32), unique=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(SmallInteger, nullable=False, default=0)
    final_amount = Column(Numeric(10, 2), nullable=False)
    address_id = Column(Integer, default=1)
    payment_method = Column(String(32), default="DEMO")
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """订单项表"""
    __tablename__ = "order_items"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class CartItem(Base):
    """购物车表"""
    __tablename__ = "cart_items"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    selected = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")


class Address(Base):
    """收货地址表"""
    __tablename__ = "addresses"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    receiver_name = Column(String(64), nullable=False)
    receiver_phone = Column(String(20), nullable=False)
    province = Column(String(32), nullable=False)
    city = Column(String(32), nullable=False)
    district = Column(String(32), nullable=False)
    detail = Column(String(200), nullable=False)
    is_default = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="addresses")


class Knowledge(Base):
    """知识库表"""
    __tablename__ = "knowledge"

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    category = Column(String(64), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    keywords = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = "system_configs"

    config_key = Column(String(64), primary_key=True)
    config_value = Column(Text, nullable=False)
    description = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============================================================
# 数据库操作工具函数
# ============================================================

def get_session() -> Session:
    """获取数据库会话"""
    return SessionLocal()


def ensure_connection() -> bool:
    """测试数据库连接"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ============================================================
# 数据库初始化
# ============================================================

def init_db() -> None:
    """初始化数据库（创建表和示例数据）"""
    Base.metadata.create_all(engine)
    
    # 检查是否已有数据
    with SessionLocal() as session:
        existing = session.query(Product).count()
        if existing == 0:
            _seed_sample_data(session)
            logger.info("✅ 示例数据已创建")


def _seed_sample_data(session: Session) -> None:
    """插入示例数据"""
    from datetime import datetime
    import time as time_module
    
    # 用户
    users = [
        User(username="demo_user", password_hash="sha256:123456", nickname="演示用户"),
        User(username="test_user", password_hash="sha256:test123", nickname="测试用户"),
        User(username="alice", password_hash="sha256:alice2024", nickname="Alice"),
        User(username="bob", password_hash="sha256:bob2024", nickname="Bob"),
    ]
    session.add_all(users)
    
    # 商品
    products = [
        Product(name="iPhone 15 Pro", category="手机", price=8999.00, stock=100, description="A17 Pro 芯片，钛金属设计"),
        Product(name="华为 Mate 60 Pro", category="手机", price=6999.00, stock=80, description="麒麟9000S 芯片，卫星通信"),
        Product(name="小米 14 Ultra", category="手机", price=6499.00, stock=50, description="骁龙8 Gen3，徕卡光学"),
        Product(name="OPPO Find X7", category="手机", price=3999.00, stock=30, description="天玑9300，哈苏影像"),
        Product(name="vivo X100 Pro", category="手机", price=4999.00, stock=25, description="蔡司光学，天玑9300"),
        Product(name="MacBook Pro 14", category="电脑", price=14999.00, stock=20, description="M3 Pro 芯片"),
        Product(name="联想拯救者 Y9000P", category="电脑", price=10999.00, stock=15, description="Intel i9，RTX 4080"),
        Product(name="戴尔 XPS 15", category="电脑", price=12999.00, stock=10, description="Intel i9，RTX 4070"),
        Product(name="ThinkPad X1 Carbon", category="电脑", price=9999.00, stock=12, description="Intel i7，16GB，1TB SSD"),
        Product(name="AirPods Pro 2", category="耳机", price=1899.00, stock=200, description="主动降噪，空间音频"),
        Product(name="索尼 WH-1000XM5", category="耳机", price=2399.00, stock=50, description="行业领先降噪"),
        Product(name="Bose QuietComfort Ultra", category="耳机", price=2999.00, stock=30, description="Immersive Audio"),
        Product(name="小米 Buds 4 Pro", category="耳机", price=1299.00, stock=100, description="55dB 降噪"),
        Product(name="华为 FreeBuds Pro 3", category="耳机", price=1499.00, stock=80, description="星闪连接，双金标认证"),
        Product(name="罗技 MX Master 3S", category="配件", price=699.00, stock=150, description="8K DPI，静音点击"),
        Product(name="罗技 MX Keys Mini", category="配件", price=599.00, stock=100, description="紧凑设计，背光按键"),
        Product(name="小米智能音箱 Pro", category="配件", price=499.00, stock=60, description="Hi-Res 音质，360环绕"),
        Product(name="飞利浦电动牙刷 HX9933", category="配件", price=899.00, stock=80, description="智能感应刷头"),
        Product(name="戴森吹风机 HD15", category="配件", price=2999.00, stock=20, description="负离子护发，智能温控"),
        Product(name="Nike Air Max 270", category="鞋靴", price=899.00, stock=40, description="经典气垫，舒适缓震"),
        Product(name="Adidas Ultraboost 22", category="鞋靴", price=1399.00, stock=30, description="BOOST 中底，Primeknit 鞋面"),
        Product(name="李宁䨻科技跑鞋", category="鞋靴", price=699.00, stock=50, description="䨻中底科技，超临界发泡"),
        Product(name="安踏 C10", category="鞋靴", price=1299.00, stock=25, description="SUP-FOAM 中底，纤维织面"),
        Product(name="北脸冲锋衣", category="服饰", price=1599.00, stock=15, description="GORE-TEX PRO 面料"),
        Product(name="始祖鸟羽绒服", category="服饰", price=4599.00, stock=10, description="850蓬鹅绒，NISMO 防撕裂"),
    ]
    session.add_all(products)
    
    session.flush()
    
    # 订单
    orders = [
        Order(order_no="ORD20240101001", user_id=1, status=3, final_amount=8999.00, remark="已完成 - iPhone 15 Pro"),
        Order(order_no="ORD20240102002", user_id=1, status=1, final_amount=1899.00, remark="已支付 - AirPods Pro 2"),
        Order(order_no="ORD20240103003", user_id=2, status=2, final_amount=14999.00, remark="已发货 - MacBook Pro 14"),
        Order(order_no="ORD20240104004", user_id=2, status=0, final_amount=6499.00, remark="待支付 - 小米 14 Ultra"),
        Order(order_no="ORD20240105005", user_id=3, status=4, final_amount=2399.00, remark="已取消 - Sony WH-1000XM5"),
        Order(order_no="ORD20240106006", user_id=3, status=1, final_amount=1299.00, remark="已支付 - 小米 Buds 4 Pro"),
        Order(order_no="ORD20240107007", user_id=4, status=3, final_amount=14498.00, remark="已完成 - 戴尔 XPS 15 + FreeBuds"),
        Order(order_no="ORD20240108008", user_id=4, status=0, final_amount=599.00, remark="待支付 - 罗技 MX Keys Mini"),
    ]
    session.add_all(orders)
    
    session.flush()
    
    # 订单项
    order_items = [
        OrderItem(order_id=1, product_id=1, product_name="iPhone 15 Pro", quantity=1, unit_price=8999.00, subtotal=8999.00),
        OrderItem(order_id=2, product_id=10, product_name="AirPods Pro 2", quantity=1, unit_price=1899.00, subtotal=1899.00),
        OrderItem(order_id=3, product_id=6, product_name="MacBook Pro 14", quantity=1, unit_price=14999.00, subtotal=14999.00),
        OrderItem(order_id=4, product_id=3, product_name="小米 14 Ultra", quantity=1, unit_price=6499.00, subtotal=6499.00),
        OrderItem(order_id=5, product_id=11, product_name="索尼 WH-1000XM5", quantity=1, unit_price=2399.00, subtotal=2399.00),
        OrderItem(order_id=6, product_id=13, product_name="小米 Buds 4 Pro", quantity=1, unit_price=1299.00, subtotal=1299.00),
        OrderItem(order_id=7, product_id=8, product_name="戴尔 XPS 15", quantity=1, unit_price=12999.00, subtotal=12999.00),
        OrderItem(order_id=7, product_id=14, product_name="华为 FreeBuds Pro 3", quantity=1, unit_price=1499.00, subtotal=1499.00),
        OrderItem(order_id=8, product_id=16, product_name="罗技 MX Keys Mini", quantity=1, unit_price=599.00, subtotal=599.00),
    ]
    session.add_all(order_items)
    
    # 购物车
    cart_items = [
        CartItem(user_id=1, product_id=2, quantity=1),
        CartItem(user_id=1, product_id=11, quantity=2),
        CartItem(user_id=2, product_id=5, quantity=1),
        CartItem(user_id=3, product_id=15, quantity=1),
        CartItem(user_id=3, product_id=17, quantity=3),
        CartItem(user_id=4, product_id=9, quantity=1),
    ]
    session.add_all(cart_items)
    
    # 地址
    addresses = [
        Address(user_id=1, receiver_name="张三", receiver_phone="13800138001", province="广东省", city="深圳市", district="南山区", detail="科技园腾讯大厦", is_default=1),
        Address(user_id=1, receiver_name="张三", receiver_phone="13800138001", province="广东省", city="深圳市", district="福田区", detail="中心城卓悦中心", is_default=0),
        Address(user_id=2, receiver_name="李四", receiver_phone="13800138002", province="北京市", city="北京市", district="海淀区", detail="中关村创业大厦", is_default=1),
        Address(user_id=3, receiver_name="Alice", receiver_phone="13800138003", province="上海市", city="上海市", district="浦东新区", detail="陆家嘴金融中心", is_default=1),
        Address(user_id=4, receiver_name="Bob", receiver_phone="13800138004", province="浙江省", city="杭州市", district="西湖区", detail="阿里巴巴集团", is_default=1),
    ]
    session.add_all(addresses)
    
    # 知识库
    knowledge_items = [
        Knowledge(category="refund", title="退款政策", content="商品支持7天无理由退货，需保持商品完好、配件齐全。退款将在收到退货后3-7个工作日内处理。", keywords="退款 退货 无理由 7天"),
        Knowledge(category="refund", title="退款到账时间", content="原路退回至支付账户，支付宝/微信1-3个工作日，银行卡3-7个工作日。", keywords="退款 到账 原路返回 支付"),
        Knowledge(category="return", title="换货流程", content="登录账户→我的订单→选择需换货订单→申请换货→填写换货原因→客服审核→寄回商品→收到新品。", keywords="换货 流程 申请 审核"),
        Knowledge(category="payment", title="支付方式", content="支持支付宝、微信支付、银联云闪付、花呗分期（3/6/12期）、信用卡快捷支付。", keywords="支付 方式 支付宝 微信 分期"),
        Knowledge(category="payment", title="优惠券使用", content="结算时自动匹配最优优惠券，不可与其他优惠叠加。每笔订单限用一张优惠券。", keywords="优惠券 优惠 叠加 结算"),
        Knowledge(category="shipping", title="配送时间", content="下单后24小时内发货，一线城市1-3天送达，偏远地区3-7天送达。", keywords="配送 发货 时间 物流"),
        Knowledge(category="shipping", title="运费说明", content="单笔订单满99元免运费，不足99元收取10元运费。偏远地区可能额外加收。", keywords="运费 包邮 配送 偏远地区"),
        Knowledge(category="rules", title="发票开具", content="支持电子普通发票和增值税专用发票。下单时选择需要发票并填写抬头信息。", keywords="发票 抬头 电子 增值税"),
        Knowledge(category="rules", title="会员等级", content="普通会员-银卡-金卡-钻石。等级由近12个月消费额决定，享专属折扣和优先客服。", keywords="会员 等级 折扣 积分"),
        Knowledge(category="rules", title="积分规则", content="每消费1元积1分，积分可抵现（100积分=1元），也可兑换礼品。积分有效期12个月。", keywords="积分 抵现 兑换 有效期"),
        Knowledge(category="rules", title="VIP权益", content="钻石会员享95折优惠、免费顺丰、专属客服、生日礼包、优先购买限量商品。", keywords="VIP 钻石 特权 折扣"),
        Knowledge(category="service", title="客服时间", content="在线客服9:00-23:00，电话客服400-xxx-xxxx（工作日9:00-18:00）。", keywords="客服 时间 电话 在线"),
        Knowledge(category="service", title="投诉处理", content="投诉将在24小时内响应，3个工作日内给出解决方案。不满意可申请升级处理。", keywords="投诉 处理 响应 升级"),
    ]
    session.add_all(knowledge_items)
    
    # 系统配置
    configs = [
        SystemConfig(config_key="order_prefix", config_value="ORD", description="订单号前缀"),
        SystemConfig(config_key="order_expire_minutes", config_value="30", description="待支付订单超时时间(分钟)"),
        SystemConfig(config_key="max_quantity_per_order", config_value="99", description="单笔订单最大购买数量"),
        SystemConfig(config_key="stock_warning_threshold", config_value="10", description="库存预警阈值"),
        SystemConfig(config_key="default_payment_method", config_value="DEMO", description="默认支付方式"),
        SystemConfig(config_key="version", config_value="1.0.0", description="系统版本"),
    ]
    session.add_all(configs)
    
    session.commit()
    logger.info(f"示例数据已创建: {len(products)} 商品, {len(orders)} 订单, {len(knowledge_items)} 知识")


# 添加 logger
import logging
logger = logging.getLogger(__name__)


# ============================================================
# 业务查询辅助类
# ============================================================

class EcommerceRepository:
    """电商数据仓库 - 封装所有数据库操作"""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    # ---------- 商品相关 ----------

    def search_products(
        self,
        keyword: str,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        sort_by: str = "default",
        limit: int = 20,
        in_stock: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        搜索商品（支持分类、价格区间、排序、库存筛选）
        
        Args:
            keyword: 搜索关键词
            category: 商品分类（手机/电脑/耳机等）
            min_price: 最低价格
            max_price: 最高价格
            sort_by: 排序方式（default/price_asc/price_desc/stock_desc）
            limit: 返回数量
            in_stock: 是否只显示有货商品
        """
        query = self.session.query(Product)
        
        # 关键词搜索
        if keyword:
            query = query.filter(
                or_(
                    Product.name.like(f"%{keyword}%"),
                    Product.category.like(f"%{keyword}%"),
                    Product.description.like(f"%{keyword}%"),
                )
            )
        
        # 分类筛选
        if category:
            query = query.filter(Product.category == category)
        
        # 价格区间
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        
        # 库存筛选
        if in_stock is True:
            query = query.filter(Product.stock > 0)
        elif in_stock is False:
            query = query.filter(Product.stock == 0)
        
        # 排序
        if sort_by == "price_asc":
            query = query.order_by(Product.price.asc())
        elif sort_by == "price_desc":
            query = query.order_by(Product.price.desc())
        elif sort_by == "stock_desc":
            query = query.order_by(Product.stock.desc())
        else:
            query = query.order_by(Product.id.asc())
        
        products = query.limit(limit).all()
        return [self._product_to_dict(p) for p in products]

    def get_categories(self) -> list[dict[str, Any]]:
        """获取所有商品分类"""
        from sqlalchemy import func
        results = (
            self.session.query(
                Product.category,
                func.count(Product.id).label("count"),
                func.min(Product.price).label("min_price"),
                func.max(Product.price).label("max_price"),
            )
            .group_by(Product.category)
            .all()
        )
        return [
            {
                "category": r[0],
                "count": r[1],
                "min_price": float(r[2]) if r[2] else 0,
                "max_price": float(r[3]) if r[3] else 0,
            }
            for r in results
        ]

    def get_product(self, product_id: int) -> dict[str, Any] | None:
        """获取商品详情"""
        product = self.session.query(Product).filter(Product.id == product_id).first()
        if product:
            return self._product_to_dict(product)
        return None

    def check_stock(self, product_id: int, quantity: int) -> tuple[bool, int]:
        """检查库存"""
        product = self.session.query(Product).filter(Product.id == product_id).first()
        if not product:
            return False, 0
        return product.stock >= quantity, product.stock

    # ---------- 订单相关 ----------

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        """获取订单详情"""
        order = self.session.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        result = self._order_to_dict(order)
        # 加载订单项
        items = self.session.query(OrderItem).filter(OrderItem.order_id == order_id).all()
        result["items"] = [self._order_item_to_dict(item) for item in items]
        return result

    def get_user_orders(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """获取用户订单列表"""
        orders = (
            self.session.query(Order)
            .filter(Order.user_id == user_id)
            .order_by(desc(Order.created_at))
            .limit(limit)
            .all()
        )
        return [self._order_to_dict(o) for o in orders]

    def create_order(
        self,
        user_id: int,
        product_id: int,
        quantity: int,
        address_id: int = 1,
        payment_method: str = "DEMO",
    ) -> dict[str, Any]:
        """创建订单"""
        product = self.session.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"商品不存在: {product_id}")

        subtotal = product.price * quantity
        order_no = self._generate_order_no()

        order = Order(
            order_no=order_no,
            user_id=user_id,
            status=0,  # 待支付
            final_amount=subtotal,
            address_id=address_id,
            payment_method=payment_method,
        )
        self.session.add(order)
        self.session.flush()

        order_item = OrderItem(
            order_id=order.id,
            product_id=product_id,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
            subtotal=subtotal,
        )
        self.session.add(order_item)

        # 扣减库存
        product.stock -= quantity

        self.session.commit()
        return self._order_to_dict(order)

    def cancel_order(self, order_id: int) -> dict[str, Any]:
        """取消订单"""
        order = self.session.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"订单不存在: {order_id}")
        if order.status != 0:
            raise ValueError(f"只有待支付订单可以取消")

        # 恢复库存
        items = self.session.query(OrderItem).filter(OrderItem.order_id == order_id).all()
        for item in items:
            product = self.session.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity

        order.status = 4  # 已取消
        self.session.commit()
        return self._order_to_dict(order)

    def pay_order(self, order_id: int) -> dict[str, Any]:
        """支付订单"""
        order = self.session.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"订单不存在: {order_id}")
        if order.status != 0:
            raise ValueError(f"订单状态不允许支付")

        order.status = 1  # 已支付
        self.session.commit()
        return self._order_to_dict(order)

    # ---------- 购物车相关 ----------

    def get_cart(self, user_id: int) -> list[dict[str, Any]]:
        """获取购物车"""
        items = (
            self.session.query(CartItem)
            .filter(CartItem.user_id == user_id)
            .all()
        )
        result = []
        for item in items:
            product = self.session.query(Product).filter(Product.id == item.product_id).first()
            if product:
                result.append({
                    "cartId": item.id,
                    "productId": product.id,
                    "productName": product.name,
                    "price": float(product.price),
                    "quantity": item.quantity,
                    "stock": product.stock,
                })
        return result

    def add_to_cart(self, user_id: int, product_id: int, quantity: int = 1) -> dict[str, Any]:
        """加入购物车"""
        existing = (
            self.session.query(CartItem)
            .filter(CartItem.user_id == user_id, CartItem.product_id == product_id)
            .first()
        )
        if existing:
            existing.quantity += quantity
            self.session.commit()
            return {"id": existing.id, "quantity": existing.quantity}

        item = CartItem(user_id=user_id, product_id=product_id, quantity=quantity)
        self.session.add(item)
        self.session.commit()
        return {"id": item.id, "quantity": item.quantity}

    def update_cart(self, cart_id: int, quantity: int) -> dict[str, Any]:
        """更新购物车项数量"""
        item = self.session.query(CartItem).filter(CartItem.id == cart_id).first()
        if not item:
            raise ValueError(f"购物车项不存在: {cart_id}")
        if quantity <= 0:
            self.session.delete(item)
        else:
            item.quantity = quantity
        self.session.commit()
        return {"id": cart_id, "quantity": quantity}

    def remove_from_cart(self, cart_id: int) -> None:
        """删除购物车项"""
        item = self.session.query(CartItem).filter(CartItem.id == cart_id).first()
        if item:
            self.session.delete(item)
            self.session.commit()

    def clear_cart(self, user_id: int) -> None:
        """清空购物车"""
        self.session.query(CartItem).filter(CartItem.user_id == user_id).delete()
        self.session.commit()

    # ---------- 数据统计相关 ----------

    def get_statistics(self) -> dict[str, Any]:
        """获取平台统计数据"""
        from sqlalchemy import func
        
        # 商品总数
        total_products = self.session.query(func.count(Product.id)).scalar() or 0
        
        # 订单总数和总金额
        total_orders = self.session.query(func.count(Order.id)).scalar() or 0
        total_revenue = self.session.query(func.sum(Order.final_amount)).filter(
            Order.status.in_([1, 2, 3])  # 已支付/已发货/已完成
        ).scalar() or 0
        
        # 用户总数
        total_users = self.session.query(func.count(User.id)).scalar() or 0
        
        # 库存总值
        total_stock_value = self.session.query(
            func.sum(Product.price * Product.stock)
        ).scalar() or 0
        
        return {
            "totalProducts": total_products,
            "totalOrders": total_orders,
            "totalRevenue": float(total_revenue),
            "totalUsers": total_users,
            "totalStockValue": float(total_stock_value),
        }

    def get_hot_products(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取热门商品（根据订单数量）"""
        from sqlalchemy import func
        
        results = (
            self.session.query(
                Product,
                func.count(OrderItem.id).label("order_count"),
                func.sum(OrderItem.quantity).label("total_sold"),
            )
            .outerjoin(OrderItem, Product.id == OrderItem.product_id)
            .group_by(Product.id)
            .order_by(func.count(OrderItem.id).desc())
            .limit(limit)
            .all()
        )
        
        hot_products = []
        for product, order_count, total_sold in results:
            if order_count > 0:
                product_dict = self._product_to_dict(product)
                product_dict["orderCount"] = order_count
                product_dict["totalSold"] = total_sold or 0
                hot_products.append(product_dict)
        
        # 如果没有订单，按库存排序返回
        if not hot_products:
            products = self.session.query(Product).order_by(Product.stock.desc()).limit(limit).all()
            hot_products = [self._product_to_dict(p) for p in products]
        
        return hot_products

    def get_orders_by_status(self) -> list[dict[str, Any]]:
        """按状态统计订单"""
        from sqlalchemy import func
        
        results = (
            self.session.query(
                Order.status,
                func.count(Order.id).label("count"),
                func.sum(Order.final_amount).label("total"),
            )
            .group_by(Order.status)
            .all()
        )
        
        status_map = {
            0: "待支付",
            1: "已支付",
            2: "已发货",
            3: "已完成",
            4: "已取消",
        }
        
        return [
            {
                "status": r[0],
                "statusLabel": status_map.get(r[0], "未知"),
                "count": r[1],
                "totalAmount": float(r[2]) if r[2] else 0,
            }
            for r in results
        ]

    # ---------- 知识库相关 ----------

    def search_knowledge(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """搜索知识库"""
        query_builder = self.session.query(Knowledge)
        query = (query or "").strip()
        if query:
            keyword = f"%{query}%"
            query_builder = query_builder.filter(
                or_(
                    Knowledge.title.like(keyword),
                    Knowledge.content.like(keyword),
                    Knowledge.keywords.like(keyword),
                )
            )
        results = query_builder.order_by(Knowledge.id.asc()).limit(limit).all()
        return [self._knowledge_to_dict(k) for k in results]

    # ---------- 用户相关 ----------

    def get_user(self, username: str) -> dict[str, Any] | None:
        """根据用户名获取用户"""
        user = self.session.query(User).filter(User.username == username).first()
        if user:
            return {"id": user.id, "username": user.username, "nickname": user.nickname}
        return None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        """根据用户 ID 获取用户。"""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user:
            return {"id": user.id, "username": user.username, "nickname": user.nickname}
        return None

    # ---------- 工具方法 ----------

    def _generate_order_no(self) -> str:
        """生成订单号"""
        import time as time_module
        timestamp = time_module.strftime("%Y%m%d%H%M%S")
        random_part = str(int(time_module.time() * 1000) % 10000).zfill(4)
        return f"ORD{timestamp}{random_part}"

    def _product_to_dict(self, product: Product) -> dict[str, Any]:
        return {
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "price": float(product.price),
            "stock": product.stock,
            "description": product.description,
        }

    def _order_to_dict(self, order: Order) -> dict[str, Any]:
        return {
            "id": order.id,
            "orderNo": order.order_no,
            "userId": order.user_id,
            "status": order.status,
            "finalAmount": float(order.final_amount),
            "paymentMethod": order.payment_method,
            "remark": order.remark,
            "createdAt": order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else None,
            "updatedAt": order.updated_at.strftime("%Y-%m-%d %H:%M:%S") if order.updated_at else None,
        }

    def _order_item_to_dict(self, item: OrderItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "productId": item.product_id,
            "productName": item.product_name,
            "quantity": item.quantity,
            "unitPrice": float(item.unit_price),
            "subtotal": float(item.subtotal),
        }

    def _knowledge_to_dict(self, k: Knowledge) -> dict[str, Any]:
        return {
            "id": k.id,
            "category": k.category,
            "title": k.title,
            "content": k.content,
            "keywords": k.keywords,
        }


# ============================================================
# 便捷函数
# ============================================================

def get_repository() -> EcommerceRepository:
    """获取数据仓库实例"""
    return EcommerceRepository()
