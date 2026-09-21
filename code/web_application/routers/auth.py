import os
import secrets
import time

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_302_FOUND

from templating import templates

# Create a router object
# This behaves like a mini FastAPI app
router = APIRouter()

# Hardcoded credentials for demo purposes only
# In real applications, credentials come from a database
VALID_USERNAME = "admin"
VALID_PASSWORD = "password"

# How long a session may sit idle before it's treated as expired.
SESSION_IDLE_TIMEOUT_SECONDS = int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", "900"))

# Starlette's session cookie is a *signed* blob with no server-side record -
# on its own, logging out (or an idle timeout) can only tell the CURRENT
# response to clear the cookie; a copy of the old cookie value taken before
# that would still verify and work, since its signature never changes. This
# table is the actual source of truth for "is this session still valid",
# keyed by a random session id ("sid") carried inside the signed cookie -
# so a replayed pre-logout/pre-timeout cookie can be positively rejected,
# not just "hopefully" cleared client-side.
_active_sessions: dict[str, float] = {}


def is_session_active(request: Request) -> bool:
    """True if the session's sid is still registered server-side and not idle.

    Also implements the idle timeout: touches the sid's last-activity entry
    to extend a valid session, or revokes an idle one so it can't be reused.
    """
    sid = request.session.get("sid")
    last_activity = _active_sessions.get(sid) if sid else None
    if sid is None or last_activity is None:
        return False
    if time.time() - last_activity > SESSION_IDLE_TIMEOUT_SECONDS:
        _active_sessions.pop(sid, None)
        request.session.clear()
        return False
    _active_sessions[sid] = time.time()
    return True


@router.get("/login")
def login_page(request: Request):
    """
    Displays the login form.
    If the user is already logged in,
    the template can choose what to display.
    """
    user = request.session.get("user")
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "user": user,
            # Set on the redirect back here after a failed attempt so the template can show a Bootstrap alert.
            "error": request.query_params.get("error"),
        }
    )


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Handles login form submission.
    - Reads username and password from the form
    - Validates credentials
    - Stores user info in session if valid
    """
    if username == VALID_USERNAME and password == VALID_PASSWORD:
        # A fresh sid is the server-side handle for this login (see
        # _active_sessions above) - it's what actually gets checked/revoked
        # on logout or idle timeout, not just the presence of "user" in the
        # signed cookie (which alone can't be revoked once issued).
        sid = secrets.token_urlsafe(32)
        _active_sessions[sid] = time.time()
        request.session.clear()
        request.session["sid"] = sid
        # Store logged-in user in session
        request.session["user"] = username
        # Redirect user to dashboard
        return RedirectResponse(
            url="/dashboard",
            status_code=HTTP_302_FOUND
        )

    # If credentials are invalid, redirect back to the login page with an
    # error flag so it can show a Bootstrap alert.
    return RedirectResponse(
        url="/login?error=1",
        status_code=HTTP_302_FOUND
    )


@router.get("/dashboard")
def dashboard(request: Request):
    """
    Protected route.
    - Only accessible if user is logged in and the session hasn't gone idle
    - Redirects to login page if the session is missing, idle-expired, or
      was logged out (even if a stale cookie is replayed - see
      is_session_active above)
    """
    user = request.session.get("user")
    # If user is not logged in (or the session idled out / was revoked), block access
    if not user or not is_session_active(request):
        return RedirectResponse(
            url="/login",
            status_code=HTTP_302_FOUND
        )

    # If user is logged in, render dashboard
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user
        }
    )


@router.get("/logout")
def logout(request: Request):
    """
    Logs the user out.
    - Revokes the session server-side (so a copied cookie can't be replayed)
    - Clears all session data
    - Redirects back to home page
    """
    sid = request.session.get("sid")
    if sid:
        _active_sessions.pop(sid, None)
    request.session.clear()
    return RedirectResponse(
        url="/",
        status_code=HTTP_302_FOUND
    )
