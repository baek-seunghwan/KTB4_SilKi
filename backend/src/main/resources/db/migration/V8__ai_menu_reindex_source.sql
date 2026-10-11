CREATE TABLE menu_reindex_revisions (
    store_id UUID PRIMARY KEY REFERENCES stores(id) ON DELETE CASCADE,
    source_revision BIGINT NOT NULL CHECK (source_revision >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE VIEW ai_menu_source AS
SELECT
    store_id,
    id AS menu_id,
    name,
    COALESCE(description, '') AS description,
    CASE
        WHEN category = 'COFFEE' THEN 'coffee'
        WHEN category = 'TEA' THEN 'tea'
        WHEN category = 'BEVERAGE' AND name LIKE '%에이드%' THEN 'ade'
        WHEN category = 'BEVERAGE' AND name LIKE '%스무디%' THEN 'smoothie'
        ELSE NULL
    END AS category,
    CASE
        WHEN supports_hot AND NOT supports_ice THEN 'hot'
        WHEN supports_ice AND NOT supports_hot THEN 'ice'
        ELSE NULL
    END AS temperature,
    LOWER(default_sweetness) AS sweetness,
    CASE WHEN caffeinated THEN 'normal' ELSE 'none' END AS caffeine,
    ARRAY[]::TEXT[] AS flavor_tags,
    sales_status = 'AVAILABLE' AS is_available
FROM menus;

COMMENT ON VIEW ai_menu_source IS
    'Read-only authoritative menu source for the Silki AI reindexer.';
