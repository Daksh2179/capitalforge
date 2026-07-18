// Route table

import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { MarketsPage } from "./pages/MarketsPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { AgentPage } from "./pages/AgentPage";
import { ActivityPage } from "./pages/ActivityPage";
import { StockDetailPage } from "@/pages/StockDetailPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/markets" replace /> },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { path: "markets", element: <MarketsPage /> },
      { path: "portfolio", element: <PortfolioPage /> },
      { path: "agent", element: <AgentPage /> },
      { path: "activity", element: <ActivityPage /> },
      { path: "markets/:symbol", element: <StockDetailPage /> },
    ],
  },
]);