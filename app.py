from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mainGraph as MG
from mainGraph import (JobData, extract_mail_id, create_mail,
                       update_mail, send_mail, human_review, route_after_review)
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import os

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change_this_in_production_xyz987")
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

CLIENT_SECRETS = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# ── Graph wiring ──────────────────────────────────────────────────────────────
#
#   find_email → gen_body_sub → human_review ──(True)──→ send_mail
#                                    ↑                         
#                               update_mail ←─(False)──┘
#
APPLYGRAPH = StateGraph(JobData)
APPLYGRAPH.add_node("find_email",   extract_mail_id)
APPLYGRAPH.add_node("gen_body_sub", create_mail)
APPLYGRAPH.add_node("human_review", human_review)   # interrupt lives here
APPLYGRAPH.add_node("update_mail",  update_mail)
APPLYGRAPH.add_node("send_mail",    send_mail)

APPLYGRAPH.add_edge(START,          "find_email")
APPLYGRAPH.add_edge("find_email",   "gen_body_sub")
APPLYGRAPH.add_edge("gen_body_sub", "human_review")  # always go to review first
APPLYGRAPH.add_edge("update_mail",  "human_review")  # after update, review again

APPLYGRAPH.add_conditional_edges(
    "human_review",
    route_after_review,
    {"send_mail": "send_mail", "update_mail": "update_mail"},
)
APPLYGRAPH.add_edge("send_mail", END)

WORKFLOW     = None
CHECKPOINTER = None
CONFIG       = {"configurable": {"thread_id": "1"}}


def get_state_values():
    """Read body/subject/email from checkpointer after graph pauses."""
    snapshot = WORKFLOW.get_state(CONFIG)
    v = snapshot.values
    return {
        "body":    v.get("body", ""),
        "subject": v.get("subject", ""),
        "email":   v.get("email", ""),
    }


# ── Auth ──────────────────────────────────────────────────────────────────────
def make_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS, scopes=SCOPES,
        redirect_uri=url_for("oauth_callback", _external=True),
    )

def creds_from_session():
    t = session.get("token")
    if not t:
        return None
    return Credentials(
        token=t["token"], refresh_token=t.get("refresh_token"),
        token_uri=t["token_uri"], client_id=t["client_id"],
        client_secret=t["client_secret"], scopes=t["scopes"],
    )

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "token" not in session:
            return jsonify({"error": "not_logged_in"}), 401
        return f(*args, **kwargs)
    return wrapper


# ── OAuth routes ──────────────────────────────────────────────────────────────
@app.route("/login")
def login():
    flow = make_flow()
    auth_url, state = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true")
    session["oauth_state"]   = state
    session["code_verifier"] = flow.code_verifier
    return redirect(auth_url)

@app.route("/oauth/callback")
def oauth_callback():
    flow = make_flow()
    if session.get("code_verifier"):
        flow.code_verifier = session["code_verifier"]
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session["token"] = {
        "token": creds.token, "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri, "client_id": creds.client_id,
        "client_secret": creds.client_secret, "scopes": list(creds.scopes),
    }
    svc  = build("oauth2", "v2", credentials=creds)
    info = svc.userinfo().get().execute()
    session["user_email"] = info.get("email", "")
    session["user_name"]  = info.get("name", "")
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/me")
def me():
    if "user_email" not in session:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "email": session["user_email"], "name": session["user_name"]})


# ── App routes ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/getData", methods=["POST"])
@login_required
def getData():
    global WORKFLOW, CHECKPOINTER
    CHECKPOINTER = InMemorySaver()
    WORKFLOW     = APPLYGRAPH.compile(checkpointer=CHECKPOINTER)

    # Graph runs: find_email → gen_body_sub → human_review (pauses here)
    WORKFLOW.invoke(
        {"user_info": request.form["user_info"], "post_data": request.form["post_data"]},
        config=CONFIG,
    )
    # Graph is now paused at human_review interrupt — read state from checkpointer
    return jsonify(get_state_values()), 200


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    """User gave feedback — resume with False (= update), inject feedback."""
    feedback = request.form.get("feedback", "")
    WORKFLOW.invoke(
        Command(resume=False, update={"feedback": [feedback]}),
        config=CONFIG,
    )
    # Graph ran: update_mail → human_review (pauses again)
    return jsonify(get_state_values()), 200


@app.route("/send", methods=["POST"])
@login_required
def send():
    global WORKFLOW, CHECKPOINTER

    # Set gmail service at module level (not serializable, can't go in state)
    creds            = creds_from_session()
    MG.GMAIL_SERVICE = build("gmail", "v1", credentials=creds)
    MG.SENDER_EMAIL  = session["user_email"]

    file       = request.files.get("attachment")
    file_bytes = file.read()   if file else None
    file_name  = file.filename if file else None

    # Resume with True (= send) + attach file
    WORKFLOW.invoke(
        Command(resume=True, update={"file_bytes": file_bytes, "file_name": file_name}),
        config=CONFIG,
    )

    MG.GMAIL_SERVICE = None
    MG.SENDER_EMAIL  = ""
    WORKFLOW         = None
    CHECKPOINTER     = None
    return "Email delivered ✅"


if __name__ == "__main__":
    app.run(debug=True, port=5050)