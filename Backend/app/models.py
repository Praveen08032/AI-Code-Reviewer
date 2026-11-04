from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    language = Column(String(20))
    code = Column(Text)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pass_status = Column(Boolean)
    readability_score = Column(Integer)
    efficiency_score = Column(Integer)
    suggestions = Column(Text)         # Comma-separated or JSON string
    errors = Column(Text)              # Same
    corrected_code = Column(Text)
    raw_ai_feedback = Column(Text)
    similarity_score = Column(Float)
    is_similar_to_sample = Column(Boolean)

class SampleAnswer(Base):
    __tablename__ = "sample_answers"

    id = Column(Integer, primary_key=True, index=True)
    question_title = Column(String, nullable=False)
    language = Column(String, nullable=False)
    ideal_code = Column(Text, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(80), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True)
    role = Column(String(12), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    google_sub = Column(String(255), unique=True, nullable=False, index=True)
    # google_sub retains its legacy database name; other providers use namespaced IDs.
    auth_provider = Column(String(20), nullable=False, default="google", server_default="google")
    email = Column(String(320), nullable=False)
    name = Column(String(200), nullable=False)
    picture = Column(Text, nullable=True)
    first_login_at = Column(DateTime, nullable=False)
    last_login_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    login_count = Column(Integer, nullable=False, default=0)
    blocked_at = Column(DateTime, nullable=True)


class OwnerAccount(Base):
    __tablename__ = "owner_account"
    id = Column(Integer, primary_key=True)
    google_sub = Column(String(255), unique=True, nullable=False)
    local_access_approved_at = Column(DateTime, nullable=True)


class LoginChallenge(Base):
    __tablename__ = "login_challenges"
    token_hash = Column(String(64), primary_key=True)
    nonce_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class AccessToken(Base):
    __tablename__ = "access_tokens"
    token_hash = Column(String(64), primary_key=True)
    session_hash = Column(String(64), ForeignKey("auth_sessions.token_hash"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)


class SignInEvent(Base):
    __tablename__ = "sign_in_events"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    signed_in_at = Column(DateTime, nullable=False, index=True)


class OAuthFlow(Base):
    __tablename__ = "oauth_flows"
    state_hash = Column(String(64), primary_key=True)
    cookie_hash = Column(String(64), nullable=False)
    provider = Column(String(20), nullable=False)
    flow_data = Column(Text, nullable=False)
    callback_data = Column(Text, nullable=True)
    handoff_hash = Column(String(64), nullable=True, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)


class EmailCredential(Base):
    __tablename__ = "email_credentials"
    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    verified_at = Column(DateTime, nullable=True)


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    token_hash = Column(String(64), primary_key=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    owner_token_hash = Column(String(64), nullable=True)
    code_hash = Column(String(64), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class OwnerInvite(Base):
    __tablename__ = "owner_invites"
    token_hash = Column(String(64), primary_key=True)
    expires_at = Column(DateTime, nullable=False)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key_hash = Column(String(64), primary_key=True)
    attempts = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False, index=True)


class AIRequestLease(Base):
    __tablename__ = "ai_request_leases"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)

