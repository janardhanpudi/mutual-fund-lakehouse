-- Run once in the Neon SQL editor, as the project owner.
-- Creates the schema the app reads from and a read-only role for it.

CREATE SCHEMA IF NOT EXISTS mf_serving;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mf_reader') THEN
        CREATE ROLE mf_reader NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA mf_serving TO mf_reader;

-- The app's login user. Choose the password yourself, keep it in .env only:
--   CREATE USER mf_app WITH PASSWORD '<choose one>' IN ROLE mf_reader;
