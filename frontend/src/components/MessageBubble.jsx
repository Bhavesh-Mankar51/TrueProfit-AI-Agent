function ActionCard({ action }) {
  if (!action || typeof action !== "object") return null;
  const entries = Array.isArray(action)
    ? null
    : Object.entries(action).filter(([k]) => !k.startsWith("_"));

  if (Array.isArray(action)) {
    if (action.length === 0) return null;
    return (
      <div className="action-card">
        {action.slice(0, 5).map((item, i) => (
          <div key={i} className="action-card-row">
            {Object.entries(item)
              .slice(0, 4)
              .map(([k, v]) => (
                <span key={k} className="action-field">
                  <b>{k}:</b> {String(v)}
                </span>
              ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="action-card">
      {entries.slice(0, 6).map(([k, v]) => (
        <span key={k} className="action-field">
          <b>{k}:</b> {String(v)}
        </span>
      ))}
    </div>
  );
}

export default function MessageBubble({ role, text, action }) {
  return (
    <div className={`bubble-row ${role}`}>
      <div className={`bubble ${role}`}>
        <div>{text}</div>
        {role === "agent" && <ActionCard action={action} />}
      </div>
    </div>
  );
}
