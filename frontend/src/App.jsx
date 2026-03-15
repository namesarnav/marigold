import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext.jsx";
import { ToastProvider } from "./toast.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import DeckView from "./pages/DeckView.jsx";
import QuizModePage from "./pages/QuizModePage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";
import Pricing from "./pages/Pricing.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/dashboard"
              element={<ProtectedRoute><Dashboard /></ProtectedRoute>}
            />
            <Route
              path="/deck/:id"
              element={<ProtectedRoute><DeckView /></ProtectedRoute>}
            />
            <Route
              path="/quiz/:id"
              element={<ProtectedRoute><QuizModePage /></ProtectedRoute>}
            />
            <Route
              path="/results/:id"
              element={<ProtectedRoute><ResultsPage /></ProtectedRoute>}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
