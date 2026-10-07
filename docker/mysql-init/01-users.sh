#!/bin/bash
# Runs once, as root, when the MySQL data volume is first created.
# The app user gets DML only; schema changes go through a separate migrate user.
set -euo pipefail
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS '${MYSQL_APP_USER}'@'%' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_APP_USER}'@'%';
CREATE USER IF NOT EXISTS '${MYSQL_MIGRATE_USER}'@'%' IDENTIFIED BY '${MYSQL_MIGRATE_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_MIGRATE_USER}'@'%';
FLUSH PRIVILEGES;
SQL
