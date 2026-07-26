import { useState } from "react";
import { fetchReportsSummary } from "../api/client.js";

function firstOfMonth() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}
function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function ReportsView() {
  const [startDate, setStartDate] = useState(firstOfMonth());
  const [endDate, setEndDate] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load(e) {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetchReportsSummary(startDate, endDate);
      setData(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const maxTotal = data
    ? Math.max(
        data.total_income,
        data.total_expenses,
        ...(data.expense_by_category || []).map((c) => c.total),
        1
      )
    : 1;

  return (
    <div className="panel">
      <h3>Reports</h3>
      <form className="reports-form" onSubmit={load}>
        <label>
          From
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Loading…" : "Run"}
        </button>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {data && (
        <div className="report-results">
          <div className="report-totals">
            <div>
              Income: <b>Rs {data.total_income}</b>
            </div>
            <div>
              Expenses: <b>Rs {data.total_expenses}</b>
            </div>
            <div>
              Profit: <b className={data.profit >= 0 ? "positive" : "negative"}>Rs {data.profit}</b>
            </div>
          </div>

          <h4>Expenses by category</h4>
          <table>
            <tbody>
              {(data.expense_by_category || []).map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td className="bar-cell">
                    <div className="bar" style={{ width: `${(c.total / maxTotal) * 100}%` }} />
                  </td>
                  <td>Rs {c.total}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4>Income by category</h4>
          <table>
            <tbody>
              {(data.income_by_category || []).map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td className="bar-cell">
                    <div
                      className="bar income"
                      style={{ width: `${(c.total / maxTotal) * 100}%` }}
                    />
                  </td>
                  <td>Rs {c.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
