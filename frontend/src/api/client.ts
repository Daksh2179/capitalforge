// Base fetch wrapper and typed ApiError

const BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined;

if (!BASE_URL) {
  throw new Error(
    "VITE_API_BASE_URL is not set. Add it to frontend/.env (see .env.example)."
  );
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  searchParams?: Record<string, string | number | undefined>;
}

/**
 * Every API call in the app goes through this function. Components and
 * hooks never call fetch() directly — this is the single place that
 * knows about the base URL, JSON encoding, and error shape.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, searchParams } = options;

  const url = new URL(path, BASE_URL);
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const response = await fetch(url.toString(), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let errorBody: unknown = null;
    try {
      errorBody = await response.json();
    } catch {
      // response had no JSON body; errorBody stays null
    }
    const message =
      (errorBody as { detail?: string })?.detail ??
      `Request to ${path} failed with status ${response.status}`;
    throw new ApiError(response.status, message, errorBody);
  }

  // 204 No Content or empty body responses
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}