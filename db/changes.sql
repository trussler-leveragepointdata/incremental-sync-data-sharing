-- Deterministic incremental changes (applied between ingest runs).
-- Change timestamp is later than all seed timestamps in init.sql.

-- Update exactly 5 existing cases
UPDATE cases
SET status = 'escalated',
    updated_at = TIMESTAMPTZ '2026-04-01T12:00:00Z'
WHERE case_id IN (1, 2, 3, 4, 5);

-- Insert exactly 2 new customers
INSERT INTO customers (name, email, country, updated_at) VALUES
    ('New Customer Alpha', 'alpha.new@example.com', 'US', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    ('New Customer Beta', 'beta.new@example.com', 'UK', TIMESTAMPTZ '2026-04-01T12:00:00Z');

-- Insert exactly 10 new cases (mix of existing and new customers; IDs 33-34 are new customers)
INSERT INTO cases (customer_id, title, description, status, updated_at) VALUES
    (1, 'Billing dispute follow-up', 'Customer reported duplicate invoice during reconciliation', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (5, 'Audit trail request', 'Compliance audit requires payments history export', 'in_progress', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (10, 'Fraud alert review', 'AML screening flagged transaction for onboarding review', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (15, 'Reconciliation mismatch', 'Billing and payments totals do not match for March', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (20, 'Compliance certification', 'Annual compliance documentation update required', 'in_progress', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (33, 'New customer onboarding', 'Complete onboarding checklist for alpha account', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (34, 'New customer billing setup', 'Configure billing profile for beta account', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (33, 'AML initial screening', 'Run AML checks for new customer alpha', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (34, 'Payments method verification', 'Verify payments instrument for beta', 'open', TIMESTAMPTZ '2026-04-01T12:00:00Z'),
    (32, 'Audit sample case', 'Random audit sample for reconciliation controls', 'resolved', TIMESTAMPTZ '2026-04-01T12:00:00Z');
