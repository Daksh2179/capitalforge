// Route table

import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { WelcomePage } from "@/pages/WelcomePage";
import { TradingModePage } from "@/pages/TradingModePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { AgentPage } from "@/pages/AgentPage";
import { ActivityPage } from "@/pages/ActivityPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { isOnboardingComplete } from "@/lib/onboarding";

function RootRedirect() {
  return isOnboardingComplete() ? (
    <Navigate to="/dashboard" replace />
  ) : (
    <WelcomePage />
  );
}

export const router = createBrowserRouter([
  { path: "/", element: <RootRedirect /> },
  { path: "/trading-mode", element: <TradingModePage /> },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { path: "dashboard", element: <DashboardPage /> },
      { path: "agent", element: <AgentPage /> },
      { path: "activity", element: <ActivityPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);