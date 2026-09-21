from fastapi import APIRouter, Request

from templating import templates

# Create a router object
# This behaves like a mini FastAPI app
router = APIRouter()


@router.get("/")
@router.get("/home")
def home(request: Request):
    """
    Home page route.
    - Registered at both "/" (the assignment's required path) and "/home"
      (an alias) - both render the same page.
    - Checks if a user is logged in using the session
    - Passes user info to the template, which shows a Login link when
      logged out, or a Dashboard + Logout link when logged in
    """
    user = request.session.get("user")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user
        }
    )
