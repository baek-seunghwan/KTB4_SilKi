ALTER TABLE order_sessions
    ADD COLUMN fulfillment_type VARCHAR(20)
        CHECK (fulfillment_type IN ('DINE_IN', 'TAKEOUT'));
