import React, { useEffect, useState } from "react";
import axios from "axios";
import { Sparkles } from "lucide-react";

const SubmissionHistory = () => {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await axios.get(
          `${import.meta.env.VITE_API_BASE_URL}/submission-history`
        );
        setSubmissions(res.data);
      } catch (err) {
        console.error("Failed to load submission history", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white relative">
      {/* Animated background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-pink-500/5 rounded-full blur-3xl animate-pulse delay-2000"></div>
      </div>

      <div className="relative z-10 max-w-6xl mx-auto p-6">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 bg-gradient-to-r from-purple-500 to-cyan-500 rounded-xl flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <div>
            <h2 className="text-3xl font-bold text-white">
              Submission History
            </h2>
            <p className="text-gray-400">
              Your past attempts and their AI evaluations
            </p>
          </div>
        </div>

        {loading ? (
          <p className="text-gray-400">Loading...</p>
        ) : submissions.length === 0 ? (
          <p className="text-gray-400">No submissions yet.</p>
        ) : (
          <div className="space-y-6">
            {[...submissions].reverse().map((sub) => (
              <div
                key={sub.id}
                className="bg-gray-800/50 backdrop-blur-sm border border-gray-700 rounded-xl p-6 transition-all hover:shadow-xl hover:border-gray-500"
              >
                <div className="text-sm text-gray-400 mb-2">
                  <strong className="text-white">Submitted:</strong>{" "}
                  {new Date(sub.created_at).toLocaleString()}
                </div>

                <pre className="bg-gray-900/60 text-gray-300 p-4 rounded-md text-sm overflow-x-auto max-h-60 border border-gray-700">
                  {sub.code}
                </pre>

                <div className="mt-4 text-sm space-y-2 text-gray-300">
                  <div>
                    <strong className="text-white">Language:</strong>{" "}
                    {sub.language}
                  </div>
                  <div>
                    <strong className="text-white">Pass:</strong>{" "}
                    {sub.pass_status ? (
                      <span className="text-green-400">✅ Passed</span>
                    ) : (
                      <span className="text-red-400">❌ Failed</span>
                    )}
                  </div>
                  <div>
                    <strong className="text-white">Readability:</strong>{" "}
                    {sub.readability_score}/10
                  </div>
                  <div>
                    <strong className="text-white">Efficiency:</strong>{" "}
                    {sub.efficiency_score}/10
                  </div>
                  <div>
                    <strong className="text-white">Similarity:</strong>{" "}
                    {sub.similarity_score != null
                      ? `${sub.similarity_score}%`
                      : "N/A"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SubmissionHistory;
