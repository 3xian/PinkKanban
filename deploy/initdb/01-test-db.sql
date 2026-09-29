CREATE DATABASE IF NOT EXISTS kanban_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON kanban.* TO 'kanban'@'%';
GRANT ALL PRIVILEGES ON kanban_test.* TO 'kanban'@'%';
FLUSH PRIVILEGES;
