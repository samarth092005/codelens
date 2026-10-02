from fastapi.testclient import TestClient


def test_create_repository(client: TestClient):
    """Test creating a new repository."""
    payload = {
        "name": "codelens-backend",
        "url": "https://github.com/codelens/backend.git",
        "description": "Backend engine for CodeLens",
        "is_private": False,
        "default_branch": "main",
    }
    response = client.post("/api/v1/repositories", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "codelens-backend"
    assert data["url"] == "https://github.com/codelens/backend.git"
    assert data["description"] == "Backend engine for CodeLens"
    assert data["is_private"] is False
    assert data["default_branch"] == "main"
    assert data["status"] == "pending"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_duplicate_repository_url_fails(client: TestClient):
    """Test creating a repository with an existing URL returns 409 Conflict."""
    payload = {
        "name": "repo-dup",
        "url": "https://github.com/org/unique-repo.git",
    }
    res1 = client.post("/api/v1/repositories", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/repositories", json=payload)
    assert res2.status_code == 409
    assert "already registered" in res2.json()["detail"]


def test_get_repository_by_id(client: TestClient):
    """Test retrieving a repository by its identifier."""
    payload = {
        "name": "lookup-repo",
        "url": "https://github.com/org/lookup-repo.git",
    }
    create_res = client.post("/api/v1/repositories", json=payload)
    assert create_res.status_code == 201
    repo_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/repositories/{repo_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == repo_id
    assert get_res.json()["name"] == "lookup-repo"


def test_get_nonexistent_repository_returns_404(client: TestClient):
    """Test querying a non-existent repository ID returns 404."""
    response = client.get("/api/v1/repositories/999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_repositories(client: TestClient):
    """Test listing repositories with pagination."""
    # Create two repositories
    client.post(
        "/api/v1/repositories",
        json={"name": "repo-alpha", "url": "https://github.com/org/alpha.git"},
    )
    client.post(
        "/api/v1/repositories",
        json={"name": "repo-beta", "url": "https://github.com/org/beta.git"},
    )

    response = client.get("/api/v1/repositories?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    urls = [r["url"] for r in data]
    assert "https://github.com/org/alpha.git" in urls
    assert "https://github.com/org/beta.git" in urls


def test_delete_repository(client: TestClient):
    """Test deleting a repository."""
    create_res = client.post(
        "/api/v1/repositories",
        json={"name": "delete-me", "url": "https://github.com/org/delete-me.git"},
    )
    repo_id = create_res.json()["id"]

    # Delete
    del_res = client.delete(f"/api/v1/repositories/{repo_id}")
    assert del_res.status_code == 204

    # Verify not found
    get_res = client.get(f"/api/v1/repositories/{repo_id}")
    assert get_res.status_code == 404


def test_delete_nonexistent_repository_returns_404(client: TestClient):
    """Test deleting a non-existent repository returns 404."""
    response = client.delete("/api/v1/repositories/999999")
    assert response.status_code == 404


def test_create_user_and_associate_repository(client: TestClient):
    """Test creating a user and associating a repository with that user."""
    # 1. Create User
    user_payload = {
        "email": "developer@codelens.dev",
        "username": "codelens-dev",
        "full_name": "CodeLens Developer",
    }
    user_res = client.post("/api/v1/users", json=user_payload)
    assert user_res.status_code == 201
    user_data = user_res.json()
    user_id = user_data["id"]
    assert user_data["email"] == "developer@codelens.dev"
    assert user_data["username"] == "codelens-dev"

    # 2. Create Repository with owner_id
    repo_payload = {
        "name": "dev-repo",
        "url": "https://github.com/codelens/dev-repo.git",
        "owner_id": user_id,
    }
    repo_res = client.post("/api/v1/repositories", json=repo_payload)
    assert repo_res.status_code == 201
    repo_data = repo_res.json()
    assert repo_data["owner_id"] == user_id


def test_create_repository_with_invalid_owner_fails(client: TestClient):
    """Test creating a repository referencing a non-existent owner returns 404."""
    repo_payload = {
        "name": "orphan-repo",
        "url": "https://github.com/codelens/orphan-repo.git",
        "owner_id": 999999,
    }
    response = client.post("/api/v1/repositories", json=repo_payload)
    assert response.status_code == 404
    assert "User with id 999999 not found" in response.json()["detail"]


def test_create_duplicate_user_fails(client: TestClient):
    """Test creating duplicate user fails with 409."""
    user_payload = {
        "email": "duplicate@codelens.dev",
        "username": "duplicate_user",
    }
    res1 = client.post("/api/v1/users", json=user_payload)
    assert res1.status_code == 201

    # Attempt same email
    res2 = client.post(
        "/api/v1/users",
        json={"email": "duplicate@codelens.dev", "username": "another_user"},
    )
    assert res2.status_code == 409

    # Attempt same username
    res3 = client.post(
        "/api/v1/users",
        json={"email": "another@codelens.dev", "username": "duplicate_user"},
    )
    assert res3.status_code == 409
