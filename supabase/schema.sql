-- Windy City Reaper: Supabase / Postgres upgrade path.
-- Same table and column names as engine/db.py (SQLite), so migration is mechanical:
--   sqlite3 data/engine.db .dump  ->  adapt types  ->  psql, or export CSVs per table.
-- Run in the Supabase SQL editor. pgvector enables semantic search / cross-dataset
-- correlation over document chunks (embeddings are populated by your own job).

create extension if not exists vector;

create table if not exists sources (
  key text primary key, jurisdiction text not null, name text not null, url text,
  method text not null, enabled boolean not null default true,
  last_run timestamptz, last_status text, last_detail text, items_last_run int default 0
);

create table if not exists documents (
  id bigserial primary key, source_key text not null, jurisdiction text not null,
  url text not null unique, title text, content_type text, method text, published_at text,
  first_seen timestamptz not null, last_fetched timestamptz not null, current_hash text,
  version_count int not null default 0, lat double precision, lon double precision
);

create table if not exists versions (
  id bigserial primary key, document_id bigint not null references documents(id),
  hash text not null, fetched_at timestamptz not null, size int, text text,
  tsv tsvector generated always as (to_tsvector('english', coalesce(text, ''))) stored
);
create index if not exists ix_versions_doc on versions(document_id);
create index if not exists ix_versions_tsv on versions using gin(tsv);

create table if not exists chunks (               -- pgvector: semantic retrieval
  id bigserial primary key, version_id bigint not null references versions(id),
  ord int not null, text text not null, embedding vector(1536)
);
create index if not exists ix_chunks_embedding on chunks using hnsw (embedding vector_cosine_ops);

create table if not exists events (
  id text primary key, jurisdiction text not null, kind text not null, severity text not null,
  title text not null, quote text, source_url text, method text, fetched_at text,
  created_at timestamptz not null, watchlist_hits jsonb default '[]', hash text,
  lat double precision, lon double precision, data jsonb default '{}',
  alerted boolean not null default false, ledgered boolean not null default false
);
create index if not exists ix_events_created on events(created_at desc);

create table if not exists metrics (
  jurisdiction text not null, series text not null, grp text not null, bucket text not null,
  value double precision not null, n int, updated_at timestamptz not null,
  primary key (jurisdiction, series, grp, bucket)
);

create table if not exists requests (
  id bigserial primary key, dedupe_key text unique, jurisdiction text not null, state text not null,
  kind text not null, agency text, subject text not null, body text not null, source_url text,
  status text not null default 'draft', created_at timestamptz not null, sent_at timestamptz,
  due_at date, notes text
);

create table if not exists ledger (
  seq bigserial primary key, event_id text not null, entry_hash text not null,
  prev_hash text not null, committed_at timestamptz not null
);

-- Public read access for the journalist API (Supabase row-level security).
alter table events enable row level security;
create policy "public read events" on events for select using (true);
