ROLES = ("owner", "admin", "member", "viewer")
ASSIGNABLE_ROLES = ("admin", "member", "viewer")
ROLE_RANK = {"viewer": 1, "member": 2, "admin": 3, "owner": 4}
PRIORITIES = ("none", "low", "medium", "high", "urgent")
COLORS = (
    "#D63A56",
    "#C47B2B",
    "#5C6B52",
    "#3D6B8A",
    "#7A5EA8",
    "#C46B4A",
    "#2F6F6A",
    "#8A4B5A",
)
DEFAULT_COLUMNS = ("待办", "进行中", "已完成")
DEFAULT_LABELS = (
    ("重要", "#D63A56"),
    ("设计", "#7A5EA8"),
    ("开发", "#3D6B8A"),
    ("阻塞", "#C47B2B"),
)
ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".zip",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_LABELS = 30
MAX_CHECKLISTS = 20
MAX_CHECKLIST_ITEMS = 100
MAX_COMMENTS = 1000
MAX_COLUMNS = 40
MAX_CARDS = 4000
SESSION_COOKIE = "kb_session"
SESSION_DAYS = 14
