// TanStack QueryClient instance and defaults

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30s — matches the polling cadence discussed for portfolio/orders/decision-log data
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});