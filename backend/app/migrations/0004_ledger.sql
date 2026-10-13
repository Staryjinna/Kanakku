ALTER TABLE businesses ADD COLUMN onboarding_done INTEGER NOT NULL DEFAULT 0;
-- businesses that existed before onboarding was introduced skip it
UPDATE businesses SET onboarding_done = 1;

-- Used by the dashboard's overdue-receivables tile now and by payment follow-ups (Phase 4).
CREATE TABLE sales_invoices (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  party_id INTEGER NOT NULL REFERENCES parties(id),
  invoice_no TEXT NOT NULL,
  invoice_date TEXT NOT NULL,
  due_date TEXT NOT NULL,
  total_paise INTEGER NOT NULL CHECK (total_paise >= 0),
  paid_paise INTEGER NOT NULL DEFAULT 0 CHECK (paid_paise >= 0),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','paid')),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_sales_invoices_business ON sales_invoices(business_id, status, due_date);

CREATE TABLE followups (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  invoice_id INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
  channel TEXT NOT NULL CHECK (channel IN ('whatsapp','email')),
  draft_text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','sent','rejected')),
  tone TEXT NOT NULL DEFAULT 'gentle',
  used_template INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE INDEX idx_followups_invoice ON followups(business_id, invoice_id);
