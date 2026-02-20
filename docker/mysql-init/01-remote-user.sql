-- Allow lng_user to connect from any host (e.g. Adminer, web app in another container)
-- Runs only on first MySQL init (empty data volume). For existing DB, run the same SQL manually (see AUTH_SETUP.md).
CREATE USER IF NOT EXISTS 'lng_user'@'%' IDENTIFIED BY 'lng-graphrag-password';
GRANT ALL PRIVILEGES ON lng_graphrag_auth.* TO 'lng_user'@'%';
FLUSH PRIVILEGES;
