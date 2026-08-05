ALTER TABLE vendor_ledger
    ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(10,2) NOT NULL DEFAULT 0;

ALTER TABLE customer_credit
    ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(10,2) NOT NULL DEFAULT 0;

UPDATE vendor_ledger SET paid_amount = amount WHERE status = 'settled';
UPDATE customer_credit SET paid_amount = amount WHERE status = 'settled';
