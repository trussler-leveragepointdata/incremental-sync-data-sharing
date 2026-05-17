-- Schema and deterministic seed data for incremental sync prototype.

CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cases (
    case_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_customers_updated_at ON customers(updated_at);
CREATE INDEX idx_cases_updated_at ON cases(updated_at);
CREATE INDEX idx_cases_customer_id ON cases(customer_id);

DO $$
DECLARE
    anchor TIMESTAMPTZ := TIMESTAMPTZ '2026-03-01T00:00:00Z';
    i INT;
    case_num INT;
    cust_ts TIMESTAMPTZ;
    case_ts TIMESTAMPTZ;
    kw TEXT[] := ARRAY[
        'billing', 'audit', 'compliance', 'payments', 'reconciliation',
        'onboarding', 'fraud', 'AML'
    ];
    kw_idx INT;
    cust_id INT;
    statuses TEXT[] := ARRAY['open', 'in_progress', 'resolved', 'closed'];
BEGIN
    FOR i IN 1..32 LOOP
        cust_ts := anchor + ((i - 1) % 30) * INTERVAL '1 day'
            + ((i - 1) / 30) * INTERVAL '1 hour';
        INSERT INTO customers (name, email, country, updated_at)
        VALUES (
            'Customer ' || i,
            'customer' || i || '@example.com',
            CASE (i % 5)
                WHEN 0 THEN 'US'
                WHEN 1 THEN 'UK'
                WHEN 2 THEN 'DE'
                WHEN 3 THEN 'FR'
                ELSE 'CA'
            END,
            cust_ts
        );
    END LOOP;

    FOR case_num IN 1..210 LOOP
        cust_id := 1 + ((case_num - 1) % 32);
        kw_idx := 1 + ((case_num - 1) % array_length(kw, 1));
        case_ts := anchor + ((case_num - 1) % 30) * INTERVAL '1 day'
            + ((case_num - 1) % 24) * INTERVAL '1 hour';
        INSERT INTO cases (customer_id, title, description, status, updated_at)
        VALUES (
            cust_id,
            initcap(kw[kw_idx]) || ' review case #' || case_num,
            'Case related to ' || kw[kw_idx] || ' for customer ' || cust_id
                || '. Requires ' || kw[1 + (case_num % 7)] || ' follow-up.',
            statuses[1 + (case_num % array_length(statuses, 1))],
            case_ts
        );
    END LOOP;
END $$;
