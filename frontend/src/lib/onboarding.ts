// Onboarding-seen flag, persisted in localStorage since there's no
// backend user record to attach this to in V1 (no auth).

const ONBOARDING_KEY = "capitalforge:onboarding-complete";

export function isOnboardingComplete(): boolean {
  return localStorage.getItem(ONBOARDING_KEY) === "true";
}

export function markOnboardingComplete(): void {
  localStorage.setItem(ONBOARDING_KEY, "true");
}