-- One row per AMFI scheme variant, holding its current details.
-- updated_at changes only when a row is actually updated (see the loader in Step 3).

CREATE TABLE IF NOT EXISTS scheme_master (
    scheme_code            text PRIMARY KEY,
    scheme_name            text NOT NULL,
    plan                   text,
    option                 text,
    isin_growth_or_payout  text,
    isin_reinvestment      text,
    category_raw           text,
    amc                    text NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now()
);

-- A trigger: the database itself sets updated_at on every UPDATE, so no code can forget to.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS scheme_master_set_updated_at ON scheme_master;
CREATE TRIGGER scheme_master_set_updated_at
    BEFORE UPDATE ON scheme_master
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- CDC asks "which rows changed since X?", so index that column.
CREATE INDEX IF NOT EXISTS scheme_master_updated_at_idx ON scheme_master (updated_at);