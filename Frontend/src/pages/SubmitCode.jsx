import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import CodeEditor from "@/components/CodeEditor";
import FeedbackPanel from "@/components/FeedbackPanel";
import { useNavigate } from "react-router-dom";
import { Code, Zap, Eye, Sparkles, Play } from "lucide-react";

const SubmitCode = () => {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("python");
  const [questionTitle, setQuestionTitle] = useState("");
  const [questionOptions, setQuestionOptions] = useState([]);
  const [feedback, setFeedback] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [error, setError] = useState(null);

  // Only show questions that have a sample answer in the selected language
  const filteredQuestions = questionOptions.filter((q) => q.language === language);

  const scrollRef = useRef(null);

  useEffect(() => {
    const fetchQuestions = async () => {
      try {
        const res = await axios.get(
          `${import.meta.env.VITE_API_BASE_URL}/sample-questions`
        );
        setQuestionOptions(res.data);
      } catch (err) {
        console.error("Failed to fetch questions", err);
      }
    };
    fetchQuestions();
  }, []);

  useEffect(() => {
    if (showFeedback) {
      scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [showFeedback]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    setError(null);

    if (!code.trim() || !language || !questionTitle) {
      setError("Please choose a language and question, and write some code.");
      return;
    }

    setLoading(true);
    try {
      const res = await axios.post(
        `${import.meta.env.VITE_API_BASE_URL}/submit-code`,
        { code, language, question_title: questionTitle }
      );
      setFeedback(res.data);
      setShowFeedback(true);
    } catch (err) {
      console.error("Submission failed:", err);
      const detail = err.response?.data?.detail || "";
      if (detail.includes("429") || detail.toLowerCase().includes("quota")) {
        setError("The AI's free daily limit has been reached. Please try again later.");
      } else if (!err.response) {
        setError("Could not reach the server. It may be waking up, so please try again in a minute.");
      } else {
        setError("The AI review failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white">
      {/* Glows */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-pink-500/5 rounded-full blur-3xl animate-pulse delay-2000"></div>
      </div>

      {/* Content */}
      <div className="relative z-10 max-w-6xl mx-auto p-6 space-y-8">
        {/* Feedback Panel */}
        {loading && (
          <div ref={scrollRef} className="text-center text-gray-400 animate-pulse text-lg mt-4">
            <p>Analyzing your code... 🔍</p>
          </div>
        )}

        {showFeedback && feedback && !loading && (
          <div ref={scrollRef} className="space-y-4">
            <div className="text-left">
              <button
                onClick={() => setShowFeedback(false)}
                className="mt-4 px-4 py-2 bg-gray-800 border border-gray-500 rounded-lg text-sm hover:bg-gray-700 transition"
              >
                ← Back to Editor
              </button>
            </div>
            <FeedbackPanel feedback={feedback} />
          </div>
        )}

        {/* Code Submit Form */}
        {!showFeedback && (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-gradient-to-r from-purple-500 to-cyan-500 rounded-xl flex items-center justify-center">
                <Code className="w-6 h-6 text-white" />
              </div>
              <div>
                <h2 className="text-2xl font-bold">Submit Your Solution</h2>
                <p className="text-gray-400">
                  Write, test, and get instant AI feedback
                </p>
              </div>
            </div>

            {/* Language Selector */}
            <div>
              <label className="text-sm font-medium text-gray-300">
                Programming Language
              </label>
              <select
                value={language}
                onChange={(e) => {
                  setLanguage(e.target.value);
                  setQuestionTitle("");
                }}
                className="w-full bg-gray-800/50 text-white border border-gray-700 rounded-xl px-4 py-3 mt-2 focus:outline-none"
              >
                <option value="python">🐍 Python</option>
                <option value="javascript">🚀 JavaScript</option>
              </select>
            </div>

            {/* Question Title */}
            <div>
              <label className="text-sm font-medium text-gray-300">
                Challenge Question
              </label>
              <select
                value={questionTitle}
                onChange={(e) => setQuestionTitle(e.target.value)}
                className="w-full bg-gray-800/50 text-white border border-gray-700 rounded-xl px-4 py-3 mt-2 focus:outline-none"
              >
                <option value="">🎯 Choose your challenge...</option>
                {filteredQuestions.map((q) => (
                  <option key={q.id} value={q.question_title}>
                    {q.question_title}
                  </option>
                ))}
              </select>
            </div>

            {/* Code Editor */}
            <div>
              <label className="text-sm font-medium text-gray-300">
                Your Code
              </label>
              <CodeEditor code={code} onChange={setCode} language={language} />
            </div>

            {error && (
              <div className="p-4 rounded-lg bg-red-900/30 border border-red-600 text-red-300">
                {error}
              </div>
            )}

            {/* Submit & View Result */}
            <div className="flex flex-col sm:flex-row gap-4">
              <button
                type="submit"
                disabled={
                  !code.trim() || !language || !questionTitle || loading
                }
                className="flex-1 bg-gradient-to-r from-purple-500 to-cyan-500 hover:from-purple-600 hover:to-cyan-600 text-white font-semibold px-6 py-3 rounded-xl flex items-center justify-center gap-2 transition-all"
              >
                {loading ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Play className="w-5 h-5" />
                    Submit & Analyze
                  </>
                )}
              </button>
              {feedback && (
                <button
                  type="button"
                  onClick={() => setShowFeedback(true)}
                  className="flex-1 bg-gray-800 border border-gray-500 hover:bg-gray-700 text-white px-6 py-3 rounded-xl flex items-center justify-center gap-2"
                >
                  <Eye className="w-5 h-5" />
                  View Result
                </button>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default SubmitCode;
