"""Project avatar previews are checked against an isolated in-memory database."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Project, ProjectMember, User
from app.services.projects import PROJECT_AVATAR_LIMIT, list_projects


def test_project_previews_are_bounded_ordered_and_scoped_to_membership():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            people = [User(
                email=f"person{i}@example.com", password_hash="unused",
                display_name=f"成员 {i}", avatar_id="pet-1", avatar_color="#D63A56",
            ) for i in range(8)]
            db.add_all(people)
            db.flush()
            projects = [Project(
                name=name, owner_id=people[-1].id, archived=archived, color="#D63A56",
            ) for name, archived in [("多人", False), ("单人", False), ("私有", False), ("归档", True)]]
            db.add_all(projects)
            db.flush()
            for person in people:
                db.add(ProjectMember(
                    project_id=projects[0].id, user_id=person.id,
                    role="owner" if person is people[-1] else "member",
                ))
            for project, person in [(projects[1], people[0]), (projects[2], people[-1]), (projects[3], people[0])]:
                db.add(ProjectMember(project_id=project.id, user_id=person.id, role="owner"))
            db.flush()

            result = {p["name"]: p for p in list_projects(db, people[0], archived=False)}
            assert set(result) == {"多人", "单人"}
            preview = result["多人"]["member_preview"]
            assert result["多人"]["member_count"] == 8
            assert len(preview) == PROJECT_AVATAR_LIMIT == 5
            assert [person["id"] for person in preview] == [people[-1].id] + [p.id for p in people[:4]]
            assert all("email" not in person and "password_hash" not in person for person in preview)
            assert result["单人"]["member_preview"][0]["id"] == people[0].id
            assert len(result["单人"]["member_preview"]) == 1

            people[-1].avatar_id = "robot-2"
            people[-1].display_name = "更新后的头像"
            db.flush()
            updated = next(p for p in list_projects(db, people[0], archived=False) if p["name"] == "多人")
            assert updated["member_preview"][0]["avatar_id"] == "robot-2"
            assert updated["member_preview"][0]["display_name"] == "更新后的头像"
            archived = list_projects(db, people[0], archived=True)
            assert [p["name"] for p in archived] == ["归档"]
            assert archived[0]["member_preview"][0]["id"] == people[0].id
    finally:
        engine.dispose()
