ALTER TABLE orders
    ADD COLUMN order_session_id UUID REFERENCES order_sessions(id) ON DELETE SET NULL,
    ADD COLUMN fulfillment_type VARCHAR(20)
        CHECK (fulfillment_type IN ('DINE_IN', 'TAKEOUT')),
    ADD COLUMN payment_method VARCHAR(30) NOT NULL DEFAULT 'PAY_AT_COUNTER'
        CHECK (payment_method IN ('PAY_AT_COUNTER'));

CREATE UNIQUE INDEX uq_orders_order_session
    ON orders (order_session_id)
    WHERE order_session_id IS NOT NULL;
