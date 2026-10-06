import React from "react";
import { useNavigate } from "react-router-dom";
import { Rocket, Eye } from "lucide-react";

const LandingPage = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white px-6 py-10">
      {/* Animated background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-pink-500/5 rounded-full blur-3xl animate-pulse delay-2000"></div>
      </div>

      {/* HERO SECTION */}
      <div className="max-w-6xl mx-auto text-center py-20">
        <h1 className="text-5xl font-bold bg-gradient-to-r from-purple-400 to-cyan-400 text-transparent bg-clip-text mb-6">
          Welcome to CodeCheck
        </h1>
        <p className="text-lg text-gray-300 mb-10 max-w-2xl mx-auto">
          A smart, beautiful, and insightful way to test, analyze, and improve
          your code.
        </p>
        <div className="flex justify-center gap-4">
          <button
            onClick={() => navigate("/submit")}
            className="flex items-center gap-2 bg-gradient-to-r from-purple-500 to-cyan-500 hover:from-purple-600 hover:to-cyan-600 text-white px-6 py-3 rounded-xl text-lg font-semibold shadow-md hover:shadow-purple-400/30 transition-all"
          >
            <Rocket className="w-5 h-5" />
            Try Now
          </button>
          <button
            onClick={() => navigate("/sample-questions")}
            className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-white px-6 py-3 rounded-xl text-lg font-semibold transition-all"
          >
            <Eye className="w-5 h-5" /> View Samples
          </button>
        </div>
      </div>

      {/* HOW IT WORKS */}
      <section className="max-w-5xl mx-auto py-16 space-y-10">
        <h2 className="text-3xl font-bold text-white text-center">
          How It Works
        </h2>
        <div className="grid md:grid-cols-3 gap-8 text-center text-gray-300">
          <div className="p-6 bg-slate-800/50 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl font-semibold text-white mb-2">
              1. Submit Code
            </h3>
            <p>Use our editor to submit your code in Python or JavaScript.</p>
          </div>
          <div className="p-6 bg-slate-800/50 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl font-semibold text-white mb-2">
              2. Get Feedback
            </h3>
            <p>We analyze readability, efficiency, and similarity.</p>
          </div>
          <div className="p-6 bg-slate-800/50 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl font-semibold text-white mb-2">
              3. Improve Faster
            </h3>
            <p>Track history and review curated ideal solutions.</p>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="max-w-6xl mx-auto py-16">
        <h2 className="text-3xl font-bold text-center text-white mb-10">
          Why CodeCheck?
        </h2>
        <div className="grid md:grid-cols-2 gap-10">
          <div className="bg-gray-800/40 p-6 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl text-purple-300 font-semibold mb-2">
              📈 Performance Insights
            </h3>
            <p className="text-gray-300">
              Quantified feedback on readability, efficiency, and test pass
              rates.
            </p>
          </div>
          <div className="bg-gray-800/40 p-6 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl text-purple-300 font-semibold mb-2">
              🧠 Smart Evaluation
            </h3>
            <p className="text-gray-300">
              Similarity detection helps detect plagiarism and reuse patterns.
            </p>
          </div>
          <div className="bg-gray-800/40 p-6 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl text-purple-300 font-semibold mb-2">
              📚 Sample Library
            </h3>
            <p className="text-gray-300">
              Compare with expert-curated solutions and learn best practices.
            </p>
          </div>
          <div className="bg-gray-800/40 p-6 rounded-xl border border-gray-700 hover:border-purple-500 hover:shadow-purple-500/30 transition-all shadow-lg">
            <h3 className="text-xl text-purple-300 font-semibold mb-2">
              🕒 Submission History
            </h3>
            <p className="text-gray-300">
              Track all your submissions over time with full feedback.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <div className="text-center py-20">
        <h2 className="text-3xl font-bold text-white mb-6">
          Ready to test your code?
        </h2>
        <button
          onClick={() => navigate("/submit")}
          className="bg-gradient-to-r from-purple-500 to-cyan-500 hover:from-purple-600 hover:to-cyan-600 text-white px-8 py-3 rounded-xl text-lg font-bold transition-all"
        >
          Start Coding
        </button>
      </div>

      {/* FOOTER */}
      <footer className="text-center text-gray-500 text-sm mt-12 border-t border-gray-700 pt-6">
        © {new Date().getFullYear()} CodeCheck. All rights reserved.
      </footer>
    </div>
  );
};

export default LandingPage;
