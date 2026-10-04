import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class GitRepositoryError(Exception):
    """Raised when a repository path is not a valid Git repository."""
    pass


@dataclass(frozen=True)
class GitMetadata:
    commit_sha: str
    branch_name: str
    commit_message: str | None


@dataclass(frozen=True)
class GitCommitInfo:
    commit_hash: str
    parent_hash: str | None
    author_name: str
    author_email: str
    committed_at: datetime
    commit_message: str


@dataclass(frozen=True)
class GitDiffFile:
    file_path: str
    old_path: str | None
    change_type: str  # ADDED, MODIFIED, DELETED, RENAMED
    additions: int
    deletions: int

    @property
    def path(self) -> str:
        return self.file_path

    @property
    def insertions(self) -> int:
        return self.additions


class GitService:
    """Service to safely extract Git metadata and history without executing repository code."""

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

    def get_commit_history(
        self, repo_path: Path | str, max_commits: int | None = None
    ) -> list[GitCommitInfo]:
        """Extract full chronological commit history using git log."""
        p = Path(repo_path).resolve()
        if not self.is_git_repository(p):
            raise GitRepositoryError(f"Directory is not a valid Git repository: {p}")

        try:
            # Output format: %H (hash) \0 %P (parent hashes) \0 %an (author name) \0 %ae (author email) \0 %aI (iso date) \0 %B (message) \x01
            cmd = ["git", "log", "--reverse"]
            if max_commits is not None:
                cmd.extend(["-n", str(max_commits)])
            cmd.append("--format=%H%x00%P%x00%an%x00%ae%x00%aI%x00%B%x01")

            res = subprocess.run(
                cmd,
                cwd=str(p),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
                shell=False,
            )
            raw_output = res.stdout
            if not raw_output.strip():
                return []

            commits: list[GitCommitInfo] = []
            entries = raw_output.split("\x01")
            for entry in entries:
                entry = entry.strip("\r\n")
                if not entry:
                    continue
                parts = entry.split("\x00")
                if len(parts) < 6:
                    continue

                commit_hash = parts[0].strip()
                parents_str = parts[1].strip()
                parent_hash = parents_str.split()[0] if parents_str else None
                author_name = parts[2].strip()
                author_email = parts[3].strip()
                date_str = parts[4].strip()
                commit_message = parts[5].strip()

                try:
                    committed_at = datetime.fromisoformat(date_str)
                except Exception:
                    committed_at = datetime.now(timezone.utc)

                commits.append(
                    GitCommitInfo(
                        commit_hash=commit_hash,
                        parent_hash=parent_hash,
                        author_name=author_name,
                        author_email=author_email,
                        committed_at=committed_at,
                        commit_message=commit_message,
                    )
                )

            return commits
        except subprocess.CalledProcessError as e:
            raise GitRepositoryError(f"Git log failed: {e.stderr.strip()}") from e
        except Exception as e:
            raise GitRepositoryError(f"Failed to extract commit history: {e}") from e

    def get_commit_diff_files(
        self,
        repo_path: Path | str,
        commit_hash: str,
        parent_hash: str | None = None,
    ) -> list[GitDiffFile]:
        """Extract files changed in a commit with change types and additions/deletions statistics."""
        p = Path(repo_path).resolve()
        if not self.is_git_repository(p):
            raise GitRepositoryError(f"Directory is not a valid Git repository: {p}")

        try:
            # 1. Get name-status
            if parent_hash:
                diff_cmd = ["git", "diff-tree", "--no-commit-id", "--name-status", "-M", "-r", commit_hash]
                numstat_cmd = ["git", "diff-tree", "--no-commit-id", "--numstat", "-M", "-r", commit_hash]
            else:
                diff_cmd = ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "--root", commit_hash]
                numstat_cmd = ["git", "diff-tree", "--no-commit-id", "--numstat", "-r", "--root", commit_hash]

            status_res = subprocess.run(
                diff_cmd,
                cwd=str(p),
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
                shell=False,
            )

            # Map: file_path -> (change_type, old_path)
            status_map: dict[str, tuple[str, str | None]] = {}
            for line in status_res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                status_code = parts[0]
                if status_code.startswith("R") and len(parts) >= 3:
                    old_path = PurePosixPath(parts[1]).as_posix()
                    new_path = PurePosixPath(parts[2]).as_posix()
                    status_map[new_path] = ("RENAMED", old_path)
                elif status_code.startswith("A") and len(parts) >= 2:
                    path = PurePosixPath(parts[1]).as_posix()
                    status_map[path] = ("ADDED", None)
                elif status_code.startswith("D") and len(parts) >= 2:
                    path = PurePosixPath(parts[1]).as_posix()
                    status_map[path] = ("DELETED", None)
                elif status_code.startswith("M") and len(parts) >= 2:
                    path = PurePosixPath(parts[1]).as_posix()
                    status_map[path] = ("MODIFIED", None)
                elif len(parts) >= 2:
                    path = PurePosixPath(parts[1]).as_posix()
                    status_map[path] = ("MODIFIED", None)

            # 2. Get numstat for additions and deletions
            numstat_res = subprocess.run(
                numstat_cmd,
                cwd=str(p),
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
                shell=False,
            )

            stats_map: dict[str, tuple[int, int]] = {}
            for line in numstat_res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                adds_str, dels_str, path_str = parts[0], parts[1], parts[2]
                try:
                    adds = int(adds_str)
                except ValueError:
                    adds = 0
                try:
                    dels = int(dels_str)
                except ValueError:
                    dels = 0

                # In renames, path_str might be "{old => new}" or "old => new"
                if " => " in path_str:
                    # Clean up rename path syntax
                    cleaned = path_str
                    if "{" in cleaned and "}" in cleaned:
                        prefix = cleaned[:cleaned.find("{")]
                        suffix = cleaned[cleaned.find("}") + 1:]
                        middle = cleaned[cleaned.find("{") + 1:cleaned.find("}")]
                        new_mid = middle.split(" => ")[1]
                        final_path = PurePosixPath(prefix + new_mid + suffix).as_posix()
                    else:
                        final_path = PurePosixPath(cleaned.split(" => ")[1]).as_posix()
                    stats_map[final_path] = (adds, dels)
                else:
                    norm_path = PurePosixPath(path_str).as_posix()
                    stats_map[norm_path] = (adds, dels)

            diff_files: list[GitDiffFile] = []
            for path, (change_type, old_path) in sorted(status_map.items()):
                adds, dels = stats_map.get(path, (0, 0))
                diff_files.append(
                    GitDiffFile(
                        file_path=path,
                        old_path=old_path,
                        change_type=change_type,
                        additions=adds,
                        deletions=dels,
                    )
                )

            return diff_files
        except subprocess.CalledProcessError as e:
            raise GitRepositoryError(f"Git diff failed: {e.stderr.strip()}") from e
        except Exception as e:
            raise GitRepositoryError(f"Failed to get commit diff: {e}") from e

    def get_file_content_at_commit(
        self,
        repo_path: Path | str,
        commit_hash: str,
        relative_path: str,
    ) -> bytes | None:
        """Safely fetch file content at a specific commit using git show."""
        p = Path(repo_path).resolve()
        if not self.is_git_repository(p):
            raise GitRepositoryError(f"Directory is not a valid Git repository: {p}")

        posix_rel_path = PurePosixPath(relative_path).as_posix()
        try:
            res = subprocess.run(
                ["git", "show", f"{commit_hash}:{posix_rel_path}"],
                cwd=str(p),
                capture_output=True,
                check=True,
                timeout=10,
                shell=False,
            )
            return res.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None


git_service = GitService()
