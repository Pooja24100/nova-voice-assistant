import csv
import io

import app as nova_app


def make_test_client(tmp_path, monkeypatch):
    test_database = tmp_path / "test_history.db"
    monkeypatch.setattr(nova_app, "DATABASE", test_database)
    nova_app.initialize_database()
    nova_app.app.config.update(TESTING=True)
    return nova_app.app.test_client()


def test_health_reports_api_key_status(tmp_path, monkeypatch):
    client = make_test_client(tmp_path, monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "api_key": False}


def test_builtin_command_is_saved_to_history(tmp_path, monkeypatch):
    client = make_test_client(tmp_path, monkeypatch)

    response = client.post(
        "/ask",
        json={"command": "open google", "session_id": "session-1"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["answer"] == "Opening google."
    assert payload["open_url"] == "https://www.google.com"

    history_response = client.get("/history/session-1")
    history = history_response.get_json()

    assert len(history) == 1
    assert history[0]["user_text"] == "open google"
    assert history[0]["assistant_text"] == "Opening google."


def test_history_export_returns_csv(tmp_path, monkeypatch):
    client = make_test_client(tmp_path, monkeypatch)
    client.post("/ask", json={"command": "what date", "session_id": "session-2"})

    response = client.get("/history/export")
    csv_rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert csv_rows[0] == ["Date", "You", "Nova"]
    assert csv_rows[1][1] == "what date"


def test_clear_history_deletes_all_rows(tmp_path, monkeypatch):
    client = make_test_client(tmp_path, monkeypatch)
    client.post("/ask", json={"command": "time", "session_id": "session-3"})

    response = client.delete("/history")
    history_response = client.get("/history")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert history_response.get_json() == []
