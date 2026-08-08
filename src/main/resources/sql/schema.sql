-- =====================================================================
-- Ecommerce Order System - Schema (MySQL 8.x)
--
-- Notes:
-- * Spring Boot is configured with `spring.jpa.hibernate.ddl-auto=update`,
--   so Hibernate will create/migrate tables automatically in dev. This
--   script exists as a reference + for manual provisioning (prod, CI).
-- * Run on an empty database. To re-init, drop the schema and re-create.
-- * Column types and nullability match the JPA entities under
--   src/main/java/com/ecommerce/entity.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ecommerce_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE ecommerce_db;

-- ---------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    username     VARCHAR(64)  NOT NULL,
    password     VARCHAR(255) NOT NULL,
    email        VARCHAR(128) NOT NULL,
    phone        VARCHAR(32)  NULL,
    real_name    VARCHAR(64)  NULL,
    gender       INT          NULL COMMENT '0:unknown 1:male 2:female',
    avatar       VARCHAR(500) NULL,
    status       INT          NOT NULL DEFAULT 1 COMMENT '1:active 0:inactive',
    role         INT          NOT NULL DEFAULT 0 COMMENT '0:user 1:admin',
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username),
    UNIQUE KEY uk_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- categories
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    name         VARCHAR(64)  NOT NULL,
    description  VARCHAR(255) NULL,
    image_url    VARCHAR(500) NULL,
    status       INT          NOT NULL DEFAULT 1 COMMENT '1:active 0:inactive',
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_categories_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id           BIGINT         NOT NULL AUTO_INCREMENT,
    name         VARCHAR(255)   NOT NULL,
    description  VARCHAR(1000)  NULL,
    price        DECIMAL(10, 2) NOT NULL,
    stock        INT            NOT NULL,
    sold_count   INT            NOT NULL DEFAULT 0,
    image_url    VARCHAR(500)   NULL,
    category_id  BIGINT         NULL,
    status       INT            NOT NULL DEFAULT 1 COMMENT '1:on sale 0:off sale',
    created_at   TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_products_category (category_id),
    CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- addresses
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS addresses (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    user_id     BIGINT       NOT NULL,
    name        VARCHAR(64)  NOT NULL,
    phone       VARCHAR(32)  NOT NULL,
    province    VARCHAR(64)  NOT NULL,
    city        VARCHAR(64)  NOT NULL,
    district    VARCHAR(64)  NOT NULL,
    address     VARCHAR(255) NOT NULL,
    is_default  INT          NOT NULL DEFAULT 0 COMMENT '0:no 1:yes',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_addresses_user (user_id),
    CONSTRAINT fk_addresses_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- shopping_carts
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shopping_carts (
    id          BIGINT    NOT NULL AUTO_INCREMENT,
    user_id     BIGINT    NOT NULL,
    product_id  BIGINT    NOT NULL,
    quantity    INT       NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_cart_user_product (user_id, product_id),
    KEY idx_cart_user (user_id),
    KEY idx_cart_product (product_id),
    CONSTRAINT fk_cart_user    FOREIGN KEY (user_id)    REFERENCES users (id),
    CONSTRAINT fk_cart_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- orders
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id                BIGINT         NOT NULL AUTO_INCREMENT,
    order_no          VARCHAR(64)    NOT NULL,
    user_id           BIGINT         NOT NULL,
    total_amount      DECIMAL(10, 2) NOT NULL,
    discount_amount   DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    final_amount      DECIMAL(10, 2) NOT NULL,
    shipping_address  VARCHAR(500)   NULL,
    shipping_phone    VARCHAR(32)    NULL,
    shipping_name     VARCHAR(64)    NULL,
    status            INT            NOT NULL DEFAULT 0 COMMENT '0:pending 1:paid 2:shipped 3:delivered 4:cancelled',
    payment_status    INT            NOT NULL DEFAULT 0 COMMENT '0:unpaid 1:paid 2:refunding 3:refunded',
    payment_method    VARCHAR(32)    NULL,
    paid_at           DATETIME       NULL,
    shipped_at        DATETIME       NULL,
    delivered_at      DATETIME       NULL,
    remark            VARCHAR(500)   NULL,
    created_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_orders_order_no (order_no),
    KEY idx_orders_user (user_id),
    KEY idx_orders_status (status),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- order_items
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id          BIGINT         NOT NULL AUTO_INCREMENT,
    order_id    BIGINT         NOT NULL,
    product_id  BIGINT         NOT NULL,
    quantity    INT            NOT NULL,
    unit_price  DECIMAL(10, 2) NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    created_at  TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_order_items_order   (order_id),
    KEY idx_order_items_product (product_id),
    CONSTRAINT fk_order_items_order   FOREIGN KEY (order_id)   REFERENCES orders (id) ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- reviews
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id          BIGINT    NOT NULL AUTO_INCREMENT,
    product_id  BIGINT    NOT NULL,
    user_id     BIGINT    NOT NULL,
    rating      INT       NOT NULL COMMENT '1-5 stars',
    content     TEXT      NULL,
    like_count  INT       NOT NULL DEFAULT 0,
    status      INT       NOT NULL DEFAULT 0 COMMENT '0:pending 1:approved',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_reviews_product (product_id),
    KEY idx_reviews_user    (user_id),
    CONSTRAINT fk_reviews_product FOREIGN KEY (product_id) REFERENCES products (id),
    CONSTRAINT fk_reviews_user    FOREIGN KEY (user_id)    REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
