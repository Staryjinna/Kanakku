-- GST corpus is shared across businesses (not business-owned).
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  source_url TEXT,
  file_path TEXT NOT NULL,
  file_hash TEXT NOT NULL UNIQUE,
  ingested_at TEXT NOT NULL
);

CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page INTEGER NOT NULL,
  ordinal INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX idx_chunks_document ON chunks(document_id, page, ordinal);

-- rowid = chunks.id. chunks_vec (sqlite-vec) is created at first ingest, once the
-- embedding dimension is known.
CREATE VIRTUAL TABLE chunks_fts USING fts5(text);

CREATE TABLE gst_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE qa_logs (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  cited_chunk_ids TEXT NOT NULL DEFAULT '[]',
  refused INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_qa_logs_business ON qa_logs(business_id, id);
