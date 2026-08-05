import { useEffect, useState } from "react";
import { fetchDues } from "../api/client.js";
import {
  dueStatus,
  formatAmount,
  formatShortDate,
  isOverdue,
  sumAmounts,
} from "../utils/format.js";

function DuesList({ rows, nameKey, emptyText, tone }) {
  if (rows.length === 0) {
    return <p className="empty-state">{emptyText}</p>;
  }

  return (
    <ul className="dues-list">
      {rows.map((d) => {
        const status = dueStatus(d.due_date);
        return (
          <li key={d.id} className="due-item">
            <span className={`due-marker ${status.tone === "overdue" ? "overdue" : tone}`} />
            <div className="due-main">
              <span className="due-name">{d[nameKey] || "Unnamed"}</span>
              <span className={`due-status ${status.tone}`}>{status.text}</span>
              {d.note && <span className="due-note">{d.note}</span>}
            </div>
            <div className="due-side">
              <span className="due-amount">{formatAmount(d.amount)}</span>
              {Number(d.paid_amount) > 0 ? (
                <span className="due-since">
                  {formatAmount(d.paid_amount)} paid of {formatAmount(d.original_amount)}
                </span>
              ) : (
                d.credit_date && (
                  <span className="due-since">since {formatShortDate(d.credit_date)}</span>
                )
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function LoadingRows() {
  return (
    <ul className="dues-list">
      {[0, 1, 2].map((i) => (
        <li key={i} className="due-item skeleton-row">
          <span className="skeleton skeleton-line wide" />
          <span className="skeleton skeleton-line narrow" />
        </li>
      ))}
    </ul>
  );
}

export default function DuesPanel({ refreshKey }) {
  const [vendorDues, setVendorDues] = useState([]);
  const [customerDues, setCustomerDues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchDues("vendor"), fetchDues("customer")])
      .then(([v, c]) => {
        if (cancelled) return;
        setVendorDues(v.dues || []);
        setCustomerDues(c.dues || []);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [refreshKey, nonce]);

  const payableTotal = sumAmounts(vendorDues);
  const receivableTotal = sumAmounts(customerDues);
  const netPosition = receivableTotal - payableTotal;
  const overduePayable = vendorDues.filter((d) => isOverdue(d.due_date)).length;
  const overdueReceivable = customerDues.filter((d) => isOverdue(d.due_date)).length;

  return (
    <div className="panel">
      <div className="panel-toolbar">
        <span className="panel-eyebrow">Outstanding balances</span>
        <button
          type="button"
          className="icon-button"
          onClick={() => setNonce((n) => n + 1)}
          disabled={loading}
          title="Refresh"
          aria-label="Refresh dues"
        >
          ↻
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Payable</span>
          <span className="stat-value negative">{formatAmount(payableTotal)}</span>
          <span className="stat-meta">
            {vendorDues.length} open
            {overduePayable > 0 && <b className="stat-flag"> · {overduePayable} overdue</b>}
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Receivable</span>
          <span className="stat-value positive">{formatAmount(receivableTotal)}</span>
          <span className="stat-meta">
            {customerDues.length} open
            {overdueReceivable > 0 && <b className="stat-flag"> · {overdueReceivable} overdue</b>}
          </span>
        </div>
      </div>

      <div className="net-position">
        <span>Net position</span>
        <b className={netPosition >= 0 ? "positive" : "negative"}>{formatAmount(netPosition)}</b>
      </div>

      <section className="panel-section">
        <header className="section-header">
          <h3>Accounts Payable</h3>
          <span className="section-sub">Vendors</span>
        </header>
        {loading ? (
          <LoadingRows />
        ) : (
          <DuesList
            rows={vendorDues}
            nameKey="vendor_name"
            emptyText="No pending vendor bills."
            tone="payable"
          />
        )}
      </section>

      <section className="panel-section">
        <header className="section-header">
          <h3>Accounts Receivable</h3>
          <span className="section-sub">Customers</span>
        </header>
        {loading ? (
          <LoadingRows />
        ) : (
          <DuesList
            rows={customerDues}
            nameKey="customer_name"
            emptyText="No pending customer credit."
            tone="receivable"
          />
        )}
      </section>
    </div>
  );
}
