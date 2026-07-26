import { useState } from "react";
import ChatWindow from "./components/ChatWindow.jsx";
import DuesPanel from "./components/DuesPanel.jsx";
import ReminderBanner from "./components/ReminderBanner.jsx";
import ReportsView from "./components/ReportsView.jsx";

export default function App() {
  const [tab, setTab] = useState("dues");
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Shopkeeper Agent</h1>
      </header>
      <ReminderBanner />
      <div className="app-body">
        <ChatWindow onActionTaken={() => setRefreshKey((k) => k + 1)} />
        <aside className="sidebar">
          <div className="tabs">
            <button className={tab === "dues" ? "active" : ""} onClick={() => setTab("dues")}>
              Dues
            </button>
            <button
              className={tab === "reports" ? "active" : ""}
              onClick={() => setTab("reports")}
            >
              Reports
            </button>
          </div>
          {tab === "dues" ? <DuesPanel refreshKey={refreshKey} /> : <ReportsView />}
        </aside>
      </div>
    </div>
  );
}
