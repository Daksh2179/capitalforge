import { useState } from "react";
import { ChatTab } from "@/components/chat/ChatTab";
import { cn } from "@/lib/utils";

const TABS = ["Overview", "Chat", "Agent Rules", "History"] as const;
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
      {activeTab === "Overview" && <p className="text-muted-foreground">Overview — not yet implemented.</p>}
      {activeTab === "Agent Rules" && <p className="text-muted-foreground">Agent Rules — not yet implemented.</p>}
      {activeTab === "History" && <p className="text-muted-foreground">History — not yet implemented.</p>}
    </div>
  );
}