import { useState } from "react";
import { ChatTab } from "@/components/chat/ChatTab";
import { cn } from "@/lib/utils";
import { OverviewTab } from "@/components/agent/OverviewTab";
import { HistoryTab } from "@/components/agent/HistoryTab";

const TABS = ["Overview", "Chat", "History"] as const;
type Tab = (typeof TABS)[number];

export function AgentPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Chat");

  return (
    <div>
      <div className="mb-4 flex gap-4 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              "border-b-2 px-1 pb-2 text-sm font-medium transition-colors",
              activeTab === tab
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Chat" && <ChatTab />}
      {activeTab === "Overview" && <OverviewTab />}
      {activeTab === "History" && <HistoryTab />}
    </div>
  );
}