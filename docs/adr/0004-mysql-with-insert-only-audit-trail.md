# MySQL, with an insert-only Audit Trail

We store Calls, Possession Codes, Device Inbox messages and the Audit Trail in MySQL rather than MongoDB. Banks expect transactional writes and an audit record that cannot be edited, and the team already knows MySQL; JSON columns give us the schema flexibility we wanted from MongoDB for per-Signal details. The Audit Trail table has no update path in code, and schema setup adds database triggers that reject UPDATE and DELETE on it. Tests run the same SQLAlchemy models on SQLite.
