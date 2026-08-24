import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Dashboard from "./pages/specialist/Dashboard";
import ExceptionsIndex from "./pages/specialist/ExceptionsIndex";
import ExceptionReview from "./pages/specialist/ExceptionReview";
import QueryExport from "./pages/specialist/QueryExport";
import Upload from "./pages/submitter/Upload";
import Status from "./pages/submitter/Status";
import AnswerQuery from "./pages/submitter/AnswerQuery";

function Root() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "specialist" ? "/dashboard" : "/submitter/status"} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Root />} />
          <Route path="/login" element={<Login />} />

          <Route
            path="/dashboard"
            element={
              <ProtectedRoute role="specialist">
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/exceptions"
            element={
              <ProtectedRoute role="specialist">
                <ExceptionsIndex />
              </ProtectedRoute>
            }
          />
          <Route
            path="/exceptions/:submissionId"
            element={
              <ProtectedRoute role="specialist">
                <ExceptionReview />
              </ProtectedRoute>
            }
          />
          <Route
            path="/query-export"
            element={
              <ProtectedRoute role="specialist">
                <QueryExport />
              </ProtectedRoute>
            }
          />

          <Route
            path="/submitter/upload"
            element={
              <ProtectedRoute role="submitter">
                <Upload />
              </ProtectedRoute>
            }
          />
          <Route
            path="/submitter/status"
            element={
              <ProtectedRoute role="submitter">
                <Status />
              </ProtectedRoute>
            }
          />
          <Route
            path="/submitter/answer/:exceptionId"
            element={
              <ProtectedRoute role="submitter">
                <AnswerQuery />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
