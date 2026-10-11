CREATE TABLE admin_users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stores (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    operating_status VARCHAR(20) NOT NULL CHECK (operating_status IN ('OPEN', 'CLOSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE admin_stores (
    admin_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    PRIMARY KEY (admin_id, store_id)
);

CREATE TABLE menus (
    id UUID PRIMARY KEY,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    category VARCHAR(20) NOT NULL CHECK (category IN ('COFFEE', 'BEVERAGE', 'TEA')),
    name VARCHAR(50) NOT NULL,
    price BIGINT NOT NULL CHECK (price >= 0),
    image_key VARCHAR(500),
    sales_status VARCHAR(20) NOT NULL CHECK (sales_status IN ('AVAILABLE', 'SOLD_OUT')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store_id, name)
);

CREATE INDEX idx_menus_store_category_created
    ON menus (store_id, category, created_at DESC);

CREATE SEQUENCE order_number_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE RESTRICT,
    order_number BIGINT NOT NULL UNIQUE,
    idempotency_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('RECEIVED', 'PREPARING', 'COMPLETED')),
    total_price BIGINT NOT NULL CHECK (total_price >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store_id, idempotency_key)
);

CREATE INDEX idx_orders_store_created
    ON orders (store_id, created_at DESC);

CREATE TABLE order_items (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_id UUID NOT NULL,
    menu_name VARCHAR(50) NOT NULL,
    unit_price BIGINT NOT NULL CHECK (unit_price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
    subtotal BIGINT NOT NULL CHECK (subtotal >= 0)
);

CREATE INDEX idx_order_items_order ON order_items (order_id);
