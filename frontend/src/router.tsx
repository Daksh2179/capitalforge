// Route table

import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { AgentPage } from "@/pages/AgentPage";
import { ActivityPage } from "@/pages/ActivityPage";
import { SettingsPage } from "@/pages/SettingsPage";

// Onboarding (Welcome -> Trading Mode) is its own implementation group,
// not built yet. For now the root path renders the layout directly with
// Dashboard as the index route, so the foundation is independently
// testable before onboarding exists.
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "agent", element: <AgentPage /> },
      { path: "activity", element: <ActivityPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);