-- 幂等键按用户隔离；历史订单的 NULL 不影响唯一索引。
ALTER TABLE orders ADD COLUMN idempotency_key VARCHAR(128) NULL;
ALTER TABLE orders ADD COLUMN request_hash VARCHAR(64) NULL;
CREATE UNIQUE INDEX uk_order_user_intent ON orders(user_id, idempotency_key);
