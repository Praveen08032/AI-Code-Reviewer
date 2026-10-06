// File: src/App.jsx
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import Rail from "./components/Rail";
import Dashboard from "./pages/Dashboard";
import SubmitCode from "./pages/SubmitCode";
import SampleAnswerList from "./pages/SampleAnswerList";
import AddSampleAnswer from "./pages/AddSampleAnswer";
import SubmissionHistory from "./pages/SubmissionHistory";

export default function App() {
  return (
    <Router>
      <div className="app">
        <Rail />
        <main className="ws">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dashboard" element={<Navigate to="/" replace />} />
            <Route path="/submit" element={<SubmitCode />} />
            <Route path="/sample-questions" element={<SampleAnswerList />} />
            <Route path="/add-sample" element={<AddSampleAnswer />} />
            <Route path="/history-submissions" element={<SubmissionHistory />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
