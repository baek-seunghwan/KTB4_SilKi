CREATE TABLE menu_option_groups (
    id UUID PRIMARY KEY,
    menu_id UUID NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(50) NOT NULL,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    min_selections INTEGER NOT NULL DEFAULT 0 CHECK (min_selections >= 0),
    max_selections INTEGER NOT NULL DEFAULT 1 CHECK (max_selections >= min_selections),
    display_order INTEGER NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    UNIQUE (menu_id, code)
);

CREATE INDEX idx_menu_option_groups_menu_order
    ON menu_option_groups (menu_id, display_order);

CREATE TABLE menu_option_values (
    id UUID PRIMARY KEY,
    option_group_id UUID NOT NULL REFERENCES menu_option_groups(id) ON DELETE CASCADE,
    code VARCHAR(30) NOT NULL,
    name VARCHAR(50) NOT NULL,
    additional_price BIGINT NOT NULL DEFAULT 0 CHECK (additional_price >= 0),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    UNIQUE (option_group_id, code)
);

CREATE INDEX idx_menu_option_values_group_order
    ON menu_option_values (option_group_id, display_order);

CREATE UNIQUE INDEX uq_menu_option_values_default
    ON menu_option_values (option_group_id)
    WHERE is_default;
