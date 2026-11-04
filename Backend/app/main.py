from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.schemas import CodeSubmission, CodeFeedback, SampleAnswerCreate, SubmissionRead
from app.database import init_db, SessionLocal, get_db
from app.models import Submission, SampleAnswer, User
from app.auth import router as auth_router, admin_router, get_current_user, allowed_origins
from sqlalchemy import and_, or_, tuple_, text
from app.ai_utils import AIServiceError, get_gemini_feedback, parse_ai_feedback
from app.ai_usage import ai_request
from app.similarity import calculate_similarity, normalize_code
from app.default_answers import DEFAULT_SAMPLES, seed_default_answers, get_sample_description
from app.chat import router as chat_router
from app.oauth import router as oauth_router
from app.password_auth import router as password_auth_router
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from typing import List
import os
import logging

# Load environment variables
load_dotenv()

app = FastAPI()
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(password_auth_router)
app.include_router(admin_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # Pydantic's default errors can echo rejected password values back to clients.
    if request.url.path in {"/auth/login", "/auth/register", "/auth/verify-email", "/auth/resend-verification"}:
        message = error.errors()[0].get("msg", "Check your email and password.").removeprefix("Value error, ")
        return JSONResponse(status_code=422, content={"detail": message})
    # Rejected source code and oversized payloads need not be echoed in an error response.
    errors = [{"type": item["type"], "loc": item["loc"], "msg": item["msg"]} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


init_db()
with SessionLocal() as db:
    seed_default_answers(db)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def visible_samples(user):
    builtin_keys = [(language, title) for language, entries in DEFAULT_SAMPLES.items() for title in entries]
    return or_(SampleAnswer.user_id == user.id, and_(SampleAnswer.user_id.is_(None),
               tuple_(SampleAnswer.language, SampleAnswer.question_title).in_(builtin_keys)))


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from error
    return {"status": "ok", "assessment": "static_ai_review", "code_execution": False}


# Plain "def" (not async): the Gemini call is blocking, so FastAPI runs it in a worker thread
@app.post("/submit-code", response_model=CodeFeedback)
def submit_code(data: CodeSubmission, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        # Step 1: Get raw AI feedback
        is_custom = data.review_mode == "custom"
        title = "" if is_custom else data.question_title
        description = data.task_description.strip() if is_custom else get_sample_description(data.language, title)
        with ai_request(db, user.id, "review"):
            ai_reply = get_gemini_feedback(data.language, data.code, title, description, data.review_mode)

        # Step 2: Parse feedback into structured fields
        parsed = parse_ai_feedback(ai_reply)

        # Step 3: Determine pass/fail status
        readability = parsed["readability_score"] or 0
        efficiency = parsed["efficiency_score"] or 0
        pass_status = (parsed["review_complete"] and parsed["correctness_status"] == "correct" and
                       not parsed["errors"] and not parsed["missing_items"] and readability >= 5 and efficiency >= 5)

        # Step 4: Compare with sample answer
        sample = None if is_custom else db.query(SampleAnswer).filter_by(
            language=data.language.strip().lower(),
            question_title=data.question_title.strip().lower()
        ).filter(visible_samples(user)).order_by(SampleAnswer.user_id.is_(None)).first()

        similarity_score = None
        is_similar_to_sample = None

        if sample:
            similarity_score = calculate_similarity(sample.ideal_code, data.code, data.language)
            is_similar_to_sample = similarity_score >= 70  # Tune threshold as needed

        # Step 5: Package final response
        feedback = CodeFeedback(
            pass_status=pass_status,
            readability_score=parsed["readability_score"],
            efficiency_score=parsed["efficiency_score"],
            suggestions=parsed["suggestions"],
            errors=parsed["errors"],
            corrected_code=parsed["corrected_code"],
            raw_ai_feedback=ai_reply,
            similarity_score=similarity_score,
            is_similar_to_sample=is_similar_to_sample,
            correctness_status=parsed["correctness_status"],
            correctness_reason=parsed["correctness_reason"],
            review_complete=parsed["review_complete"],
            missing_items=parsed["missing_items"],
        )

        # Step 6: Save to DB
        db_submission = Submission(
            language=data.language,
            user_id=user.id,
            code=data.code,
            pass_status=feedback.pass_status,
            readability_score=feedback.readability_score,
            efficiency_score=feedback.efficiency_score,
            suggestions=", ".join(feedback.suggestions or []),
            errors=", ".join(feedback.errors or []),
            corrected_code=feedback.corrected_code,
            raw_ai_feedback=ai_reply,
            similarity_score=similarity_score,
            is_similar_to_sample=is_similar_to_sample
        )
        db.add(db_submission)
        db.commit()

        return feedback

    except HTTPException:
        db.rollback()
        raise
    except AIServiceError as e:
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        logging.getLogger(__name__).error("Review failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Could not complete or save this review. Please try again.") from e

# Optional: Seed route for a sample answer
@app.post("/add-sample-answer")
def add_sample_answer(data: SampleAnswerCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Check if sample already exists for that question + language
    existing = db.query(SampleAnswer).filter_by(
        question_title=data.question_title.strip().lower(),
        language=data.language.strip().lower()
    ).filter_by(user_id=user.id).first()

    if existing:
        raise HTTPException(status_code=400, detail="Sample answer already exists for this question and language.")

    sample = SampleAnswer(
        question_title=data.question_title.strip().lower(),
        language=data.language.strip().lower(),
        ideal_code=data.ideal_code.strip(),
        user_id=user.id,
    )

    db.add(sample)
    db.commit()

    return {"message": "Sample answer added successfully."}

@app.get("/sample-questions")
def get_sample_questions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    samples = db.query(SampleAnswer).filter(visible_samples(user)).order_by(SampleAnswer.user_id.is_(None), SampleAnswer.id).all()
    # A person's own answer can override a shared built-in without duplicate menu entries.
    samples = list({(s.language, s.question_title): s for s in reversed(samples)}.values())
    return [
        {
            "id": s.id,
            "question_title": s.question_title,
            "language": s.language,
            "description": get_sample_description(s.language, s.question_title),
            "ideal_code": s.ideal_code
        }
        for s in samples
    ]

@app.get("/submission-history", response_model=List[SubmissionRead])
def get_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Submission).filter_by(user_id=user.id).all()
