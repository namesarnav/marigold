const BASE = (import.meta.env.DEV
  ? (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
  : ""
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

async function handleResponse(res) {
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
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

// Documents
export async function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file);
  return request("POST", "/api/documents/upload", form, true);
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

export async function regenerateFlashcards(docId) {
  return request("POST", `/api/flashcards/${docId}/regenerate`);
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
