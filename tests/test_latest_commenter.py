"""Latest commenter summaries use an isolated in-memory database."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import Base, BoardColumn, Card, Comment, Project, ProjectMember, User
from app.serialize import user_brief
from app.services.board import board_dict
from app.services.cards import card_detail, delete_comment, update_comment


@pytest.fixture()
def comment_board():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            owner = User(email="owner@example.com", password_hash="unused", display_name="Owner", avatar_color="#D63A56", avatar_id="robot-6")
            author = User(email="author@example.com", password_hash="unused", display_name="Author", avatar_color="#D63A56", avatar_id="pet-1")
            db.add_all([owner, author])
            db.flush()
            project = Project(name="Comments", owner_id=owner.id, color="#D63A56")
            db.add(project)
            db.flush()
            membership = ProjectMember(project_id=project.id, user_id=author.id, role="member")
            db.add_all([ProjectMember(project_id=project.id, user_id=owner.id, role="owner"), membership])
            column = BoardColumn(project_id=project.id, name="Todo", color="#D63A56", position=0)
            db.add(column)
            db.flush()
            card = Card(project_id=project.id, column_id=column.id, title="Commented", created_by=owner.id)
            empty = Card(project_id=project.id, column_id=column.id, title="Empty", created_by=owner.id)
            db.add_all([card, empty])
            db.commit()
            yield db, owner, author, project, column, card, empty, membership
    finally:
        engine.dispose()


def assert_summary(db, owner, project, card, expected_user, count):
    board = board_dict(db, project.id, owner)
    brief = next(item for column in board["columns"] for item in column["cards"] if item["id"] == card.id)
    detail = card_detail(db, card.id, owner)
    expected = user_brief(expected_user) if expected_user is not None else None
    for summary in (brief, detail["card"]):
        assert "latest_commenter" in summary
        assert summary["latest_commenter"] == expected
        assert summary["comment_count"] == count
        if expected is not None:
            assert set(summary["latest_commenter"]) == {"id", "display_name", "avatar_color", "avatar_id"}
    assert len(detail["comments"]) == count


def test_latest_commenter_order_edit_departure_and_deletion(comment_board):
    db, owner, author, project, _column, card, empty, membership = comment_board
    assert_summary(db, owner, project, card, None, 0)
    assert_summary(db, owner, project, empty, None, 0)

    latest_time = datetime(2020, 1, 2, 12)
    first = Comment(card_id=card.id, user_id=author.id, body="First", created_at=latest_time, updated_at=latest_time)
    db.add(first)
    db.commit()
    assert_summary(db, owner, project, card, author, 1)

    older_time = datetime(2020, 1, 1, 12)
    older = Comment(card_id=card.id, user_id=owner.id, body="Higher id, older creation", created_at=older_time, updated_at=older_time)
    db.add(older)
    db.commit()
    assert older.id > first.id
    assert_summary(db, owner, project, card, author, 2)

    tied = Comment(card_id=card.id, user_id=owner.id, body="Same creation, higher id", created_at=latest_time, updated_at=latest_time)
    db.add(tied)
    db.commit()
    assert tied.id > first.id
    assert_summary(db, owner, project, card, owner, 3)

    update_comment(db, first.id, author, "Edited most recently")
    db.commit()
    assert first.updated_at > tied.updated_at
    assert_summary(db, owner, project, card, owner, 3)

    db.delete(membership)
    db.commit()
    delete_comment(db, tied.id, owner)
    db.commit()
    assert_summary(db, owner, project, card, author, 2)
    assert all(member["id"] != author.id for member in board_dict(db, project.id, owner)["members"])

    delete_comment(db, first.id, owner)
    db.commit()
    assert_summary(db, owner, project, card, owner, 1)
    delete_comment(db, older.id, owner)
    db.commit()
    assert_summary(db, owner, project, card, None, 0)
    assert_summary(db, owner, project, empty, None, 0)


def test_board_comment_summary_query_is_bulk_without_bodies(comment_board):
    db, owner, author, project, column, card, _empty, _membership = comment_board
    created_at = datetime(2020, 1, 1, 12)
    db.add(Comment(card_id=card.id, user_id=author.id, body="Original", created_at=created_at, updated_at=created_at))
    db.commit()
    statements = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", record_statement)
    try:
        board_dict(db, project.id, owner)
        baseline_count = len(statements)
        for position in range(12):
            extra = Card(project_id=project.id, column_id=column.id, title=f"Extra {position}", created_by=owner.id, position=position + 1)
            db.add(extra)
            db.flush()
            db.add(Comment(card_id=extra.id, user_id=author.id, body="Not needed in a board summary", created_at=created_at, updated_at=created_at))
        db.commit()
        statements.clear()
        board = board_dict(db, project.id, owner)
        assert len(statements) == baseline_count
        comment_queries = [statement for statement in statements if "FROM comments" in statement]
        assert len(comment_queries) == 1
        assert "comments.body" not in comment_queries[0]
        commented = [item for group in board["columns"] for item in group["cards"] if item["comment_count"]]
        assert len(commented) == 13
        assert all(item["comment_count"] == 1 and item["latest_commenter"] == user_brief(author) for item in commented)
    finally:
        event.remove(db.bind, "before_cursor_execute", record_statement)
