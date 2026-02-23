"""Web dashboard — aiohttp + jinja2."""

import logging
from aiohttp import web
import aiohttp_jinja2
import jinja2

import database as db
from config import ADMIN_SECRET, BOT_USERNAME, WEB_HOST, WEB_PORT

logger = logging.getLogger(__name__)


# ─── Middleware: auth check ───────────────────────────────────

def check_auth(request: web.Request) -> bool:
    return request.cookies.get("auth") == ADMIN_SECRET


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path in ("/login", "/static"):
        return await handler(request)
    if not check_auth(request):
        raise web.HTTPFound("/login")
    return await handler(request)


# ─── Routes ───────────────────────────────────────────────────

async def login_page(request: web.Request):
    error = request.query.get("error", "")
    return aiohttp_jinja2.render_template("login.html", request, {"error": error})


async def login_post(request: web.Request):
    data = await request.post()
    secret = data.get("secret", "")
    if secret == ADMIN_SECRET:
        resp = web.HTTPFound("/")
        resp.set_cookie("auth", ADMIN_SECRET, max_age=86400 * 7, httponly=True)
        return resp
    raise web.HTTPFound("/login?error=1")


async def logout(request: web.Request):
    resp = web.HTTPFound("/login")
    resp.del_cookie("auth")
    return resp


async def dashboard(request: web.Request):
    sessions = await db.list_sessions()
    return aiohttp_jinja2.render_template("dashboard.html", request, {
        "sessions": sessions,
        "bot_username": BOT_USERNAME,
    })


async def global_stats_page(request: web.Request):
    stats = await db.get_global_stats()
    return aiohttp_jinja2.render_template("global_stats.html", request, {
        "stats": stats,
    })


async def global_stats_json(request: web.Request):
    stats = await db.get_global_stats()
    return web.json_response(stats)


async def session_detail(request: web.Request):
    session_id = request.match_info["session_id"]
    stats = await db.get_session_stats(session_id)
    sessions_list = await db.list_sessions()
    desc = ""
    for s in sessions_list:
        if s["session_id"] == session_id:
            desc = s["description"]
            break
    return aiohttp_jinja2.render_template("session_detail.html", request, {
        "session_id": session_id,
        "description": desc,
        "stats": stats,
        "bot_username": BOT_USERNAME,
    })


async def session_stats_json(request: web.Request):
    session_id = request.match_info["session_id"]
    stats = await db.get_session_stats(session_id)
    return web.json_response(stats)


async def create_session_post(request: web.Request):
    data = await request.post()
    session_id = data.get("session_id", "").strip().lower().replace(" ", "_")
    description = data.get("description", "").strip()
    if session_id and session_id != "free":
        await db.create_session(session_id, description)
    raise web.HTTPFound("/")


async def delete_session_post(request: web.Request):
    session_id = request.match_info["session_id"]
    await db.delete_session(session_id)
    raise web.HTTPFound("/")


# ─── Quiz editor ─────────────────────────────────────────────

async def editor_page(request: web.Request):
    questions = await db.get_questions()
    result_texts = await db.get_result_texts()
    saved = request.query.get("saved", "")
    return aiohttp_jinja2.render_template("editor.html", request, {
        "questions": questions,
        "result_texts": result_texts,
        "saved": saved,
    })


async def save_question_post(request: web.Request):
    data = await request.post()
    sort_order = int(data.get("sort_order", 0))
    title = data.get("title", "").strip()
    text = data.get("text", "").strip()
    answer_a = data.get("answer_a", "").strip()
    answer_b = data.get("answer_b", "").strip()
    answer_c = data.get("answer_c", "").strip()
    if sort_order and title and text:
        await db.update_question(sort_order, title, text, answer_a, answer_b, answer_c)
    raise web.HTTPFound("/editor?saved=question")


async def save_result_text_post(request: web.Request):
    data = await request.post()
    letter = data.get("letter", "").strip().upper()
    style = data.get("style", "").strip()
    subtitle = data.get("subtitle", "").strip()
    description = data.get("description", "").strip()
    risks = data.get("risks", "").strip()
    advice = data.get("advice", "").strip()
    if letter in ("A", "B", "C") and style:
        await db.update_result_text(letter, style, subtitle, description, risks, advice)
    raise web.HTTPFound("/editor?saved=result")


# ─── App factory ──────────────────────────────────────────────

def create_web_app() -> web.Application:
    import pathlib
    base = pathlib.Path(__file__).parent

    app = web.Application(middlewares=[auth_middleware])
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(str(base / "templates")))

    app.router.add_get("/login", login_page)
    app.router.add_post("/login", login_post)
    app.router.add_get("/logout", logout)
    app.router.add_get("/", dashboard)
    app.router.add_get("/global", global_stats_page)
    app.router.add_get("/api/global/stats", global_stats_json)
    app.router.add_post("/session/create", create_session_post)
    app.router.add_get("/session/{session_id}", session_detail)
    app.router.add_get("/api/session/{session_id}/stats", session_stats_json)
    app.router.add_post("/session/{session_id}/delete", delete_session_post)
    app.router.add_get("/editor", editor_page)
    app.router.add_post("/editor/question", save_question_post)
    app.router.add_post("/editor/result", save_result_text_post)
    app.router.add_static("/static", str(base / "static"))

    return app
