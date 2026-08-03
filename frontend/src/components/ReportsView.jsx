import { useEffect, useState } from "react";
import { fetchReportsSummary } from "../api/client.js";
import { formatAmount, formatDate, humanize, toISODate } from "../utils/format.js";

function monthStart(offset = 0) {
  const d = new Date();
  return toISODate(new Date(d.getFullYear(), d.getMonth() + offset, 1));
}
function monthEnd(offset = 0) {
  const d = new Date();
  return toISODate(new Date(d.getFullYear(), d.getMonth() + offset + 1, 0));
}
function daysAgo(n) {
  const d = new Date();
  return toISODate(new Date(d.getFullYear(), d.getMonth(), d.getDate() - n));
}
function today() {
  return toISODate(new Date());
}

const PRESETS = [
  { id: "this_month", label: "This month", range: () => [monthStart(), today()] },
  { id: "last_30", label: "Last 30 days", range: () => [daysAgo(29), today()] },
  { id: "last_month", label: "Last month", range: () => [monthStart(-1), monthEnd(-1)] },
  { id: "last_7", label: "Last 7 days", range: () => [daysAgo(6), today()] },
];

function Breakdown({ title, rows, variant, total }) {
  if (!rows || rows.length === 0) {
    return (
      <section className="panel-section">
        <header className="section-header">
          <h3>{title}</h3>
        </header>
        <p className="empty-state">Nothing recorded in this period.</p>
      </section>
    );
  }

  const max = Math.max(...rows.map((r) => Number(r.total) || 0), 1);

  return (
    <section className="panel-section">
      <header className="section-header">
        <h3>{title}</h3>
        <span className="section-sub">{rows.length} categories</span>
      </header>
      <div className="breakdown">
        {rows.map((r) => {
          const value = Number(r.total) || 0;
          const share = total > 0 ? Math.round((value / total) * 100) : 0;
          return (
            <div className="breakdown-row" key={r.category}>
              <div className="breakdown-head">
                <span className="breakdown-label">{humanize(r.category)}</span>
                <span className="breakdown-value">{formatAmount(value)}</span>
              </div>
              <div className="bar-track">
                <div
                  className={`bar-fill ${variant}`}
                  style={{ width: `${Math.max((value / max) * 100, 2)}%` }}
                />
              </div>
              <span className="breakdown-share">{share}% of total</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function ReportsView() {
  const [startDate, setStartDate] = useState(monthStart());
  const [endDate, setEndDate] = useState(today());
  const [applied, setApplied] = useState({ start: monthStart(), end: today() });
  const [preset, setPreset] = useState("this_month");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchReportsSummary(applied.start, applied.end)
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [applied]);

  function applyPreset(p) {
    const [start, end] = p.range();
    setPreset(p.id);
    setStartDate(start);
    setEndDate(end);
    setApplied({ start, end });
  }

  function applyCustom(e) {
    e.preventDefault();
    if (!startDate || !endDate || startDate > endDate) return;
    setPreset(null);
    setApplied({ start: startDate, end: endDate });
  }

  const invalidRange = Boolean(startDate && endDate && startDate > endDate);
  const income = Number(data?.total_income) || 0;
  const expenses = Number(data?.total_expenses) || 0;
  const profit = Number(data?.profit) || 0;
  const margin = income > 0 ? Math.round((profit / income) * 100) : null;

  return (
    <div className="panel">
      <div className="panel-toolbar">
        <span className="panel-eyebrow">
          {formatDate(applied.start)} — {formatDate(applied.end)}
        </span>
      </div>

      <div className="preset-row">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`chip ${preset === p.id ? "active" : ""}`}
            onClick={() => applyPreset(p)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <form className="reports-form" onSubmit={applyCustom}>
        <label>
          From
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </label>
        <button type="submit" disabled={loading || invalidRange}>
          {loading ? "…" : "Apply"}
        </button>
      </form>

      {invalidRange && <p className="field-hint">Start date must be before end date.</p>}
      {error && <div className="error-banner">{error}</div>}

      {loading && !data && <div className="skeleton skeleton-block" />}

      {data && (
        <>
          <div className={`stat-grid ${loading ? "is-stale" : ""}`}>
            <div className="stat-card">
              <span className="stat-label">Income</span>
              <span className="stat-value positive">{formatAmount(income)}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">Expenses</span>
              <span className="stat-value negative">{formatAmount(expenses)}</span>
            </div>
          </div>

          <div className={`profit-card ${profit >= 0 ? "positive" : "negative"}`}>
            <div>
              <span className="stat-label">Net profit</span>
              <span className="profit-value">{formatAmount(profit)}</span>
            </div>
            {margin !== null && <span className="profit-margin">{margin}% margin</span>}
          </div>

          <Breakdown
            title="Expenses by category"
            rows={data.expense_by_category}
            variant="expense"
            total={expenses}
          />
          <Breakdown
            title="Income by category"
            rows={data.income_by_category}
            variant="income"
            total={income}
          />
        </>
      )}
    </div>
  );
}
