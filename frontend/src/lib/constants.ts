// V1 user-id constant and useCurrentUser seam

const V1_USER_ID = import.meta.env.VITE_USER_ID as string | undefined;

if (!V1_USER_ID) {
  // Fails loudly at startup rather than silently sending "undefined"
  // as a user_id to every API call.
  throw new Error(
    "VITE_USER_ID is not set. Add it to frontend/.env (see .env.example)."
  );
}

/**
 * The one seam every component/hook goes through for the current user's
 * identity. Returns a fixed constant in V1 (no auth). When real auth is
 * added later, only this function needs to change — no other file should
 * ever read a user id from anywhere else.
 */
export function useCurrentUser(): { userId: string } {
  return { userId: V1_USER_ID as string };
}