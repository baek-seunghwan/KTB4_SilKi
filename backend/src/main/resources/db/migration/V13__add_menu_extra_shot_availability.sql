ALTER TABLE menus ADD COLUMN supports_extra_shot BOOLEAN;

UPDATE menus SET supports_extra_shot = TRUE;

ALTER TABLE menus
    ALTER COLUMN supports_extra_shot SET NOT NULL,
    ALTER COLUMN supports_extra_shot SET DEFAULT FALSE;
