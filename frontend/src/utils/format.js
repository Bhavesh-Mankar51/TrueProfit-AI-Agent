export function formatAmount(value) {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "Rs 0";
  const hasPaise = Math.abs(n % 1) > 0.005;
  const digits = hasPaise ? 2 : 0;
  const formatted = new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Math.abs(n));
  return `${n < 0 ? "-" : ""}Rs ${formatted}`;
}

export function parseDate(value) {
  if (!value) return null;
  const [y, m, d] = String(value).slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

export function formatDate(value) {
  const date = parseDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatShortDate(value) {
  const date = parseDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(date);
}

export function daysUntil(value) {
  const date = parseDate(value);
  if (!date) return null;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((date - today) / 86400000);
}

export function dueStatus(dueDate) {
  const days = daysUntil(dueDate);
  if (days === null) return { text: "No due date", tone: "neutral" };
  if (days < 0) {
    const n = Math.abs(days);
    return { text: `Overdue by ${n} ${n === 1 ? "day" : "days"}`, tone: "overdue" };
  }
  if (days === 0) return { text: "Due today", tone: "soon" };
  if (days <= 7) return { text: `Due in ${days} ${days === 1 ? "day" : "days"}`, tone: "soon" };
  return { text: `Due ${formatDate(dueDate)}`, tone: "neutral" };
}

export function humanize(value) {
  if (!value) return "Uncategorised";
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function sumAmounts(rows) {
  return (rows || []).reduce((acc, row) => acc + Number(row.amount || 0), 0);
}

export function isOverdue(dueDate) {
  const days = daysUntil(dueDate);
  return days !== null && days < 0;
}

export function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
