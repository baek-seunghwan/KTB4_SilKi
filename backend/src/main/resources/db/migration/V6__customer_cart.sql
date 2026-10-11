CREATE TABLE cart_items (
    id UUID PRIMARY KEY,
    order_session_id UUID NOT NULL REFERENCES order_sessions(id) ON DELETE CASCADE,
    menu_id UUID NOT NULL REFERENCES menus(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cart_items_session_created
    ON cart_items (order_session_id, created_at);

CREATE TABLE cart_item_options (
    cart_item_id UUID NOT NULL REFERENCES cart_items(id) ON DELETE CASCADE,
    option_value_id UUID NOT NULL REFERENCES menu_option_values(id) ON DELETE RESTRICT,
    PRIMARY KEY (cart_item_id, option_value_id)
);

CREATE INDEX idx_cart_item_options_value
    ON cart_item_options (option_value_id);
