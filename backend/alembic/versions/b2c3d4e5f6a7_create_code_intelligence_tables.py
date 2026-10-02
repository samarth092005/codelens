"""create code intelligence tables

Revision ID: b2c3d4e5f6a7
Revises: 4e722ff6e3f7
Create Date: 2026-10-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '4e722ff6e3f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. repository_versions table
    op.create_table(
        'repository_versions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('commit_sha', sa.String(length=40), nullable=False),
        sa.Column('branch_name', sa.String(length=255), nullable=False),
        sa.Column('commit_message', sa.Text(), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_repository_versions_id'), 'repository_versions', ['id'], unique=False)
    op.create_index(op.f('ix_repository_versions_repository_id'), 'repository_versions', ['repository_id'], unique=False)
    op.create_index(op.f('ix_repository_versions_commit_sha'), 'repository_versions', ['commit_sha'], unique=False)

    # 2. files table
    op.create_table(
        'files',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('repository_version_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=1000), nullable=False),
        sa.Column('extension', sa.String(length=50), nullable=False),
        sa.Column('language', sa.String(length=50), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('parsing_status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['repository_version_id'], ['repository_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_files_id'), 'files', ['id'], unique=False)
    op.create_index(op.f('ix_files_repository_version_id'), 'files', ['repository_version_id'], unique=False)
    op.create_index(op.f('ix_files_path'), 'files', ['path'], unique=False)
    op.create_index(op.f('ix_files_language'), 'files', ['language'], unique=False)
    op.create_index(op.f('ix_files_parsing_status'), 'files', ['parsing_status'], unique=False)

    # 3. symbols table
    op.create_table(
        'symbols',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('qualified_name', sa.String(length=512), nullable=False),
        sa.Column('symbol_type', sa.String(length=50), nullable=False),
        sa.Column('parent_symbol_id', sa.Integer(), nullable=True),
        sa.Column('line_start', sa.Integer(), nullable=False),
        sa.Column('line_end', sa.Integer(), nullable=False),
        sa.Column('visibility', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_symbol_id'], ['symbols.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_symbols_id'), 'symbols', ['id'], unique=False)
    op.create_index(op.f('ix_symbols_file_id'), 'symbols', ['file_id'], unique=False)
    op.create_index(op.f('ix_symbols_name'), 'symbols', ['name'], unique=False)
    op.create_index(op.f('ix_symbols_qualified_name'), 'symbols', ['qualified_name'], unique=False)
    op.create_index(op.f('ix_symbols_symbol_type'), 'symbols', ['symbol_type'], unique=False)
    op.create_index(op.f('ix_symbols_parent_symbol_id'), 'symbols', ['parent_symbol_id'], unique=False)

    # 4. dependencies table
    op.create_table(
        'dependencies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('repository_version_id', sa.Integer(), nullable=False),
        sa.Column('relationship_type', sa.String(length=50), nullable=False),
        sa.Column('source_file_id', sa.Integer(), nullable=True),
        sa.Column('target_file_id', sa.Integer(), nullable=True),
        sa.Column('caller_symbol_id', sa.Integer(), nullable=True),
        sa.Column('callee_symbol_id', sa.Integer(), nullable=True),
        sa.Column('callee_name', sa.String(length=255), nullable=True),
        sa.Column('imported_module', sa.String(length=512), nullable=True),
        sa.Column('import_type', sa.String(length=50), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('resolution_status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['repository_version_id'], ['repository_versions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_file_id'], ['files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['caller_symbol_id'], ['symbols.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['callee_symbol_id'], ['symbols.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dependencies_id'), 'dependencies', ['id'], unique=False)
    op.create_index(op.f('ix_dependencies_repository_version_id'), 'dependencies', ['repository_version_id'], unique=False)
    op.create_index(op.f('ix_dependencies_relationship_type'), 'dependencies', ['relationship_type'], unique=False)
    op.create_index(op.f('ix_dependencies_source_file_id'), 'dependencies', ['source_file_id'], unique=False)
    op.create_index(op.f('ix_dependencies_target_file_id'), 'dependencies', ['target_file_id'], unique=False)
    op.create_index(op.f('ix_dependencies_caller_symbol_id'), 'dependencies', ['caller_symbol_id'], unique=False)
    op.create_index(op.f('ix_dependencies_callee_symbol_id'), 'dependencies', ['callee_symbol_id'], unique=False)
    op.create_index(op.f('ix_dependencies_resolution_status'), 'dependencies', ['resolution_status'], unique=False)

    # 5. analysis_jobs table
    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('repository_version_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['repository_version_id'], ['repository_versions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_analysis_jobs_id'), 'analysis_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_analysis_jobs_repository_id'), 'analysis_jobs', ['repository_id'], unique=False)
    op.create_index(op.f('ix_analysis_jobs_repository_version_id'), 'analysis_jobs', ['repository_version_id'], unique=False)
    op.create_index(op.f('ix_analysis_jobs_status'), 'analysis_jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_analysis_jobs_status'), table_name='analysis_jobs')
    op.drop_index(op.f('ix_analysis_jobs_repository_version_id'), table_name='analysis_jobs')
    op.drop_index(op.f('ix_analysis_jobs_repository_id'), table_name='analysis_jobs')
    op.drop_index(op.f('ix_analysis_jobs_id'), table_name='analysis_jobs')
    op.drop_table('analysis_jobs')

    op.drop_index(op.f('ix_dependencies_resolution_status'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_callee_symbol_id'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_caller_symbol_id'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_target_file_id'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_source_file_id'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_relationship_type'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_repository_version_id'), table_name='dependencies')
    op.drop_index(op.f('ix_dependencies_id'), table_name='dependencies')
    op.drop_table('dependencies')

    op.drop_index(op.f('ix_symbols_parent_symbol_id'), table_name='symbols')
    op.drop_index(op.f('ix_symbols_symbol_type'), table_name='symbols')
    op.drop_index(op.f('ix_symbols_qualified_name'), table_name='symbols')
    op.drop_index(op.f('ix_symbols_name'), table_name='symbols')
    op.drop_index(op.f('ix_symbols_file_id'), table_name='symbols')
    op.drop_index(op.f('ix_symbols_id'), table_name='symbols')
    op.drop_table('symbols')

    op.drop_index(op.f('ix_files_parsing_status'), table_name='files')
    op.drop_index(op.f('ix_files_language'), table_name='files')
    op.drop_index(op.f('ix_files_path'), table_name='files')
    op.drop_index(op.f('ix_files_repository_version_id'), table_name='files')
    op.drop_index(op.f('ix_files_id'), table_name='files')
    op.drop_table('files')

    op.drop_index(op.f('ix_repository_versions_commit_sha'), table_name='repository_versions')
    op.drop_index(op.f('ix_repository_versions_repository_id'), table_name='repository_versions')
    op.drop_index(op.f('ix_repository_versions_id'), table_name='repository_versions')
    op.drop_table('repository_versions')
