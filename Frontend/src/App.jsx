// File: src/App.jsx
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import Rail from "./components/Rail";
import Dashboard from "./pages/Dashboard";
import SubmitCode from "./pages/SubmitCode";
import SampleAnswerList from "./pages/SampleAnswerList";
import AddSampleAnswer from "./pages/AddSampleAnswer";
import SubmissionHistory from "./pages/SubmissionHistory";
import Login, { SessionLoading } from "./pages/Login";
import AccessLog from "./pages/AccessLog";
import { useAuth } from "./lib/auth";
import { useEffect, useState } from "react";

export default function App() {
  return (
    <Router><AuthenticatedApp /></Router>
  );
}

function AuthenticatedApp() {
  const { user, loading } = useAuth();
  const [ownerSetup, setOwnerSetup] = useState(() => new URLSearchParams(window.location.hash.slice(1)).has("owner-setup"));
  useEffect(() => {
    const changed = () => { if (new URLSearchParams(window.location.hash.slice(1)).has("owner-setup")) setOwnerSetup(true); };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  if (loading) return <SessionLoading />;
  if (!user || ownerSetup) return <Login onSignedIn={() => setOwnerSetup(false)} />;
  return <div className="app" key={user.id}>
        <Rail />
        <main className="ws">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dashboard" element={<Navigate to="/" replace />} />
            <Route path="/submit" element={<SubmitCode />} />
            <Route path="/sample-questions" element={<SampleAnswerList />} />
            <Route path="/add-sample" element={<AddSampleAnswer />} />
            <Route path="/history-submissions" element={<SubmissionHistory />} />
            <Route path="/access" element={user.is_owner ? <AccessLog /> : <Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>;
}
