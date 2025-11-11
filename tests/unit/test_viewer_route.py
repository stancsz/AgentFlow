from pathlib import Path

from agentflow.viewer.server import create_app


def test_viewer_index_returns_200(tmp_path):
    # Use the repository's sandbox directory which includes example artifact files
    repo_root = Path(__file__).resolve().parents[3]
    sandbox_dir = repo_root / "sandbox"

    app = create_app(sandbox_dir)
    client = app.test_client()

    resp = client.get("/")
    assert resp.status_code == 200
