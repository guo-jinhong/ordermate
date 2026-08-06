-- ============================================================
-- 电商业务演示数据增强脚本
-- 数据库: ecommerce_db
-- 用途:
--   1. 给后端业务库补充更多商品、订单、地址、购物车样例
--   2. 便于测试 Agent 搜索商品、查订单、取消订单、购物车等完整链路
--
-- 说明:
--   - 本脚本只写业务库 ecommerce_db，不创建 ecommerce_agent
--   - Agent 仍然只直接读取 ecommerce_db.knowledge
--   - 业务数据仍由 Spring Boot 后端 API 管理
--   - 使用 100+ 的固定 ID，避免和现有初始化数据冲突
-- ============================================================

USE ecommerce_db;

-- ------------------------------------------------------------
-- 分类
-- ------------------------------------------------------------
INSERT INTO categories (id, name, description, status) VALUES
    (101, 'Mobile Phones', '手机、平板和智能移动设备', 1),
    (102, 'Computers', '笔记本电脑、键鼠和办公设备', 1),
    (103, 'Audio', '耳机、音箱和音频设备', 1),
    (104, 'Smart Accessories', '智能硬件、生活电器和数码配件', 1),
    (105, 'Shoes', '跑鞋、训练鞋和户外鞋靴', 1),
    (106, 'Outdoor Clothing', '服饰、冲锋衣和保暖装备', 1)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    status = VALUES(status);

COMMIT;

-- ------------------------------------------------------------
-- 测试用户
-- 密码均为 password，便于演示登录
-- ------------------------------------------------------------
INSERT INTO users (id, username, password, email, phone, real_name, gender, status, role) VALUES
    (101, 'demo_user', '$2a$10$rCx7Ve89lmbxrFadsappSOtBET0NeqGHW4afKr3sjSAaS2CApapsu', 'demo_user@example.com', '13800138001', '张三', 1, 1, 0),
    (102, 'alice',     '$2a$10$rCx7Ve89lmbxrFadsappSOtBET0NeqGHW4afKr3sjSAaS2CApapsu', 'alice@example.com',     '13800138003', 'Alice', 2, 1, 0),
    (103, 'bob',       '$2a$10$rCx7Ve89lmbxrFadsappSOtBET0NeqGHW4afKr3sjSAaS2CApapsu', 'bob@example.com',       '13800138004', 'Bob', 1, 1, 0),
    (104, 'vip_user',  '$2a$10$rCx7Ve89lmbxrFadsappSOtBET0NeqGHW4afKr3sjSAaS2CApapsu', 'vip_user@example.com',  '13800138005', '钻石会员', 2, 1, 0)
ON DUPLICATE KEY UPDATE
    phone = VALUES(phone),
    real_name = VALUES(real_name),
    gender = VALUES(gender),
    status = VALUES(status);

COMMIT;

-- ------------------------------------------------------------
-- 商品
-- ------------------------------------------------------------
INSERT INTO products (id, name, description, price, stock, sold_count, category_id, status) VALUES
    (101, 'iPhone 15 Pro', 'A17 Pro 芯片，钛金属设计，专业级摄像系统', 8999.00, 100, 18, 101, 1),
    (102, '华为 Mate 60 Pro', '麒麟9000S 芯片，卫星通信，超可靠玄武架构', 6999.00, 80, 22, 101, 1),
    (103, '小米 14 Ultra', '骁龙8 Gen3，徕卡光学，Xiaomi HyperOS', 6499.00, 50, 13, 101, 1),
    (104, 'OPPO Find X7', '天玑9300，哈苏影像，AI 手机', 3999.00, 30, 9, 101, 1),
    (105, 'vivo X100 Pro', '蔡司光学，天玑9300，旗舰影像手机', 4999.00, 25, 11, 101, 1),
    (106, 'MacBook Pro 14', 'M3 Pro 芯片，18GB 内存，512GB 存储', 14999.00, 20, 7, 102, 1),
    (107, '联想拯救者 Y9000P', 'Intel i9-13900HX，RTX 4080，32GB DDR5', 10999.00, 15, 5, 102, 1),
    (108, '戴尔 XPS 15', 'Intel i9-13900H，RTX 4070，32GB DDR5', 12999.00, 10, 4, 102, 1),
    (109, 'ThinkPad X1 Carbon', 'Intel i7-1365U，16GB，1TB SSD，轻薄商务本', 9999.00, 12, 6, 102, 1),
    (110, 'AirPods Pro 2', '主动降噪，空间音频，USB-C 充电盒', 1899.00, 200, 38, 103, 1),
    (111, '索尼 WH-1000XM5', '行业领先降噪，高解析音频，30小时续航', 2399.00, 50, 14, 103, 1),
    (112, 'Bose QuietComfort Ultra', '沉浸音频，定制声学，蓝牙5.3', 2999.00, 30, 8, 103, 1),
    (113, '小米 Buds 4 Pro', '55dB 降噪，19mm 动圈，IP57 防水', 1299.00, 100, 19, 103, 1),
    (114, '华为 FreeBuds Pro 3', '星闪连接，双金标认证，52dB 降噪', 1499.00, 80, 16, 103, 1),
    (115, '罗技 MX Master 3S', '8K DPI，静音点击，多设备切换', 699.00, 150, 24, 104, 1),
    (116, '罗技 MX Keys Mini', '紧凑设计，背光按键，多设备连接', 599.00, 100, 21, 104, 1),
    (117, '小米智能音箱 Pro', 'Hi-Res 音质，360度环绕，智能语音控制', 499.00, 60, 12, 104, 1),
    (118, '飞利浦电动牙刷 HX9933', '智能感应刷头，4种清洁模式', 899.00, 80, 10, 104, 1),
    (119, '戴森吹风机 HD15', '负离子护发，智能温控，快速干发', 2999.00, 20, 6, 104, 1),
    (120, 'Nike Air Max 270', '经典气垫，舒适缓震，日常穿搭', 899.00, 40, 17, 105, 1),
    (121, 'Adidas Ultraboost 22', 'BOOST 中底，Primeknit 鞋面，高回弹跑鞋', 1399.00, 30, 12, 105, 1),
    (122, '李宁䨻科技跑鞋', '䨻中底科技，超临界发泡，专业跑步', 699.00, 50, 20, 105, 1),
    (123, '安踏 C10', 'SUP-FOAM 中底，纤维织面，碳板跑鞋', 1299.00, 25, 9, 105, 1),
    (124, '北脸冲锋衣', 'GORE-TEX PRO 面料，全压胶防水，户外专业', 1599.00, 15, 5, 106, 1),
    (125, '始祖鸟羽绒服', '850蓬鹅绒，防撕裂面料，极寒保暖', 4599.00, 10, 3, 106, 1),
    -- 新增：低价商品（<1000元）
    (126, '小米 Redmi 13C', '6.74英寸大屏，5000mAh 大电池，入门手机', 799.00, 200, 45, 101, 1),
    (127, '飞利浦耳机 TAT1109', '入耳式真无线，降噪，长续航', 299.00, 500, 60, 103, 1),
    (128, '小米充电宝 20000mAh', '大容量快充，移动电源', 149.00, 1000, 80, 104, 1),
    -- 新增：无库存商品（测试"无货"查询）
    (129, '华为 Mate X5 折叠屏', '7.85英寸折叠屏，麒麟9000S，旗舰折叠手机', 12999.00, 0, 3, 101, 1),
    (130, '索尼 WH-1000XM6 限量版', '顶级降噪限量版，金色外观', 3599.00, 0, 1, 103, 1),
    -- 新增：更多价格区间手机
    (131, '荣耀 90 GT', '骁龙8 Gen2，24GB内存，顶级性能', 3999.00, 35, 10, 101, 1),
    (132, 'iQOO Neo9', '骁龙8 Gen2，电竞手机，120W 快充', 2999.00, 40, 12, 101, 1),
    -- 新增：更多电脑品类
    (133, '华硕 ROG 幻16', 'AMD Ryzen 9，RTX 4070，游戏本', 15999.00, 8, 3, 102, 1),
    (134, '华为 MateBook X Pro', '3.1K OLED 触控屏，轻薄商务本', 9299.00, 15, 6, 102, 1)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    price = VALUES(price),
    stock = VALUES(stock),
    sold_count = VALUES(sold_count),
    category_id = VALUES(category_id),
    status = VALUES(status);

-- ------------------------------------------------------------
-- 收货地址
-- ------------------------------------------------------------
INSERT INTO addresses (id, user_id, name, phone, province, city, district, address, is_default) VALUES
    (101, 101, '张三', '13800138001', '广东省', '深圳市', '南山区', '科技园腾讯大厦', 1),
    (102, 101, '张三', '13800138001', '广东省', '深圳市', '福田区', '中心城卓悦中心', 0),
    (103, 102, 'Alice', '13800138003', '上海市', '上海市', '浦东新区', '陆家嘴金融中心', 1),
    (104, 103, 'Bob', '13800138004', '浙江省', '杭州市', '西湖区', '阿里巴巴园区', 1),
    (105, 104, '钻石会员', '13800138005', '北京市', '北京市', '海淀区', '中关村软件园', 1)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    phone = VALUES(phone),
    province = VALUES(province),
    city = VALUES(city),
    district = VALUES(district),
    address = VALUES(address),
    is_default = VALUES(is_default);

-- ------------------------------------------------------------
-- 购物车
-- ------------------------------------------------------------
INSERT INTO shopping_carts (id, user_id, product_id, quantity) VALUES
    (101, 101, 102, 1),
    (102, 101, 111, 2),
    (103, 102, 105, 1),
    (104, 103, 115, 1),
    (105, 103, 117, 3),
    (106, 104, 109, 1),
    (107, 104, 125, 1)
ON DUPLICATE KEY UPDATE
    quantity = VALUES(quantity);

-- ------------------------------------------------------------
-- 订单
-- 状态: 0待支付, 1已支付, 2已发货, 3已完成, 4已取消
-- 支付状态: 0未支付, 1已支付, 3已退款
-- ------------------------------------------------------------
INSERT INTO orders (
    id, order_no, user_id, total_amount, discount_amount, final_amount,
    shipping_address, shipping_phone, shipping_name,
    status, payment_status, payment_method, paid_at, shipped_at, delivered_at, remark
) VALUES
    (101, 'ORD20240101001', 101, 8999.00, 0.00, 8999.00, '广东省 深圳市 南山区 科技园腾讯大厦', '13800138001', '张三', 3, 1, 'DEMO', '2024-01-01 10:20:00', '2024-01-01 18:00:00', '2024-01-03 15:30:00', '已完成 - iPhone 15 Pro'),
    (102, 'ORD20240102002', 101, 1899.00, 0.00, 1899.00, '广东省 深圳市 南山区 科技园腾讯大厦', '13800138001', '张三', 1, 1, 'DEMO', '2024-01-02 09:15:00', NULL, NULL, '已支付 - AirPods Pro 2'),
    (103, 'ORD20240103003', 102, 14999.00, 0.00, 14999.00, '上海市 上海市 浦东新区 陆家嘴金融中心', '13800138003', 'Alice', 2, 1, 'DEMO', '2024-01-03 11:00:00', '2024-01-03 19:20:00', NULL, '已发货 - MacBook Pro 14'),
    (104, 'ORD20240104004', 102, 6499.00, 0.00, 6499.00, '上海市 上海市 浦东新区 陆家嘴金融中心', '13800138003', 'Alice', 0, 0, 'DEMO', NULL, NULL, NULL, '待支付 - 小米 14 Ultra'),
    (105, 'ORD20240105005', 103, 2999.00, 0.00, 2999.00, '浙江省 杭州市 西湖区 阿里巴巴园区', '13800138004', 'Bob', 4, 3, 'DEMO', '2024-01-05 14:30:00', NULL, NULL, '已取消 - Bose QuietComfort Ultra'),
    (106, 'ORD20240106006', 103, 1299.00, 0.00, 1299.00, '浙江省 杭州市 西湖区 阿里巴巴园区', '13800138004', 'Bob', 1, 1, 'DEMO', '2024-01-06 20:10:00', NULL, NULL, '已支付 - 小米 Buds 4 Pro'),
    (107, 'ORD20240107007', 104, 14498.00, 0.00, 14498.00, '北京市 北京市 海淀区 中关村软件园', '13800138005', '钻石会员', 3, 1, 'DEMO', '2024-01-07 08:30:00', '2024-01-07 16:00:00', '2024-01-09 12:10:00', '已完成 - 戴尔 XPS 15 + 华为 FreeBuds Pro 3'),
    (108, 'ORD20240108008', 104, 599.00, 0.00, 599.00, '北京市 北京市 海淀区 中关村软件园', '13800138005', '钻石会员', 0, 0, 'DEMO', NULL, NULL, NULL, '待支付 - 罗技 MX Keys Mini')
ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    payment_status = VALUES(payment_status),
    shipping_address = VALUES(shipping_address),
    shipping_phone = VALUES(shipping_phone),
    shipping_name = VALUES(shipping_name),
    remark = VALUES(remark),
    updated_at = CURRENT_TIMESTAMP;

-- ------------------------------------------------------------
-- 订单项
-- ------------------------------------------------------------
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
    (101, 101, 101, 1, 8999.00, 8999.00),
    (102, 102, 110, 1, 1899.00, 1899.00),
    (103, 103, 106, 1, 14999.00, 14999.00),
    (104, 104, 103, 1, 6499.00, 6499.00),
    (105, 105, 112, 1, 2999.00, 2999.00),
    (106, 106, 113, 1, 1299.00, 1299.00),
    (107, 107, 108, 1, 12999.00, 12999.00),
    (108, 107, 114, 1, 1499.00, 1499.00),
    (109, 108, 116, 1, 599.00, 599.00)
ON DUPLICATE KEY UPDATE
    quantity = VALUES(quantity),
    unit_price = VALUES(unit_price),
    total_price = VALUES(total_price);

-- ------------------------------------------------------------
-- Function Calling 演示日期
-- 固定部分商品 created_at，便于验证“2026-07 之后发布/上架”的筛选。
-- ------------------------------------------------------------
UPDATE products SET created_at = '2026-06-10 09:00:00', updated_at = CURRENT_TIMESTAMP WHERE id IN (110, 111);
UPDATE products SET created_at = '2026-07-05 09:00:00', updated_at = CURRENT_TIMESTAMP WHERE id IN (112, 113);
UPDATE products SET created_at = '2026-08-01 09:00:00', updated_at = CURRENT_TIMESTAMP WHERE id IN (114, 127, 130);
UPDATE products SET created_at = '2026-07-12 09:00:00', updated_at = CURRENT_TIMESTAMP WHERE id IN (104, 126, 132);
UPDATE products SET created_at = '2026-05-20 09:00:00', updated_at = CURRENT_TIMESTAMP WHERE id IN (128);

SELECT '业务演示数据增强完成' AS message;
SELECT COUNT(*) AS category_count FROM categories;
SELECT COUNT(*) AS product_count FROM products;
SELECT COUNT(*) AS order_count FROM orders;
SELECT COUNT(*) AS cart_count FROM shopping_carts;
