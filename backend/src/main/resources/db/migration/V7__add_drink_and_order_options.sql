ALTER TABLE menus
    ADD COLUMN supports_hot BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN supports_ice BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN default_sweetness VARCHAR(20) NOT NULL DEFAULT 'MEDIUM'
        CHECK (default_sweetness IN ('LOW', 'MEDIUM', 'HIGH')),
    ADD COLUMN caffeinated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD CONSTRAINT chk_menus_available_temperature CHECK (supports_hot OR supports_ice);

UPDATE menus SET caffeinated = TRUE WHERE category = 'COFFEE';

ALTER TABLE order_items
    ADD COLUMN final_sweetness VARCHAR(20)
        CHECK (final_sweetness IN ('VERY_LOW', 'LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH'));

CREATE TABLE order_item_options (
    id UUID PRIMARY KEY,
    order_item_id UUID NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    option_type VARCHAR(20) NOT NULL
        CHECK (option_type IN ('TEMPERATURE', 'SIZE', 'EXTRA_SHOT', 'SWEETNESS')),
    option_code VARCHAR(20) NOT NULL,
    option_name VARCHAR(50) NOT NULL,
    additional_price BIGINT NOT NULL CHECK (additional_price >= 0),
    UNIQUE (order_item_id, option_type)
);

CREATE INDEX idx_order_item_options_item ON order_item_options (order_item_id);
