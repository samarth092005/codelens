import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitRepositoryError(Exception):
    """Raised when a repository path is not a valid Git repository."""
    pass


@dataclass(frozen=True)
class GitMetadata:
    commit_sha: str
    branch_name: str
    commit_message: str | None


class GitService:
    """Service to safely extract Git metadata without executing repository code."""

    def is_git_repository(self, repo_path: Path | str) -> bool:
        """Check if path contains a valid .git directory or file."""
        p = Path(repo_path).resolve()
        if not p.is_dir():
            return False
        git_dir = p / ".git"
        return git_dir.exists()

    def extract_metadata(self, repo_path: Path | str) -> GitMetadata:
        """Extract commit SHA, branch name, and commit message safely using git CLI.
        
        Security guarantees:
        - shell=False
        - Fixed arguments only
        - No execution of repository hooks or code
        """
        p = Path(repo_path).resolve()
        if not self.is_git_repository(p):
            raise GitRepositoryError(f"Directory is not a valid Git repository: {p}")

        try:
            # 1. Commit SHA
            sha_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(p),
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
                shell=False,
            )
            commit_sha = sha_res.stdout.strip()
            if not commit_sha:
                raise GitRepositoryError("Could not retrieve commit SHA from Git repository")

            # 2. Branch name
            branch_res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(p),
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                shell=False,
            )
            branch_name = branch_res.stdout.strip()
            if not branch_name or branch_name == "HEAD":
                branch_name = "main"

            # 3. Commit message
            msg_res = subprocess.run(
                ["git", "log", "-1", "--format=%B"],
                cwd=str(p),
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                shell=False,
            )
            commit_message = msg_res.stdout.strip() or None

            return GitMetadata(
                commit_sha=commit_sha,
                branch_name=branch_name,
                commit_message=commit_message,
            )
        except subprocess.TimeoutExpired as e:
            raise GitRepositoryError(f"Git command timed out: {e}") from e
        except subprocess.CalledProcessError as e:
            raise GitRepositoryError(f"Git command failed: {e.stderr.strip()}") from e
        except FileNotFoundError as e:
            raise GitRepositoryError("Git executable not found in system PATH") from e


git_service = GitService()
