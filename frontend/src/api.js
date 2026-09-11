// Where the API lives.
//
// VITE_API_BASE_URL is baked in at build time — Vite substitutes
// import.meta.env during compilation, so this is a property of the bundle, not
// of the running container. Changing it on the frontend service requires a
// rebuild, not a restart.
//
// Empty means "same origin", which is correct when one service serves both the
// API and this bundle. In the split deployment the frontend and the API are
// different Railway services on different domains, so this must be set to the
// API service's public URL or every request goes to the static file server and
// comes back as index.html.
const BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/+$/, "");

function getToken() {
  return localStorage.getItem("access_token");
}

function setToken(token) {
  localStorage.setItem("access_token", token);
}

function clearToken() {
  localStorage.removeItem("access_token");
}

async function request(method, path, body, isFormData = false) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!isFormData && body) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: isFormData ? body : body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    // Try to refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      const headers2 = {};
      const newToken = getToken();
      if (newToken) headers2["Authorization"] = `Bearer ${newToken}`;
      if (!isFormData && body) headers2["Content-Type"] = "application/json";
      const res2 = await fetch(`${BASE}${path}`, {
        method,
        headers: headers2,
        credentials: "include",
        body: isFormData ? body : body ? JSON.stringify(body) : undefined,
      });
      return handleResponse(res2);
    } else {
      clearToken();
      throw new Error("Session expired. Please log in again.");
    }
  }

  return handleResponse(res);
}

/**
 * An error carrying the parts of a FastAPI error body the UI acts on.
 *
 * `code` is what makes the verification gate work: the backend answers every
 * gated endpoint with a 403 whose detail is an object, and the UI has to tell
 * "confirm your email" apart from an ordinary refusal.
 */
export class ApiError extends Error {
  constructor(message, { status, code } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/**
 * Pull a human-readable message out of FastAPI's `detail`.
 *
 * `detail` takes three shapes and the UI sees all three: a plain string from
 * `HTTPException(detail="...")`, an object from the verification gate
 * (`{code, message, email}`), and an array of field errors from a 422. Only
 * the string case was handled, so a gated request rendered the object through
 * `new Error(obj)` and put the literal text "[object Object]" on screen in
 * place of "Confirm your email address to use Marigold."
 */
function describe(detail, status) {
  if (typeof detail === "string" && detail) return detail;

  if (Array.isArray(detail)) {
    // 422 from Pydantic. `msg` alone reads better than the full locator, and
    // these are almost always a single field.
    const first = detail[0];
    if (first?.msg) return first.msg;
  }

  if (detail && typeof detail === "object" && detail.message) {
    return detail.message;
  }

  return `Request failed (${status})`;
}

async function handleResponse(res) {
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const detail = data.detail;
    throw new ApiError(describe(detail, res.status), {
      status: res.status,
      code: detail && typeof detail === "object" ? detail.code : undefined,
    });
  }

  return data;
}

async function tryRefresh() {
  const res = await fetch(`${BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) return false;
  const data = await res.json().catch(() => null);
  if (data?.access_token) {
    setToken(data.access_token);
    return true;
  }
  return false;
}

// Auth
export async function register(email, password, name) {
  const data = await request("POST", "/api/auth/register", { email, password, name });
  setToken(data.access_token);
  return data;
}

export async function login(email, password) {
  const data = await request("POST", "/api/auth/login", { email, password });
  setToken(data.access_token);
  return data;
}

export async function logout() {
  await request("POST", "/api/auth/logout").catch(() => {});
  clearToken();
}

export async function getMe() {
  return request("GET", "/api/auth/me");
}

// Email verification

/**
 * Spend a verification token from an emailed link.
 *
 * The backend returns a full session, so clicking the link in a browser that
 * was never signed in logs the account in rather than bouncing to a form —
 * which is why this stores the access token like login and register do.
 */
export async function verifyEmail(token) {
  const data = await request("POST", "/api/auth/verify-email", { token });
  setToken(data.access_token);
  return data;
}

/**
 * Ask for another verification email.
 *
 * Answers the same way for an unknown address, an already-verified account and
 * a successful send — the endpoint refuses to leak which one it was — so the
 * UI can only ever say "if that address needs confirming, it's on its way".
 * Rate limited server-side; that surfaces as a 429.
 */
export async function resendVerification(email) {
  return request("POST", "/api/auth/resend-verification", { email });
}

// Password reset

/**
 * Start a reset. Always resolves the same way.
 *
 * The endpoint answers identically for an address with an account and one
 * without, so this cannot be used to find out who has registered. The UI must
 * not claim an email was sent — only that one was sent *if* the account exists.
 * Rate limited per address; that surfaces as a 429.
 */
export async function forgotPassword(email) {
  return request("POST", "/api/auth/forgot-password", { email });
}

/**
 * Set a new password from an emailed reset token.
 *
 * Returns a message, not a session: the backend revokes every refresh token as
 * part of the reset, so anything an attacker already holds dies with it. That
 * is also why this cannot log the user straight in — they sign in again with
 * the new password.
 */
export async function resetPassword(token, password) {
  return request("POST", "/api/auth/reset-password", { token, password });
}

// OAuth

/**
 * Which providers the server has credentials for.
 *
 * Buttons are rendered from this rather than hardcoded, so a provider that is
 * not configured is never offered — clicking it would 503.
 */
export async function getOAuthProviders() {
  const data = await request("GET", "/api/auth/oauth/providers");
  return data.providers ?? [];
}

/**
 * Where to send the browser to start a provider flow.
 *
 * A full page navigation, not fetch: the provider redirects through its own
 * consent screen and back, and the state/PKCE values live in a cookie the
 * backend sets. XHR cannot follow that.
 */
export function oauthLoginUrl(provider) {
  return `${BASE}/api/auth/oauth/${provider}/login`;
}

/**
 * Finish a provider sign-in after the callback lands back on the SPA.
 *
 * The backend has already set the httpOnly refresh cookie on the redirect; all
 * that is left is to trade it for an access token. Returns whether that worked.
 */
export async function completeOAuthLogin() {
  return tryRefresh();
}

// Documents
export async function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file);
  return request("POST", "/api/documents/upload", form, true);
}

/**
 * Wait for a freshly uploaded document to finish card generation.
 *
 * Upload returns as soon as the row exists, with status "processing" — the
 * Gemini call runs server-side afterwards, so the request cannot be left
 * hanging on it without tripping the ingress response timeout. The client
 * polls instead.
 *
 * Resolves with the document once its status leaves "processing". Rejects if
 * generation failed, or if it is still going after `timeoutMs` — a caller that
 * polls forever is how a stuck job turns into a spinner nobody can dismiss.
 */
export async function waitForDocument(
  docId,
  { intervalMs = 1500, timeoutMs = 180000, onTick } = {}
) {
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const doc = await getDocument(docId);
    if (doc.status === "ready") return doc;
    if (doc.status === "failed") {
      throw new Error(
        "We couldn't generate flashcards from this PDF. Please try again."
      );
    }
    if (Date.now() >= deadline) {
      throw new Error(
        "Still working on this PDF. It will appear on your dashboard when it's done."
      );
    }
    if (onTick) onTick(doc);
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export async function listDocuments() {
  return request("GET", "/api/documents");
}

export async function getDocument(docId) {
  return request("GET", `/api/documents/${docId}`);
}

export async function deleteDocument(docId) {
  return request("DELETE", `/api/documents/${docId}`);
}

// Documents
export async function renameDocument(docId, filename) {
  return request("PATCH", `/api/documents/${docId}`, { filename });
}

// Stats
export async function getStats() {
  return request("GET", "/api/stats/me");
}

// Flashcards
export async function getFlashcards(docId) {
  return request("GET", `/api/flashcards/${docId}`);
}

export async function createFlashcard(docId, question, answer, topic) {
  return request("POST", `/api/flashcards/${docId}/new`, { question, answer, topic });
}

export async function patchFlashcard(cardId, fields) {
  return request("PATCH", `/api/flashcards/${cardId}`, fields);
}

export async function deleteFlashcard(cardId) {
  return request("DELETE", `/api/flashcards/${cardId}`);
}

export async function reviewFlashcard(cardId, known, responseTimeMs) {
  return request("POST", `/api/flashcards/${cardId}/review`, {
    known,
    response_time_ms: responseTimeMs,
  });
}

export async function regenerateFlashcards(docId) {
  return request("POST", `/api/flashcards/${docId}/regenerate`);
}

// Review

/**
 * Concepts ranked by forgetting risk, most at-risk first.
 *
 * `asOf` may be a future Date — the backend projects the forgetting curve
 * forward, which is what drives the exam-readiness view. It is sent through
 * `URLSearchParams` rather than string concatenation because an ISO offset
 * contains "+", which decodes to a space in a query string and is rejected.
 */
export async function getReviewQueue({ limit = 20, asOf = null } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (asOf) params.set("as_of", asOf.toISOString());
  return request("GET", `/api/review/next?${params}`);
}

// Quiz
export async function startQuiz(docId, numQuestions) {
  return request("POST", "/api/quiz/start", { doc_id: docId, num_questions: numQuestions });
}

export async function submitAnswer(quizId, answer, timeTaken) {
  return request("POST", `/api/quiz/${quizId}/answer`, { answer, time_taken_seconds: timeTaken });
}

export async function skipQuestion(quizId, timeTaken) {
  return request("POST", `/api/quiz/${quizId}/skip`, { time_taken_seconds: timeTaken });
}

export async function getQuizResults(quizId) {
  return request("GET", `/api/quiz/${quizId}/results`);
}

export async function getQuizHistory() {
  return request("GET", "/api/quiz/history");
}

export async function getQuizReview(quizId) {
  return request("GET", `/api/quiz/${quizId}/review`);
}

export { getToken, clearToken };
