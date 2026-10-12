CREATE TABLE parties (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('vendor','customer')),
  name TEXT NOT NULL,
  gstin TEXT,
  phone TEXT,
  email TEXT
);
CREATE INDEX idx_parties_business ON parties(business_id, kind);

CREATE TABLE bills (
  id INTEGER PRIMARY KEY,
  business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  party_id INTEGER REFERENCES parties(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (status IN ('processing','needs_review','confirmed','failed')),
  file_path TEXT NOT NULL,
  original_name TEXT NOT NULL DEFAULT '',
  vendor_name TEXT,
  vendor_gstin TEXT,
  bill_no TEXT,
  bill_date TEXT,
  taxable_paise INTEGER,
  cgst_paise INTEGER,
  sgst_paise INTEGER,
  igst_paise INTEGER,
  total_paise INTEGER,
  category TEXT,
  extraction_json TEXT,
  confidence_json TEXT,
  validation_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  confirmed_at TEXT
);
CREATE INDEX idx_bills_business ON bills(business_id, status, created_at);

CREATE TABLE bill_items (
  id INTEGER PRIMARY KEY,
  bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  description TEXT NOT NULL,
  hsn TEXT,
  qty REAL NOT NULL,
  rate_paise INTEGER NOT NULL,
  gst_rate REAL,
  amount_paise INTEGER NOT NULL
);
CREATE INDEX idx_bill_items_bill ON bill_items(bill_id);
