from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional
import operator
from langgraph.types import interrupt, Command
from dotenv import load_dotenv
load_dotenv()

import base64, mimetypes, os
from email.message import EmailMessage

def get_model():
    load_dotenv(override=True)
    return ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.5,
        api_key=os.getenv("GROQ_API_KEY"),
    )

# Gmail service lives here — NOT in state (not serializable)
GMAIL_SERVICE = None
SENDER_EMAIL  = ""


class JobData(BaseModel):
    user_info:    str = Field(default="I am a developer interested in AI roles")
    subject:      str = Field(default="")
    body:         str = Field(default="")
    email:        str = Field(default="")
    post_data:    str = Field(default="")
    feedback:     Annotated[List[str], operator.add] = Field(default=[])
    file_bytes:   Optional[bytes] = None
    file_name:    Optional[str]   = None
    send_approved: bool = Field(default=False)


# ── Nodes ─────────────────────────────────────────────────────────────────────

def extract_mail_id(state: JobData):
    MODEL = get_model()
    prompt = PromptTemplate(
        template=(
            "From the text below, extract ONLY the email address where the candidate "
            "has to apply. Return ONLY the email address, nothing else.\n\nPost:\n{post_data}"
        )
    )
    email = (prompt | MODEL | StrOutputParser()).invoke({"post_data": state.post_data})
    return {"email": email.strip()}


def create_mail(state: JobData):
    MODEL = get_model()
    prompt = PromptTemplate(
        template=(
            "You are an expert email writer for job applications.\n"
            "Write a short (<=100 words), professional application email.\n\n"
            "Rules:\n"
            "- No placeholders.\n"
            "- No contact details after the candidate name.\n"
            "- Mention the resume is attached.\n"
            "- Output ONLY valid JSON, nothing else.\n\n"
            "User Info:\n{user_information}\n\n"
            "Job Post:\n{post_data}\n\n"
            'Return exactly: {{"subject": "...", "body": "..."}}'
        )
    )
    resp = (prompt | MODEL | JsonOutputParser()).invoke(
        {"user_information": state.user_info, "post_data": state.post_data}
    )
    return {"body": resp["body"], "subject": resp["subject"]}


def human_review(state: JobData):
    """
    Pauses the graph here. 
    Resume value: True = send,  False = apply feedback and update.
    """
    decision = interrupt("Waiting for user: send or update?")
    return {"send_approved": bool(decision)}


def route_after_review(state: JobData) -> str:
    return "send_mail" if state.send_approved else "update_mail"


def update_mail(state: JobData):
    MODEL = get_model()
    prompt = PromptTemplate(
        template=(
            "Improve the email below based ONLY on the feedback.\n\n"
            "Feedback:\n{feedback}\n\n"
            "Subject:\n{subject}\n\nBody:\n{body}\n\n"
            'Return ONLY JSON: {{"subject": "...", "body": "..."}}'
        )
    )
    resp = (prompt | MODEL | JsonOutputParser()).invoke(
        {"feedback": state.feedback[-1], "subject": state.subject, "body": state.body}
    )
    return {"subject": resp["subject"], "body": resp["body"]}


def send_mail(state: JobData):
    if GMAIL_SERVICE is None:
        raise RuntimeError("GMAIL_SERVICE not set — is the user logged in?")

    msg = EmailMessage()
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = state.email
    msg["Subject"] = state.subject
    msg.set_content(state.body)

    if state.file_bytes and state.file_name:
        mime_type, _ = mimetypes.guess_type(state.file_name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        msg.add_attachment(
            state.file_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=state.file_name,
        )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    GMAIL_SERVICE.users().messages().send(userId="me", body={"raw": raw}).execute()
    print("Email delivered via Gmail API ✅")
    return {}