CREATE TABLE shops (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    owner_name TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE vendors (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id),
    name TEXT NOT NULL,
    phone TEXT,
    notes TEXT
);

CREATE TABLE expenses (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id),
    amount NUMERIC(10,2) NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    vendor_id INTEGER REFERENCES vendors(id),
    payment_method TEXT DEFAULT 'cash',
    expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE income (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id),
    amount NUMERIC(10,2) NOT NULL,
    category TEXT NOT NULL,
    item_description TEXT,
    customer_name TEXT,
    payment_method TEXT DEFAULT 'cash',
    income_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE vendor_ledger (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER REFERENCES vendors(id),
    amount NUMERIC(10,2) NOT NULL,
    paid_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    type TEXT NOT NULL,
    due_date DATE,
    status TEXT DEFAULT 'pending',
    note TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE customer_credit (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id),
    customer_name TEXT NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    paid_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    note TEXT,
    credit_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_expenses_shop_date ON expenses(shop_id, expense_date);
CREATE INDEX idx_income_shop_date ON income(shop_id, income_date);
CREATE INDEX idx_vendor_ledger_status ON vendor_ledger(status, due_date);
CREATE INDEX idx_customer_credit_status ON customer_credit(status, customer_name);

INSERT INTO shops (name, owner_name) VALUES ('Test General Store', 'Ramesh Shah');

INSERT INTO categories (name) VALUES
    ('inventory'), ('rent'), ('electricity'), ('salary'), ('transport'), ('misc');
