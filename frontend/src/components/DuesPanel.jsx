import { useEffect, useState } from "react";
import { fetchDues } from "../api/client.js";

export default function DuesPanel({ refreshKey }) {
  const [vendorDues, setVendorDues] = useState([]);
  const [customerDues, setCustomerDues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
  }, [refreshKey]);

  if (loading) return <div className="panel">Loading dues…</div>;
  if (error) return <div className="panel error-banner">{error}</div>;

  return (
    <div className="panel">
      <h3>Accounts Payable (Vendors)</h3>
      {vendorDues.length === 0 ? (
        <p className="muted">Nothing pending.</p>
      ) : (
        <ul>
          {vendorDues.map((d) => (
            <li key={d.id}>
              <b>{d.vendor_name}</b> — Rs {d.amount}
              {d.due_date ? ` (due ${d.due_date})` : ""}
            </li>
          ))}
        </ul>
      )}

      <h3>Owed to you (customers)</h3>
      {customerDues.length === 0 ? (
        <p className="muted">Nothing pending.</p>
      ) : (
        <ul>
          {customerDues.map((d) => (
            <li key={d.id}>
              <b>{d.customer_name}</b> — Rs {d.amount}
              {d.credit_date ? ` (since ${d.credit_date})` : ""}
              {d.due_date ? ` (due ${d.due_date})` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
