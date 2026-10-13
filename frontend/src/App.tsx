import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Spinner } from "./components/Layout";
import Account from "./pages/Account";
import Ask from "./pages/Ask";
import BillReview from "./pages/BillReview";
import Bills from "./pages/Bills";
import Dashboard from "./pages/Dashboard";
import Followups from "./pages/Followups";
import Ledger from "./pages/Ledger";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Privacy from "./pages/Privacy";
import Signup from "./pages/Signup";

function Protected({ children, onboarding = false }: { children: JSX.Element; onboarding?: boolean }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.onboarding_done && !onboarding) return <Navigate to="/onboarding" replace />;
  return children;
}

export default function App() {
  const { loading } = useAuth();
  if (loading) return <Spinner />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/bills" element={<Protected><Bills /></Protected>} />
      <Route path="/bills/:id" element={<Protected><BillReview /></Protected>} />
      <Route path="/ask" element={<Protected><Ask /></Protected>} />
      <Route path="/ledger" element={<Protected><Ledger /></Protected>} />
      <Route path="/followups" element={<Protected><Followups /></Protected>} />
      <Route path="/account" element={<Protected><Account /></Protected>} />
      <Route path="/onboarding" element={<Protected onboarding><Onboarding /></Protected>} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
