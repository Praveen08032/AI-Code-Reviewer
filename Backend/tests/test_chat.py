import os
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.ai_utils import get_chat_reply
from app.chat import get_chat_db
from app.main import app
from app.models import Base, ChatConversation, ChatMessage, SampleAnswer, Submission
from app.auth import get_current_user
from auth_helpers import add_test_user


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.quota = patch.dict(os.environ, {"CHAT_REQUESTS_PER_MINUTE": "1000"})
        self.quota.start()
        self.addCleanup(self.quota.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.user = add_test_user(self.Session)
        app.dependency_overrides[get_current_user] = lambda: self.user

        def test_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_chat_db] = test_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    @patch("app.chat.get_chat_reply", return_value="Recursion means a function calls itself.")
    def test_messages_persist_and_can_be_read_by_new_client(self, reply):
        response = self.client.post("/chat/messages", json={"message": "What is recursion?"})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        reply.assert_called_once_with("What is recursion?", [])
        self.assertEqual([m["role"] for m in data["messages"]], ["user", "assistant"])
        self.assertTrue(data["messages"][0]["created_at"].endswith("+00:00"))
        with TestClient(app) as other_client:
            history = other_client.get("/chat/conversations").json()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["title"], "What is recursion?")
            saved = other_client.get("/chat/conversations/" + data["conversation"]["id"]).json()
            self.assertEqual(saved["messages"], data["messages"])

    @patch("app.chat.get_chat_reply", side_effect=["Remembered.", "cedar-42", "A new topic."])
    def test_follow_up_uses_only_the_selected_conversation(self, reply):
        first = self.client.post("/chat/messages", json={"message": "Remember cedar-42."}).json()
        conversation_id = first["conversation"]["id"]
        follow_up = self.client.post("/chat/messages", json={"conversation_id": conversation_id, "message": "What marker?"})
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(reply.call_args.args[1], [{"role": "user", "content": "Remember cedar-42."},
                                                 {"role": "assistant", "content": "Remembered."}])
        separate = self.client.post("/chat/messages", json={"message": "New question."}).json()
        reply.assert_called_with("New question.", [])
        self.assertNotEqual(separate["conversation"]["id"], conversation_id)
        self.assertEqual(len(self.client.get(f"/chat/conversations/{conversation_id}").json()["messages"]), 4)
        self.assertEqual(len(self.client.get("/chat/conversations").json()), 2)

    @patch("app.chat.get_chat_reply", return_value="Answer")
    def test_recent_context_is_bounded_while_full_history_is_kept(self, reply):
        conversation_id = None
        for i in range(12):
            data = self.client.post("/chat/messages", json={"conversation_id": conversation_id, "message": f"Question {i}"}).json()
            conversation_id = data["conversation"]["id"]
        context = reply.call_args.args[1]
        self.assertEqual(len(context), 20)
        self.assertEqual(context[0], {"role": "user", "content": "Question 1"})
        self.assertEqual(context[-1]["role"], "assistant")
        self.assertEqual(len(self.client.get(f"/chat/conversations/{conversation_id}").json()["messages"]), 24)

    @patch("app.chat.get_chat_reply", side_effect=RuntimeError("Gemini is unavailable."))
    def test_failed_generation_does_not_save_fake_answers_or_empty_chats(self, reply):
        response = self.client.post("/chat/messages", json={"message": "Hello"})
        self.assertEqual(response.status_code, 502)
        with self.Session() as db:
            self.assertEqual(db.query(ChatConversation).count(), 0)
            self.assertEqual(db.query(ChatMessage).count(), 0)

    @patch("app.chat.get_chat_reply", return_value=" ")
    def test_empty_response_is_not_saved(self, reply):
        self.assertEqual(self.client.post("/chat/messages", json={"message": "Hello"}).status_code, 502)
        self.assertEqual(self.client.get("/chat/conversations").json(), [])

    @patch("app.chat.get_chat_reply")
    def test_blank_message_and_unknown_conversation_are_rejected(self, reply):
        self.assertEqual(self.client.post("/chat/messages", json={"message": " \n "}).status_code, 422)
        self.assertEqual(self.client.post("/chat/messages", json={"message": "Hello", "conversation_id": str(uuid4())}).status_code, 404)
        reply.assert_not_called()

    @patch("app.chat.get_chat_reply", return_value="Reply")
    def test_delete_one_conversation_removes_its_messages_and_preserves_other_chats(self, reply):
        first = self.client.post("/chat/messages", json={"message": "First chat"}).json()["conversation"]["id"]
        second = self.client.post("/chat/messages", json={"message": "Second chat"}).json()["conversation"]["id"]
        response = self.client.delete(f"/chat/conversations/{first}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.get(f"/chat/conversations/{first}").status_code, 404)
        self.assertEqual(self.client.post("/chat/messages", json={"conversation_id": first, "message": "Follow-up"}).status_code, 404)
        self.assertEqual(reply.call_count, 2)
        self.assertEqual([chat["id"] for chat in self.client.get("/chat/conversations").json()], [second])
        with self.Session() as db:
            self.assertEqual(db.query(ChatMessage).filter_by(conversation_id=first).count(), 0)
            self.assertEqual(db.query(ChatMessage).filter_by(conversation_id=second).count(), 2)

    @patch("app.chat.get_chat_reply", return_value="Reply")
    def test_clear_history_removes_chats_and_messages_but_preserves_review_data(self, reply):
        self.client.post("/chat/messages", json={"message": "First chat"})
        self.client.post("/chat/messages", json={"message": "Second chat"})
        with self.Session() as db:
            db.add(Submission(language="python", code="print(1)"))
            db.add(SampleAnswer(language="python", question_title="custom sample", ideal_code="print(1)"))
            db.commit()
        self.assertEqual(self.client.delete("/chat/conversations").status_code, 204)
        self.assertEqual(self.client.get("/chat/conversations").json(), [])
        with self.Session() as db:
            self.assertEqual(db.query(ChatConversation).count(), 0)
            self.assertEqual(db.query(ChatMessage).count(), 0)
            self.assertEqual(db.query(Submission).count(), 1)
            self.assertEqual(db.query(SampleAnswer).count(), 1)
        self.assertEqual(self.client.delete("/chat/conversations").status_code, 204)

    @patch("app.chat.get_chat_reply")
    def test_delete_unknown_conversation_returns_not_found(self, reply):
        response = self.client.delete(f"/chat/conversations/{uuid4()}")
        self.assertEqual(response.status_code, 404)
        reply.assert_not_called()

    @patch("app.ai_utils.genai.Client")
    def test_sdk_receives_ordered_conversation_roles(self, model):
        generate = model.return_value.__enter__.return_value.models.generate_content
        generate.return_value.text = "Follow-up answer"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = get_chat_reply("Follow up", [{"role": "user", "content": "Question"},
                                                  {"role": "assistant", "content": "Answer"}])
        self.assertEqual(result, "Follow-up answer")
        contents = generate.call_args.kwargs["contents"]
        self.assertEqual([(item.role, item.parts[0].text) for item in contents],
                         [("user", "Question"), ("model", "Answer"), ("user", "Follow up")])
        self.assertIn("CodeCheck Assistant", generate.call_args.kwargs["config"].system_instruction)
        self.assertEqual(model.call_args.kwargs["http_options"].retry_options.attempts, 1)
        model.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
