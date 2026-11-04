import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { clearChatHistory, deleteChat, errorMessage, getChat, listChats, sendChat } from "@/lib/api";
import "@/styles/assistant.css";
import { useTheme } from "@/lib/theme";
import { useAuth } from "@/lib/auth";

const readActiveChat = (key) => {
  try { return localStorage.getItem(key); } catch { return null; }
};

function MessageBody({ text }) {
  return text.split(/(```[\s\S]*?```)/g).map((part, index) => {
    if (!part.startsWith("```")) return <span key={index}>{part}</span>;
    const language = part.match(/^```([^\n]*)/)?.[1].trim();
    return <div className="chat-code" key={index}><small>{language || "Code"}</small>
      <pre><code>{part.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")}</code></pre>
    </div>;
  });
}

function ChatGlyph({ kind = "message" }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === "trash" ? <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></>
      : kind === "close" ? <path d="m6 6 12 12M6 18 18 6" />
      : kind === "history" ? <><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></>
        : kind === "plus" ? <path d="M12 5v14M5 12h14" />
          : kind === "send" ? <path d="M12 19V5m-6 6 6-6 6 6" />
            : kind === "code" ? <path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16" />
              : <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" /><path d="M7 9h10M7 13h6" /></>}
  </svg>;
}

export default function Chatbot() {
  const { theme } = useTheme();
  const { user } = useAuth();
  const activeChatKey = `codecheck.activeChat:${user.id}`;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("chat");
  const [conversationId, setConversationId] = useState(() => readActiveChat(activeChatKey));
  const [conversations, setConversations] = useState([]);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const inputRef = useRef(null), launcherRef = useRef(null), bottomRef = useRef(null);
  const cancelDeleteRef = useRef(null), deleteSourceRef = useRef(null);

  useEffect(() => { if (deleteTarget) cancelDeleteRef.current?.focus(); }, [deleteTarget]);

  useEffect(() => {
    try {
      if (conversationId) localStorage.setItem(activeChatKey, conversationId);
      else localStorage.removeItem(activeChatKey);
    } catch { /* Chat history remains available from the server. */ }
  }, [conversationId, activeChatKey]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setHistoryLoading(true);
    listChats().then((data) => { if (alive) setConversations(data); })
      .catch((err) => { if (alive) setError(errorMessage(err)); })
      .finally(() => { if (alive) setHistoryLoading(false); });
    return () => { alive = false; };
  }, [open]);

  useEffect(() => {
    if (!open || !conversationId) { setLoading(false); return; }
    let alive = true;
    setLoading(true);
    getChat(conversationId).then((data) => { if (alive) setMessages(data.messages); })
      .catch((err) => {
        if (!alive) return;
        if (err.response?.status === 404) { setConversationId(null); setMessages([]); }
        setError(errorMessage(err));
      }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [open, conversationId]);

  useEffect(() => {
    if (open && view === "chat" && !loading && !pending) inputRef.current?.focus();
  }, [open, view, loading, pending]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ block: "nearest" }); }, [messages, pending, open, view]);

  useEffect(() => {
    if (!open) return;
    const close = (event) => {
      if (event.key === "Escape") {
        if (deleteTarget) {
          if (!deleting) { setDeleteTarget(null); deleteSourceRef.current?.focus(); }
          return;
        }
        setOpen(false); launcherRef.current?.focus();
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open, deleteTarget, deleting]);

  function newChat() {
    setDeleteTarget(null);
    setConversationId(null);
    setMessages([]);
    setDraft("");
    setError("");
    setLoading(false);
    setView("chat");
  }

  async function confirmDeletion() {
    if (!deleteTarget || deleting || pending) return;
    const target = deleteTarget;
    setDeleting(true);
    setError("");
    try {
      if (target.all) await clearChatHistory();
      else {
        try { await deleteChat(target.id); }
        catch (err) { if (err.response?.status !== 404) throw err; }
      }
      setConversations((current) => target.all ? [] : current.filter((chat) => chat.id !== target.id));
      if (target.all || target.id === conversationId) {
        setConversationId(null); setMessages([]); setDraft(""); setLoading(false);
      }
      setDeleteTarget(null);
    } catch (err) { setError(errorMessage(err)); }
    finally { setDeleting(false); }
  }

  async function send(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || pending || loading) return;
    const optimisticId = `pending-${Date.now()}`;
    setMessages((current) => [...current, { id: optimisticId, role: "user", content: text }]);
    setDraft("");
    setError("");
    setPending(true);
    try {
      const result = await sendChat({ conversation_id: conversationId, message: text });
      setMessages((current) => [...current.filter((message) => message.id !== optimisticId), ...result.messages]);
      setConversationId(result.conversation.id);
      setConversations((current) => [result.conversation, ...current.filter((chat) => chat.id !== result.conversation.id)]);
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimisticId));
      setDraft(text);
      setError(errorMessage(err));
    } finally { setPending(false); }
  }

  return <>
    <button className="chat-launcher" ref={launcherRef} aria-label="Open chatbot" aria-expanded={open} aria-controls="assistant-panel"
      title="Chat with CodeCheck Assistant" onClick={() => setOpen((current) => !current)}>
      <ChatGlyph />
    </button>
    {open && createPortal(<section id="assistant-panel" className="chat-panel" data-theme={theme} role="dialog" aria-modal="false" aria-labelledby="assistant-heading">
      <header className="chat-header">
        <div className="chat-brand-mark"><ChatGlyph kind="code" /></div>
        <div className="chat-heading"><h2 id="assistant-heading">CodeCheck <span>Assistant</span></h2><p>Code, questions, and clear answers</p></div>
        <button className="chat-icon" aria-label="Close assistant" onClick={() => { setOpen(false); launcherRef.current?.focus(); }}><ChatGlyph kind="close" /></button>
      </header>
      <div className="chat-toolbar">
        <div className="chat-view-switch">
          <button className={view === "chat" ? "selected" : ""} aria-pressed={view === "chat"} disabled={deleting} onClick={() => { setDeleteTarget(null); setView("chat"); }}><ChatGlyph />Chat</button>
          <button className={view === "history" ? "selected" : ""} aria-pressed={view === "history"} disabled={pending || deleting} onClick={() => setView("history")}><ChatGlyph kind="history" />History</button>
        </div>
        <button className="chat-new" disabled={pending || loading || deleting} onClick={newChat}><ChatGlyph kind="plus" />New chat</button>
      </div>
      {view === "history" ? <div className="chat-history">
        <div className="chat-history-heading"><h3>Your conversations</h3>
          <button className="chat-clear" disabled={!conversations.length || historyLoading || loading || pending || deleting} onClick={(event) => { deleteSourceRef.current = event.currentTarget; setDeleteTarget({ all: true }); }}><ChatGlyph kind="trash" />Clear all</button>
        </div><p className="chat-history-caption">Reopen a chat or delete one you no longer need.</p>
        {deleteTarget && <div className="chat-delete-confirm" role="alertdialog" aria-modal="false" aria-labelledby="chat-delete-heading">
          <h4 id="chat-delete-heading">{deleteTarget.all ? "Delete all chat history?" : "Delete this conversation?"}</h4>
          <p>{deleteTarget.all ? "All saved chats and their messages will be permanently deleted." : `“${deleteTarget.title}” and its messages will be permanently deleted.`}</p>
          <div><button className="chat-cancel-delete" ref={cancelDeleteRef} disabled={deleting} onClick={() => { setDeleteTarget(null); deleteSourceRef.current?.focus(); }}>Cancel</button>
            <button className="chat-confirm-delete" disabled={deleting} onClick={confirmDeletion}>{deleting ? "Deleting…" : deleteTarget.all ? "Delete all" : "Delete chat"}</button></div>
        </div>}
        {historyLoading && <p className="chat-muted">Loading conversations…</p>}
        {!historyLoading && !conversations.length && <p className="chat-muted">Your saved conversations will appear here.</p>}
        {conversations.map((chat) => <div className="chat-history-item" key={chat.id} data-active={conversationId === chat.id}>
          <button className="chat-history-open" aria-current={conversationId === chat.id} disabled={deleting} onClick={() => {
          if (conversationId !== chat.id) setMessages([]);
          setDeleteTarget(null); setConversationId(chat.id); setError(""); setView("chat");
        }}><ChatGlyph kind="message" /><span className="chat-history-text"><b>{chat.title}</b><time dateTime={chat.updated_at}>{new Date(chat.updated_at).toLocaleString()}</time></span><span className="chat-history-arrow" aria-hidden="true">↗</span></button>
          <button className="chat-delete" aria-label={`Delete conversation: ${chat.title}`} title="Delete conversation" disabled={deleting || pending || loading || historyLoading} onClick={(event) => { deleteSourceRef.current = event.currentTarget; setDeleteTarget({ id: chat.id, title: chat.title }); }}><ChatGlyph kind="trash" /></button>
        </div>)}
      </div> : <>
        <div className="chat-messages" role="log" aria-label="Chat messages" aria-live="polite" aria-busy={loading || pending}>
          {loading && <p className="chat-muted">Loading conversation…</p>}
          {!loading && !messages.length && <div className="chat-welcome"><div className="chat-welcome-mark"><ChatGlyph kind="code" /></div><span className="chat-eyebrow">A fresh conversation</span><b>What are you working on?</b><p>Untangle an error, explore an idea,<br />or ask a quick question.</p>
            <button className="chat-suggestion" onClick={() => setDraft("Can you help me understand an error in my code?")}>Help me understand an error <span aria-hidden="true">↗</span></button>
          </div>}
          {messages.map((message) => <article className={`chat-message ${message.role}`} key={message.id}>
            <div className="chat-message-label"><span className="chat-avatar" aria-hidden="true">{message.role === "user" ? "Y" : <ChatGlyph kind="code" />}</span><small>{message.role === "user" ? "You" : "CodeCheck"}</small></div><div className="chat-bubble"><MessageBody text={message.content} /></div>
          </article>)}
          {pending && <p className="chat-thinking"><span aria-hidden="true"><i /><i /><i /></span>Thinking…</p>}
          <div ref={bottomRef} />
        </div>
        <form className="chat-compose" onSubmit={send}>
          <label className="sr-only" htmlFor="chat-question">Your question</label>
          <div className="chat-input-box"><textarea id="chat-question" ref={inputRef} value={draft} maxLength={12000} rows={2} disabled={pending || loading}
            placeholder="Message CodeCheck…" onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(event); }
            }} />
            <div className="chat-input-actions"><small>Enter to send · Shift+Enter for a new line</small><button type="submit" aria-label={pending ? "Sending message" : "Send message"} disabled={!draft.trim() || pending || loading}><ChatGlyph kind="send" /></button></div>
          </div>
        </form>
      </>}
      {error && <p className="chat-error" role="alert">{error}</p>}
    </section>, document.body)}
  </>;
}
