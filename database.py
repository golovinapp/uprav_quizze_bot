import asyncpg
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

pool: asyncpg.Pool | None = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=2,
        max_size=10,
    )
    await _create_tables()
    await _seed_defaults()


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None


async def _create_tables():
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id VARCHAR(100) PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            INSERT INTO sessions (session_id, description)
            VALUES ('free', 'Свободное прохождение')
            ON CONFLICT (session_id) DO NOTHING;
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                age_group VARCHAR(20),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                session_id VARCHAR(100) NOT NULL REFERENCES sessions(session_id) ON DELETE SET NULL,
                score_a INT NOT NULL DEFAULT 0,
                score_b INT NOT NULL DEFAULT 0,
                score_c INT NOT NULL DEFAULT 0,
                final_result CHAR(1) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_results_user_session
            ON results (telegram_id, session_id)
            WHERE session_id != 'free';
        """)
        # ─── Quiz content tables ───
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                sort_order INT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                text TEXT NOT NULL,
                answer_a TEXT NOT NULL,
                answer_b TEXT NOT NULL,
                answer_c TEXT NOT NULL
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS result_texts (
                letter CHAR(1) PRIMARY KEY,
                style VARCHAR(100) NOT NULL,
                subtitle VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                risks TEXT NOT NULL,
                advice TEXT NOT NULL
            );
        """)


# ─── Seed default content (only if tables are empty) ─────────

async def _seed_defaults():
    async with pool.acquire() as conn:
        has_questions = await conn.fetchval("SELECT COUNT(*) FROM questions;")
        if has_questions == 0:
            from quiz_defaults import DEFAULT_QUESTIONS, DEFAULT_RESULTS
            for q in DEFAULT_QUESTIONS:
                await conn.execute("""
                    INSERT INTO questions (sort_order, title, text, answer_a, answer_b, answer_c)
                    VALUES ($1, $2, $3, $4, $5, $6);
                """, q["sort_order"], q["title"], q["text"],
                    q["answer_a"], q["answer_b"], q["answer_c"])
            for letter, r in DEFAULT_RESULTS.items():
                await conn.execute("""
                    INSERT INTO result_texts (letter, style, subtitle, description, risks, advice)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (letter) DO NOTHING;
                """, letter, r["style"], r["subtitle"],
                    r["description"], r["risks"], r["advice"])


# --------------- quiz content from DB ---------------

async def get_questions() -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM questions ORDER BY sort_order;")
        return [dict(r) for r in rows]


async def get_result_texts() -> dict[str, dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM result_texts ORDER BY letter;")
        return {r["letter"]: dict(r) for r in rows}


async def update_question(sort_order: int, title: str, text: str,
                          answer_a: str, answer_b: str, answer_c: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE questions
            SET title = $2, text = $3, answer_a = $4, answer_b = $5, answer_c = $6
            WHERE sort_order = $1;
        """, sort_order, title, text, answer_a, answer_b, answer_c)


async def update_result_text(letter: str, style: str, subtitle: str,
                             description: str, risks: str, advice: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE result_texts
            SET style = $2, subtitle = $3, description = $4, risks = $5, advice = $6
            WHERE letter = $1;
        """, letter, style, subtitle, description, risks, advice)


# --------------- user operations ---------------

async def upsert_user(telegram_id: int, age_group: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, age_group)
            VALUES ($1, $2)
            ON CONFLICT (telegram_id) DO UPDATE SET age_group = $2;
        """, telegram_id, age_group)


async def has_session_result(telegram_id: int, session_id: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchval("""
            SELECT 1 FROM results
            WHERE telegram_id = $1 AND session_id = $2
            LIMIT 1;
        """, telegram_id, session_id)
        return row is not None


async def save_result(telegram_id: int, session_id: str, score_a: int,
                      score_b: int, score_c: int, final_result: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO results (telegram_id, session_id, score_a, score_b, score_c, final_result)
            VALUES ($1, $2, $3, $4, $5, $6);
        """, telegram_id, session_id, score_a, score_b, score_c, final_result)


async def delete_user_data(telegram_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE telegram_id = $1;", telegram_id)


async def session_exists(session_id: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT 1 FROM sessions WHERE session_id = $1 LIMIT 1;", session_id
        )
        return row is not None


# --------------- admin / analytics ---------------

async def create_session(session_id: str, description: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO sessions (session_id, description)
            VALUES ($1, $2)
            ON CONFLICT (session_id) DO UPDATE SET description = $2;
        """, session_id, description)


async def list_sessions():
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT s.session_id, s.description, s.created_at,
                   COUNT(r.id) AS total_results
            FROM sessions s
            LEFT JOIN results r ON r.session_id = s.session_id
            GROUP BY s.session_id
            ORDER BY s.created_at DESC;
        """)


async def _get_style_map() -> dict[str, str]:
    """Return {letter: 'Style Name (\u0410/\u0411/\u0412)'} from DB."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT letter, style FROM result_texts;")
        display = {"A": "\u0410", "B": "\u0411", "C": "\u0412"}
        return {r["letter"]: f"{r['style']} ({display.get(r['letter'], r['letter'])})" for r in rows}


async def get_session_stats(session_id: str):
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM results WHERE session_id = $1;", session_id
        )
        distribution = await conn.fetch("""
            SELECT final_result, COUNT(*) AS cnt
            FROM results WHERE session_id = $1
            GROUP BY final_result ORDER BY final_result;
        """, session_id)
        by_age = await conn.fetch("""
            SELECT u.age_group, r.final_result, COUNT(*) AS cnt
            FROM results r
            JOIN users u ON u.telegram_id = r.telegram_id
            WHERE r.session_id = $1
            GROUP BY u.age_group, r.final_result
            ORDER BY u.age_group, r.final_result;
        """, session_id)
        style_map = await _get_style_map()
        return {
            "total": total,
            "distribution": [dict(row) for row in distribution],
            "by_age": [dict(row) for row in by_age],
            "style_map": style_map,
        }


async def get_global_stats():
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM results;")
        distribution = await conn.fetch("""
            SELECT final_result, COUNT(*) AS cnt
            FROM results
            GROUP BY final_result ORDER BY final_result;
        """)
        by_age = await conn.fetch("""
            SELECT u.age_group, r.final_result, COUNT(*) AS cnt
            FROM results r
            JOIN users u ON u.telegram_id = r.telegram_id
            GROUP BY u.age_group, r.final_result
            ORDER BY u.age_group, r.final_result;
        """)
        by_session = await conn.fetch("""
            SELECT r.session_id, s.description, r.final_result, COUNT(*) AS cnt
            FROM results r
            JOIN sessions s ON s.session_id = r.session_id
            GROUP BY r.session_id, s.description, r.final_result
            ORDER BY r.session_id, r.final_result;
        """)
        style_map = await _get_style_map()
        return {
            "total": total,
            "distribution": [dict(row) for row in distribution],
            "by_age": [dict(row) for row in by_age],
            "by_session": [dict(row) for row in by_session],
            "style_map": style_map,
        }


async def delete_session(session_id: str):
    if session_id == "free":
        return False
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM results WHERE session_id = $1;", session_id)
        await conn.execute("DELETE FROM sessions WHERE session_id = $1;", session_id)
        return True
