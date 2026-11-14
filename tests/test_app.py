from protean import config


def test_openapi_describes_the_app_and_docs_pages_are_off(client) -> None:
    info = client.get("/openapi.json").json()["info"]
    assert info["title"] == "Protean"
    assert info["version"] == config.VERSION
    assert info["description"] == config.DESCRIPTION
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
