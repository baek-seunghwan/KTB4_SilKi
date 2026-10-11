ALTER TABLE admin_stores
    ADD CONSTRAINT uq_admin_stores_admin UNIQUE (admin_id);
