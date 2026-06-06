-- Yaad — Supabase schema migration
-- Run once in Supabase SQL editor: https://supabase.com/dashboard/project/fpdcqezxwiibtjrfbgfh/sql
-- Safe to re-run (CREATE TABLE IF NOT EXISTS).

-- Shared provenance type
CREATE TABLE IF NOT EXISTS persons (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    relationship TEXT NOT NULL,
    aliases     JSONB DEFAULT '[]',
    notes       TEXT DEFAULT '',
    photo_ref   TEXT,
    is_reassurance_contact BOOLEAN DEFAULT FALSE,
    alert_priority INTEGER,
    provenance  JSONB
);

CREATE TABLE IF NOT EXISTS places (
    id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name    TEXT NOT NULL,
    kind    TEXT NOT NULL CHECK (kind IN ('home','familiar','other')),
    lat     DOUBLE PRECISION,
    lng     DOUBLE PRECISION,
    notes   TEXT DEFAULT '',
    provenance JSONB
);

CREATE TABLE IF NOT EXISTS events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    kind            TEXT NOT NULL,
    start_ts        TIMESTAMPTZ NOT NULL,
    end_ts          TIMESTAMPTZ,
    place_id        UUID REFERENCES places(id),
    participant_ids JSONB DEFAULT '[]',
    notes           TEXT DEFAULT '',
    provenance      JSONB
);

CREATE TABLE IF NOT EXISTS medications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    schedule_rrule  TEXT NOT NULL,
    notes           TEXT DEFAULT '',
    provenance      JSONB
);

CREATE TABLE IF NOT EXISTS med_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    medication_id   UUID REFERENCES medications(id),
    taken_ts        TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL,
    provenance      JSONB
);

CREATE TABLE IF NOT EXISTS stories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL,
    text        TEXT NOT NULL,
    people_ids  JSONB DEFAULT '[]',
    occurred_ts TIMESTAMPTZ,
    provenance  JSONB
);

CREATE TABLE IF NOT EXISTS episodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL,
    occurred_ts TIMESTAMPTZ NOT NULL,
    kind        TEXT NOT NULL,
    entity_refs JSONB DEFAULT '[]',
    summary     TEXT NOT NULL,
    provenance  JSONB
);

CREATE TABLE IF NOT EXISTS edges (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_ref TEXT NOT NULL,
    to_ref   TEXT NOT NULL,
    type     TEXT NOT NULL,
    weight   DOUBLE PRECISION DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS edges_from_ref_idx ON edges(from_ref);
CREATE INDEX IF NOT EXISTS edges_to_ref_idx ON edges(to_ref);

CREATE TABLE IF NOT EXISTS interactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lang            TEXT DEFAULT 'en',
    query           TEXT NOT NULL,
    response        TEXT NOT NULL,
    retrieved_refs  JSONB DEFAULT '[]',
    grounded        BOOLEAN NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS safe_zones (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    center_place_id     UUID REFERENCES places(id),
    radius_m            DOUBLE PRECISION NOT NULL,
    contact_ids_ordered JSONB DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS location_pings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lat         DOUBLE PRECISION NOT NULL,
    lng         DOUBLE PRECISION NOT NULL,
    inside_zone BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    kind                TEXT NOT NULL CHECK (kind IN ('wander','lost')),
    lat                 DOUBLE PRECISION NOT NULL,
    lng                 DOUBLE PRECISION NOT NULL,
    contacts_notified   JSONB DEFAULT '[]',
    status              TEXT DEFAULT 'active' CHECK (status IN ('active','resolved'))
);
