import { useEffect, useRef, useState } from "react";
import { fetchChatHistory, sendChatMessage } from "../api/client.js";
import MessageBubble from "./MessageBubble.jsx";

const GREETING = {
  role: "agent",
  text: "Hi! Tell me about a sale, an expense, or ask for a report — e.g. \"sold 2 packets of biscuits for 40\".",
};

function getSessionId() {
  let id = localStorage.getItem("shopkeeper_session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("shopkeeper_session_id", id);
  }
  return id;
}

export default function ChatWindow({ onActionTaken }) {
  const [sessionId] = useState(getSessionId);
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);


  useEffect(() => {
    let cancelled = false;
    fetchChatHistory(sessionId)
      .then((res) => {
        if (cancelled || !res.messages?.length) return;
        setMessages([GREETING, ...res.messages]);
      })
      .catch(() => {
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await sendChatMessage(sessionId, text);
      setMessages((m) => [...m, { role: "agent", text: res.reply, action: res.actions_taken }]);
      if (res.actions_taken) onActionTaken?.();
    } catch (err) {
      setError(err.message);
      setMessages((m) => [
        ...m,
        { role: "agent", text: "Something went wrong reaching the server. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-window">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} text={m.text} action={m.action} />
        ))}
        {loading && (
          <div className="bubble-row agent">
            <div className="bubble agent typing">…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {error && <div className="error-banner">{error}</div>}
      <form className="chat-input-row" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message…"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
