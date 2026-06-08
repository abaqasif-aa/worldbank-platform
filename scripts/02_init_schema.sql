-- Create schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

-- Raw indicator records (bronze layer)
CREATE TABLE IF NOT EXISTS raw.indicator_records (
    id              SERIAL PRIMARY KEY,
    country_code    CHAR(3)       NOT NULL,
    indicator_code  VARCHAR(30)   NOT NULL,
    indicator_name  VARCHAR(60)   NOT NULL,
    year            SMALLINT      NOT NULL,
    value           NUMERIC(20,4),
    ingested_at     TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (country_code, indicator_code, year)
);

-- Country metadata (loaded separately)
CREATE TABLE IF NOT EXISTS raw.country_metadata (
    country_code    CHAR(3)       PRIMARY KEY,
    country_name    VARCHAR(100)  NOT NULL,
    region          VARCHAR(60),
    income_group    VARCHAR(40),
    capital         VARCHAR(60)
);
