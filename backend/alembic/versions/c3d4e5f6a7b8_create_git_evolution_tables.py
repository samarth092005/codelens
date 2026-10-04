"""create git evolution tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. git_commits table
    op.create_table(
        'git_commits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('repository_version_id', sa.Integer(), nullable=True),
        sa.Column('commit_hash', sa.String(length=40), nullable=False),
        sa.Column('parent_hash', sa.String(length=40), nullable=True),
        sa.Column('author_name', sa.String(length=255), nullable=False),
        sa.Column('author_email', sa.String(length=255), nullable=False),
        sa.Column('commit_message', sa.Text(), nullable=True),
        sa.Column('committed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['repository_version_id'], ['repository_versions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_git_commits_id'), 'git_commits', ['id'], unique=False)
    op.create_index(op.f('ix_git_commits_repository_id'), 'git_commits', ['repository_id'], unique=False)
    op.create_index(op.f('ix_git_commits_repository_version_id'), 'git_commits', ['repository_version_id'], unique=False)
    op.create_index(op.f('ix_git_commits_commit_hash'), 'git_commits', ['commit_hash'], unique=False)
    op.create_index(op.f('ix_git_commits_parent_hash'), 'git_commits', ['parent_hash'], unique=False)
    op.create_index(op.f('ix_git_commits_committed_at'), 'git_commits', ['committed_at'], unique=False)

    # 2. commit_file_changes table
    op.create_table(
        'commit_file_changes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('commit_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('old_path', sa.String(length=1000), nullable=True),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('additions', sa.Integer(), nullable=False, default=0),
        sa.Column('deletions', sa.Integer(), nullable=False, default=0),
        sa.ForeignKeyConstraint(['commit_id'], ['git_commits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_commit_file_changes_id'), 'commit_file_changes', ['id'], unique=False)
    op.create_index(op.f('ix_commit_file_changes_commit_id'), 'commit_file_changes', ['commit_id'], unique=False)
    op.create_index(op.f('ix_commit_file_changes_file_id'), 'commit_file_changes', ['file_id'], unique=False)
    op.create_index(op.f('ix_commit_file_changes_file_path'), 'commit_file_changes', ['file_path'], unique=False)
    op.create_index(op.f('ix_commit_file_changes_change_type'), 'commit_file_changes', ['change_type'], unique=False)

    # 3. commit_symbol_changes table
    op.create_table(
        'commit_symbol_changes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('file_change_id', sa.Integer(), nullable=False),
        sa.Column('symbol_id', sa.Integer(), nullable=True),
        sa.Column('symbol_name', sa.String(length=255), nullable=False),
        sa.Column('qualified_name', sa.String(length=512), nullable=False),
        sa.Column('symbol_type', sa.String(length=50), nullable=False),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('old_line_start', sa.Integer(), nullable=True),
        sa.Column('old_line_end', sa.Integer(), nullable=True),
        sa.Column('new_line_start', sa.Integer(), nullable=True),
        sa.Column('new_line_end', sa.Integer(), nullable=True),
        sa.Column('changed_lines_count', sa.Integer(), nullable=False, default=0),
        sa.ForeignKeyConstraint(['file_change_id'], ['commit_file_changes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['symbol_id'], ['symbols.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_commit_symbol_changes_id'), 'commit_symbol_changes', ['id'], unique=False)
    op.create_index(op.f('ix_commit_symbol_changes_file_change_id'), 'commit_symbol_changes', ['file_change_id'], unique=False)
    op.create_index(op.f('ix_commit_symbol_changes_symbol_id'), 'commit_symbol_changes', ['symbol_id'], unique=False)
    op.create_index(op.f('ix_commit_symbol_changes_symbol_name'), 'commit_symbol_changes', ['symbol_name'], unique=False)
    op.create_index(op.f('ix_commit_symbol_changes_qualified_name'), 'commit_symbol_changes', ['qualified_name'], unique=False)
    op.create_index(op.f('ix_commit_symbol_changes_change_type'), 'commit_symbol_changes', ['change_type'], unique=False)


def downgrade() -> None:
    op.drop_table('commit_symbol_changes')
    op.drop_table('commit_file_changes')
    op.drop_table('git_commits')
