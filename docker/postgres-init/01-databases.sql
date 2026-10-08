-- Runs once, when the compose Postgres volume is first initialised.
--
-- The test suite drops every table after each test, so it must never share a
-- database with development data. This gives it its own, on the same server.
-- conftest.py refuses any database whose name does not end in "_test".
CREATE DATABASE marigold_test OWNER marigold;

-- scripts/eval_rag.py writes its documents and cards here, never to the dev
-- database. It refuses any database whose name does not end in "_eval".
CREATE DATABASE marigold_eval OWNER marigold;
