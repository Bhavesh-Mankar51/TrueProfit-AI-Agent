import { useEffect, useState } from "react";
import { fetchReminders } from "../api/client.js";

export default function ReminderBanner() {
  const [reminders, setReminders] = useState([]);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetchReminders()
      .then((res) => setReminders(res.reminders || []))
      .catch(() => {});
  }, []);

  if (dismissed || reminders.length === 0) return null;

  return (
    <div className="reminder-banner">
      <span>
        {reminders.length} vendor payment{reminders.length > 1 ? "s" : ""} due soon:{" "}
        {reminders
          .slice(0, 3)
          .map((r) => `${r.vendor_name} (Rs ${r.amount}${r.overdue ? ", overdue" : ""})`)
          .join(", ")}
        {reminders.length > 3 ? "…" : ""}
      </span>
      <button onClick={() => setDismissed(true)}>×</button>
    </div>
  );
}
