CREATE TABLE order_sessions (
    id UUID PRIMARY KEY,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'ORDERED', 'EXPIRED')),
    cart_version BIGINT NOT NULL DEFAULT 0 CHECK (cart_version >= 0),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_order_sessions_store_status_expires
    ON order_sessions (store_id, status, expires_at);
