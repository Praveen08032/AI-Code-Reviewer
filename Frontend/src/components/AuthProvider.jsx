import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { AuthContext } from "@/lib/auth";
import { AUTH_CHANGE_KEY, clearCachedIdentity, errorMessage, restoreSession, subscribeAuth } from "@/lib/api";

export default function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const retryVersion = useRef(0);
  const retry = useCallback(() => {
    const version = ++retryVersion.current;
    setLoading(true); setError("");
    return restoreSession().catch((err) => {
      if (version === retryVersion.current && !axios.isCancel(err) && err.response?.status !== 401) setError(errorMessage(err));
    }).finally(() => { if (version === retryVersion.current) setLoading(false); });
  }, []);
  useEffect(() => {
    const unsubscribe = subscribeAuth(setUser);
    retry();
    const changed = (event) => {
      if (event.key === AUTH_CHANGE_KEY) { clearCachedIdentity(); retry(); }
    };
    window.addEventListener("storage", changed);
    return () => { unsubscribe(); window.removeEventListener("storage", changed); };
  }, [retry]);
  return <AuthContext.Provider value={{ user, loading, error, retry }}>{children}</AuthContext.Provider>;
}
