"""add remaining tables (chat, billing, feedback, tender_notice, audit_log, sys_dict_item)

These tables were previously created by SQLAlchemy create_all() in main.py.
This migration formalizes them for production deployment tracking.

Revision ID: d1e2f3a4b5c6
Revises: b5c6d7e8f9a0
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers
revision = 'd1e2f3a4b5c6'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chat_session
    op.create_table('chat_session',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('bid_project_id', sa.Integer(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default='false'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index('ix_chat_session_tenant', 'chat_session', ['tenant_id'], if_not_exists=True)

    # chat_message
    op.create_table('chat_message',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('chat_session.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tool_call_id', sa.String(100), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=True),
        sa.Column('tool_calls', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )

    # user_quota
    op.create_table('user_quota',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('max_projects', sa.Integer(), server_default='5'),
        sa.Column('max_exports', sa.Integer(), server_default='10'),
        sa.Column('max_ai_calls', sa.Integer(), server_default='100'),
        sa.Column('used_projects', sa.Integer(), server_default='0'),
        sa.Column('used_exports', sa.Integer(), server_default='0'),
        sa.Column('used_ai_calls', sa.Integer(), server_default='0'),
        sa.Column('plan_type', sa.String(20), server_default='free'),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index('ix_user_quota_user', 'user_quota', ['user_id'], if_not_exists=True)

    # usage_log
    op.create_table('usage_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index('ix_usage_log_user', 'usage_log', ['user_id'], if_not_exists=True)

    # feedback_log
    op.create_table('feedback_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('bid_project.id'), nullable=False),
        sa.Column('chapter_no', sa.String(20), nullable=False),
        sa.Column('chapter_title', sa.String(200), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('modified_text', sa.Text(), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('diff_ratio', sa.Float(), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index('ix_feedback_project_action', 'feedback_log', ['project_id', 'action'], if_not_exists=True)
    op.create_index('ix_feedback_tenant', 'feedback_log', ['tenant_id'], if_not_exists=True)

    # tender_notice
    op.create_table('tender_notice',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('enterprise_id', sa.Integer(), sa.ForeignKey('enterprise.id'), nullable=True),
        sa.Column('source', sa.String(50), server_default='manual'),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('source_id', sa.String(200), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('buyer_name', sa.String(200), nullable=True),
        sa.Column('buyer_region', sa.String(100), nullable=True),
        sa.Column('customer_type', sa.String(20), nullable=True),
        sa.Column('tender_type', sa.String(20), nullable=True),
        sa.Column('budget_amount', sa.Float(), nullable=True),
        sa.Column('deadline', sa.String(30), nullable=True),
        sa.Column('publish_date', sa.String(30), nullable=True),
        sa.Column('delivery_scope', sa.Text(), nullable=True),
        sa.Column('content_summary', sa.Text(), nullable=True),
        sa.Column('match_score', sa.Float(), nullable=True),
        sa.Column('match_level', sa.String(20), nullable=True),
        sa.Column('match_analysis', sa.Text(), nullable=True),
        sa.Column('capability_gaps', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='new'),
        sa.Column('converted_project_id', sa.Integer(), sa.ForeignKey('bid_project.id'), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index('ix_tender_notice_tenant_status', 'tender_notice', ['tenant_id', 'status'], if_not_exists=True)
    op.create_index('ix_tender_notice_source_id', 'tender_notice', ['source_id'], if_not_exists=True)

    # audit_log
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )

    # sys_dict_item
    op.create_table('sys_dict_item',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dict_type', sa.String(50), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('value', sa.String(200), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('remark', sa.String(500), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table('sys_dict_item', if_exists=True)
    op.drop_table('audit_log', if_exists=True)
    op.drop_table('tender_notice', if_exists=True)
    op.drop_table('feedback_log', if_exists=True)
    op.drop_table('usage_log', if_exists=True)
    op.drop_table('user_quota', if_exists=True)
    op.drop_table('chat_message', if_exists=True)
    op.drop_table('chat_session', if_exists=True)
