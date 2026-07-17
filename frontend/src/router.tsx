// Route table

import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { MarketsPage } from "@/pages/MarketsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { AgentPage } from "@/pages/AgentPage";
import { ActivityPage } from "@/pages/ActivityPage";
import { SettingsPage } from "@/pages/SettingsPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/markets" replace /> },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { path: "markets", element: <MarketsPage /> },
      { path: "agent", element: <AgentPage /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "activity", element: <ActivityPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);