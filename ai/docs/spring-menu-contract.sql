-- Read-only contract check for the Spring-owned authoritative menu source.
-- Spring migration V8 creates public.ai_menu_source; the AI service must never
-- create or modify this view. Run this as the AI database role after deployment.
-- A successful zero-row result proves that the relation is readable and exposes
-- columns that can satisfy the runtime query types.

SELECT
    store_id::TEXT,
    menu_id::TEXT,
    name,
    COALESCE(description, '') AS description,
    category::TEXT,
    temperature::TEXT,
    sweetness::TEXT,
    caffeine::TEXT,
    COALESCE(flavor_tags, ARRAY[]::TEXT[]) AS flavor_tags,
    is_available IS TRUE AS is_available
FROM public.ai_menu_source
LIMIT 0;
