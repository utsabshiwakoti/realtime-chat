import { Navigate } from "react-router-dom";
import { useAuth } from "../features/auth/AuthContext";

export default function ProtectedRoute({ children }) {
  const { token, loading } = useAuth();
  if (loading) return <p style={{ padding: 24 }}>Loading...</p>;
  if (!token) return <Navigate to="/login" replace />;
  return children;
}
