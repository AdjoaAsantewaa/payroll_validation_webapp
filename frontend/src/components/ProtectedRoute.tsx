import { type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { Role } from "../types";

export function ProtectedRoute({
  role,
  requireAdmin,
  children,
}: {
  role: Role;
  requireAdmin?: boolean;
  children: ReactNode;
}) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role || (requireAdmin && !user.is_admin)) {
    return <Navigate to={user.role === "specialist" ? "/dashboard" : "/submitter/status"} replace />;
  }
  return <>{children}</>;
}
