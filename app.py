import datetime
import csv
import io
import os
import sqlite3
import urllib.parse
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from google import genai


app = Flask(__name__)
DATABASE = Path(__file__).with_name("jarvis_history.db")


def get_database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at)"
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(conversations)").fetchall()
        }
        if "session_id" not in columns:
            connection.execute("ALTER TABLE conversations ADD COLUMN session_id TEXT")
            connection.execute(
                "UPDATE conversations SET session_id = 'legacy-' || id WHERE session_id IS NULL"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id)"
        )


def save_conversation(session_id, user_text, assistant_text):
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with get_database() as connection:
        connection.execute(
            "INSERT INTO conversations (session_id, user_text, assistant_text, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_text, assistant_text, timestamp),
        )


def recent_conversation_context(session_id, limit=8):
    with get_database() as connection:
        rows = connection.execute(
            """
            SELECT user_text, assistant_text
            FROM conversations
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    context_lines = []
    for row in reversed(rows):
        context_lines.append(f"User: {row['user_text']}")
        context_lines.append(f"Nova: {row['assistant_text']}")
    return "\n".join(context_lines)


initialize_database()


def ask_gemini(question, session_id):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Your Gemini API key is not configured."

    conversation_context = recent_conversation_context(session_id)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                "You are Nova, a friendly voice assistant. "
                "Answer accurately in natural spoken language. "
                "Keep most answers below 100 words. Do not use markdown. "
                "Use the recent conversation when it helps, but never invent missing context.\n\n"
                f"Recent conversation:\n{conversation_context or 'No previous conversation.'}\n\n"
                f"User: {question}"
            ),
        )
        return response.text.strip() if response.text else "I could not generate an answer."
    except Exception as error:
        print(f"Gemini error: {error}")
        return "I could not contact Gemini right now."


def handle_command(command, session_id):
    text = command.lower().strip()

    if not text:
        return {"answer": "I did not hear a command."}

    if text in {"stop", "exit", "quit", "goodbye", "stop nova", "stop jarvis"}:
        return {"answer": "Goodbye. Have a great day!", "stop": True}

    sites = {
        "open google": "https://www.google.com",
        "open youtube": "https://www.youtube.com",
        "open github": "https://github.com",
        "open gmail": "https://mail.google.com",
    }
    for phrase, url in sites.items():
        if phrase in text:
            return {"answer": phrase.replace("open", "Opening") + ".", "open_url": url}

    if text.startswith("search for ") or text.startswith("search "):
        query = text.removeprefix("search for ").removeprefix("search ").strip()
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        return {"answer": f"Searching Google for {query}.", "open_url": url}

    if text.startswith("play "):
        query = text.removeprefix("play ").strip()
        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(query)
        )
        return {"answer": f"Searching YouTube for {query}.", "open_url": url}

    if "what time" in text or text == "time":
        now = datetime.datetime.now().strftime("%I:%M %p")
        return {"answer": f"The time is {now}."}

    if "what date" in text or "today's date" in text or text == "date":
        today = datetime.datetime.now().strftime("%A, %d %B %Y")
        return {"answer": f"Today is {today}."}

    if "who are you" in text:
        return {"answer": "I am Nova, your Python virtual assistant."}

    return {"answer": ask_gemini(text, session_id)}


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/ask")
def ask():
    data = request.get_json(silent=True) or {}
    command = str(data.get("command", "")).strip()
    session_id = str(data.get("session_id", "")).strip() or str(uuid.uuid4())
    result = handle_command(command, session_id)
    if command and result.get("answer"):
        save_conversation(session_id, command, result["answer"])
    result["session_id"] = session_id
    return jsonify(result)


@app.get("/history")
def history():
    with get_database() as connection:
        rows = connection.execute(
            """
            SELECT
                c.session_id,
                MIN(c.created_at) AS created_at,
                MAX(c.created_at) AS updated_at,
                COUNT(*) AS message_count,
                (
                    SELECT first_message.user_text
                    FROM conversations AS first_message
                    WHERE first_message.session_id = c.session_id
                    ORDER BY first_message.id ASC
                    LIMIT 1
                ) AS title
            FROM conversations AS c
            GROUP BY c.session_id
            ORDER BY MAX(c.id) DESC
            """
        ).fetchall()

    return jsonify([dict(row) for row in rows])


@app.get("/history/<session_id>")
def conversation_history(session_id):
    with get_database() as connection:
        rows = connection.execute(
            """
            SELECT id, user_text, assistant_text, created_at
            FROM conversations
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.delete("/history")
def clear_history():
    with get_database() as connection:
        connection.execute("DELETE FROM conversations")
    return jsonify({"ok": True})


@app.get("/history/export")
def export_history():
    with get_database() as connection:
        rows = connection.execute(
            """
            SELECT created_at, user_text, assistant_text
            FROM conversations
            ORDER BY id ASC
            """
        ).fetchall()

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Date", "You", "Nova"])
    for row in rows:
        writer.writerow([row["created_at"], row["user_text"], row["assistant_text"]])

    filename = f"nova-history-{datetime.date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health():
    return jsonify({"ok": True, "api_key": bool(os.getenv("GEMINI_API_KEY"))})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
