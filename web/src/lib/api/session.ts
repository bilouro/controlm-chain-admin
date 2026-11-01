const KEY = "ctmchain-token";

/**
 * Keep the session token from the URL opened by `ctmchain serve` (`?token=…`) for this tab,
 * then remove it from the address bar. Editing requests send it in `X-Ctmchain-Token`.
 */
export function captureToken(
  location: Location = window.location,
  history: History = window.history,
): void {
  const params = new URLSearchParams(location.search);
  const token = params.get("token");
  if (!token) return;
  setToken(token);
  params.delete("token");
  const query = params.toString();
  history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
}

export function setToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // storage unavailable (private mode): editing will ask for the URL again
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}
