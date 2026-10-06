import React, { useState } from "react";
import axios from "axios";
import CodeEditor from "@/components/CodeEditor";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";

const AddSampleAnswer = () => {
  const navigate = useNavigate();
  const [questionTitle, setQuestionTitle] = useState("");
  const [language, setLanguage] = useState("python");
  const [idealCode, setIdealCode] = useState("");
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);
    setError(null);

    try {
      const response = await axios.post(
        `${import.meta.env.VITE_API_BASE_URL}/add-sample-answer`,
        {
          question_title: questionTitle,
          language,
          ideal_code: idealCode,
        }
      );

      setMessage(response.data.message);
      setQuestionTitle("");
      setIdealCode("");
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || "Failed to add sample answer.");
    }
  };

  return (
    <div className="relative min-h-screen bg-gradient-to-b from-black via-gray-900 to-black text-white px-4 py-10">
      {/* Background Glow Effects */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/3 left-1/4 w-72 h-72 bg-green-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute top-1/2 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
      </div>

      <div className="max-w-4xl mx-auto bg-gray-800/40 backdrop-blur-lg border border-gray-700 p-8 rounded-2xl shadow-xl">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-12 h-12 bg-gradient-to-r from-purple-500 to-cyan-500 rounded-xl flex items-center justify-center">
            <Plus className="w-6 h-6 text-white" />
          </div>
          <div>
            <h2 className="text-2xl font-bold">Add Sample Answer</h2>
            <p className="text-gray-400">
              Add sample answers to improve code feedback
            </p>
          </div>
        </div>

        {message && (
          <div className="mb-6 p-4 rounded-lg bg-green-900/30 border border-green-600 text-green-300">
            {message}
          </div>
        )}
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-900/30 border border-red-600 text-red-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block mb-2 font-medium text-gray-300">
              Question Title
            </label>
            <input
              type="text"
              className="w-full bg-gray-900 text-white border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-gray-500"
              value={questionTitle}
              onChange={(e) => setQuestionTitle(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block mb-2 font-medium text-gray-300">
              Language
            </label>
            <select
              className="w-full bg-gray-900 text-white border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-gray-500"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
            </select>
          </div>

          <div>
            <label className="block mb-2 font-medium text-gray-300">
              Ideal Code
            </label>
            <CodeEditor
              language={language}
              code={idealCode}
              onChange={setIdealCode}
            />
          </div>

          <div className="flex justify-between items-center pt-4">
            <button
              type="submit"
              className="bg-gradient-to-r from-purple-500 to-cyan-500 hover:from-purple-600 hover:to-cyan-600 text-white px-6 py-2 rounded-xl font-semibold transition-all duration-200 transform hover:scale-105"
            >
              Add Sample Answer
            </button>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="bg-gray-700 hover:bg-gray-600 text-white px-6 py-2 rounded-xl font-semibold transition-all duration-200 transform hover:scale-105"
            >
              ← Back to Home
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddSampleAnswer;
