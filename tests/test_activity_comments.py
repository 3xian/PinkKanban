"""Activity comment bodies use current records, in isolated SQLite."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, User, Project, ProjectMember, BoardColumn, Card, Activity
from app.services.cards import add_comment, update_comment, delete_comment
from app.services.projects import activity_list


def test_activity_tracks_comment_creation_edit_and_deletion():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(email='activity@example.com', password_hash='unused', display_name='成员', avatar_color='#D63A56')
            db.add(user)
            db.flush()
            project = Project(name='项目', owner_id=user.id, color='#D63A56')
            db.add(project)
            db.flush()
            db.add(ProjectMember(project_id=project.id, user_id=user.id, role='owner'))
            column = BoardColumn(project_id=project.id, name='待办', color='#D63A56', position=0)
            db.add(column)
            db.flush()
            card = Card(project_id=project.id, column_id=column.id, title='任务', created_by=user.id)
            db.add(card)
            db.commit()
            comment = add_comment(db, card.id, user, '第一行\n<script>只是文字</script>')
            db.commit()
            item = activity_list(db, project.id, user)['items'][0]
            assert item['detail']['comment_id'] == comment.id
            assert item['detail']['body'] == comment.body
            update_comment(db, comment.id, user, '更新后的正文')
            db.commit()
            assert activity_list(db, project.id, user)['items'][0]['detail']['body'] == '更新后的正文'
            delete_comment(db, comment.id, user)
            db.commit()
            detail = activity_list(db, project.id, user)['items'][0]['detail']
            assert detail['body'] is None
            assert detail['comment_status'] == 'deleted'
            activity = db.scalar(select(Activity).where(Activity.action == 'comment.added'))
            activity.detail = '{"title":"历史任务"}'
            db.commit()
            assert activity_list(db, project.id, user)['items'][0]['detail']['comment_status'] == 'unavailable'
    finally:
        engine.dispose()
