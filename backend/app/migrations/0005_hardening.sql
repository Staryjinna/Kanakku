CREATE TABLE rate_limit_hits (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  hit_at TEXT NOT NULL
);
CREATE INDEX idx_rate_limit_user ON rate_limit_hits(user_id, hit_at);
