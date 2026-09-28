-- PostgreSQL DDL (app/db/models.py 와 동일 구조). Supabase SQL Editor 등에서 실행.
-- 모든 시각은 timestamptz(UTC 저장), 리포트 기준일은 KST 날짜.

CREATE TABLE IF NOT EXISTS reports (
    id               SERIAL PRIMARY KEY,
    report_type      VARCHAR(40)  NOT NULL,          -- us-close | kr-watchlist | kr-close-and-calendar
    report_date_kst  DATE         NOT NULL,
    generated_at_utc TIMESTAMPTZ  NOT NULL,
    status           VARCHAR(20)  NOT NULL,          -- ok | partial | failed
    revision         INTEGER      NOT NULL DEFAULT 1, -- 같은 날 재생성 시 증가
    payload          JSONB        NOT NULL,          -- 리포트 전체(출처·생성시각·면책문구 포함)
    CONSTRAINT uq_report_type_date UNIQUE (report_type, report_date_kst)
);
CREATE INDEX IF NOT EXISTS ix_reports_type_date ON reports (report_type, report_date_kst DESC);

CREATE TABLE IF NOT EXISTS job_runs (
    id              SERIAL PRIMARY KEY,
    report_type     VARCHAR(40) NOT NULL,
    started_at_utc  TIMESTAMPTZ NOT NULL,
    finished_at_utc TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL,             -- running | ok | partial | failed | skipped
    message         TEXT
);
CREATE INDEX IF NOT EXISTS ix_job_runs_type ON job_runs (report_type, started_at_utc DESC);

CREATE TABLE IF NOT EXISTS api_cache (
    cache_key      VARCHAR(64) PRIMARY KEY,           -- sha256(provider, url, params without secrets)
    provider       VARCHAR(20) NOT NULL,
    fetched_at_utc TIMESTAMPTZ NOT NULL,
    expires_at_utc TIMESTAMPTZ NOT NULL,
    body           JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_api_cache_provider ON api_cache (provider);

CREATE TABLE IF NOT EXISTS api_usage (
    provider       VARCHAR(20) NOT NULL,
    usage_date_utc DATE        NOT NULL,
    count          INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, usage_date_utc)
);

CREATE TABLE IF NOT EXISTS push_tokens (
    token          VARCHAR(512) PRIMARY KEY,
    created_at_utc TIMESTAMPTZ  NOT NULL
);
