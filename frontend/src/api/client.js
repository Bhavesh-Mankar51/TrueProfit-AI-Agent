const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export function sendChatMessage(sessionId, message) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export function fetchDues(type) {
  return request(`/dues?type=${encodeURIComponent(type)}`);
}

export function fetchReportsSummary(startDate, endDate, groupBy = "category") {
  return request(
    `/reports/summary?start_date=${startDate}&end_date=${endDate}&group_by=${groupBy}`
  );
}

export function fetchReminders() {
  return request("/reminders");
}
