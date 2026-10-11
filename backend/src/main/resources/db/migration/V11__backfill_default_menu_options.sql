INSERT INTO menu_option_groups
    (id, menu_id, code, name, required, min_selections, max_selections, display_order)
SELECT gen_random_uuid(), m.id, 'TEMPERATURE', '온도', TRUE, 1, 1, 0
FROM menus m
WHERE NOT EXISTS (
    SELECT 1 FROM menu_option_groups g WHERE g.menu_id = m.id AND g.code = 'TEMPERATURE'
);

INSERT INTO menu_option_groups
    (id, menu_id, code, name, required, min_selections, max_selections, display_order)
SELECT gen_random_uuid(), m.id, 'SIZE', '사이즈', TRUE, 1, 1, 1
FROM menus m
WHERE NOT EXISTS (
    SELECT 1 FROM menu_option_groups g WHERE g.menu_id = m.id AND g.code = 'SIZE'
);

INSERT INTO menu_option_groups
    (id, menu_id, code, name, required, min_selections, max_selections, display_order)
SELECT gen_random_uuid(), m.id, 'EXTRA_SHOT', '샷 추가', FALSE, 0, 1, 2
FROM menus m
WHERE m.caffeinated
  AND NOT EXISTS (
      SELECT 1 FROM menu_option_groups g WHERE g.menu_id = m.id AND g.code = 'EXTRA_SHOT'
  );

INSERT INTO menu_option_groups
    (id, menu_id, code, name, required, min_selections, max_selections, display_order)
SELECT gen_random_uuid(), m.id, 'SWEETNESS', '당도', FALSE, 0, 1, 3
FROM menus m
WHERE NOT EXISTS (
    SELECT 1 FROM menu_option_groups g WHERE g.menu_id = m.id AND g.code = 'SWEETNESS'
);

INSERT INTO menu_option_values
    (id, option_group_id, code, name, additional_price, is_default, display_order)
SELECT gen_random_uuid(), g.id, 'HOT', '따뜻하게', 0,
       NOT m.supports_ice AND NOT EXISTS (
           SELECT 1 FROM menu_option_values existing
           WHERE existing.option_group_id = g.id AND existing.is_default
       ), 0
FROM menu_option_groups g
JOIN menus m ON m.id = g.menu_id
WHERE g.code = 'TEMPERATURE'
  AND m.supports_hot
  AND NOT EXISTS (
      SELECT 1 FROM menu_option_values v WHERE v.option_group_id = g.id AND v.code = 'HOT'
  );

INSERT INTO menu_option_values
    (id, option_group_id, code, name, additional_price, is_default, display_order)
SELECT gen_random_uuid(), g.id, 'ICE', '차갑게', 0,
       NOT m.supports_hot AND NOT EXISTS (
           SELECT 1 FROM menu_option_values existing
           WHERE existing.option_group_id = g.id AND existing.is_default
       ), 1
FROM menu_option_groups g
JOIN menus m ON m.id = g.menu_id
WHERE g.code = 'TEMPERATURE'
  AND m.supports_ice
  AND NOT EXISTS (
      SELECT 1 FROM menu_option_values v WHERE v.option_group_id = g.id AND v.code = 'ICE'
  );

INSERT INTO menu_option_values
    (id, option_group_id, code, name, additional_price, is_default, display_order)
SELECT gen_random_uuid(), g.id, option.code, option.name, option.additional_price,
       option.code = 'REGULAR' AND NOT EXISTS (
           SELECT 1 FROM menu_option_values existing
           WHERE existing.option_group_id = g.id AND existing.is_default
       ), option.display_order
FROM menu_option_groups g
CROSS JOIN (VALUES
    ('REGULAR', '레귤러', 0::BIGINT, 0),
    ('LARGE', '라지', 500::BIGINT, 1)
) AS option(code, name, additional_price, display_order)
WHERE g.code = 'SIZE'
  AND NOT EXISTS (
      SELECT 1 FROM menu_option_values v
      WHERE v.option_group_id = g.id AND v.code = option.code
  );

INSERT INTO menu_option_values
    (id, option_group_id, code, name, additional_price, is_default, display_order)
SELECT gen_random_uuid(), g.id, option.code, option.name, option.additional_price,
       option.code = 'NONE' AND NOT EXISTS (
           SELECT 1 FROM menu_option_values existing
           WHERE existing.option_group_id = g.id AND existing.is_default
       ), option.display_order
FROM menu_option_groups g
CROSS JOIN (VALUES
    ('NONE', '추가 안 함', 0::BIGINT, 0),
    ('SHOT_1', '샷 1회 추가', 500::BIGINT, 1),
    ('SHOT_2', '샷 2회 추가', 1000::BIGINT, 2)
) AS option(code, name, additional_price, display_order)
WHERE g.code = 'EXTRA_SHOT'
  AND NOT EXISTS (
      SELECT 1 FROM menu_option_values v
      WHERE v.option_group_id = g.id AND v.code = option.code
  );

INSERT INTO menu_option_values
    (id, option_group_id, code, name, additional_price, is_default, display_order)
SELECT gen_random_uuid(), g.id, option.code, option.name, 0,
       option.code = 'NORMAL' AND NOT EXISTS (
           SELECT 1 FROM menu_option_values existing
           WHERE existing.option_group_id = g.id AND existing.is_default
       ), option.display_order
FROM menu_option_groups g
CROSS JOIN (VALUES
    ('LESS', '덜 달게', 0),
    ('NORMAL', '보통', 1),
    ('MORE', '더 달게', 2)
) AS option(code, name, display_order)
WHERE g.code = 'SWEETNESS'
  AND NOT EXISTS (
      SELECT 1 FROM menu_option_values v
      WHERE v.option_group_id = g.id AND v.code = option.code
  );
