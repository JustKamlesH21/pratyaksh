-- The app user creates tables and the Audit Trail triggers on first start.
GRANT TRIGGER ON pratyaksh.* TO 'pratyaksh'@'%';
FLUSH PRIVILEGES;
