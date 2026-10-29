import unittest

from server.main import DatabaseConnection


class SqlServerTranslationTests(unittest.TestCase):
    def test_limit_becomes_select_top(self):
        sql = "SELECT id, name FROM travelers ORDER BY name LIMIT 10"
        self.assertEqual(
            DatabaseConnection._sql_server_sql(sql),
            "SELECT TOP 10 id, name FROM travelers ORDER BY name",
        )

    def test_insert_returning_becomes_output(self):
        sql = "INSERT INTO users (id, name) VALUES (%s, %s) RETURNING id, name"
        self.assertEqual(
            DatabaseConnection._sql_server_sql(sql),
            "INSERT INTO users (id, name) OUTPUT inserted.id, inserted.name VALUES (?, ?)",
        )

    def test_update_returning_preserves_aliases(self):
        sql = "UPDATE expenses SET expense_date = %s WHERE id = %s RETURNING expense_date AS date"
        self.assertEqual(
            DatabaseConnection._sql_server_sql(sql),
            "UPDATE expenses SET expense_date = ? OUTPUT inserted.expense_date AS date WHERE id = ?",
        )

    def test_boolean_literals_become_sql_server_bits(self):
        sql = "UPDATE notifications SET is_read = TRUE WHERE is_read = FALSE"
        self.assertEqual(
            DatabaseConnection._sql_server_sql(sql),
            "UPDATE notifications SET is_read = 1 WHERE is_read = 0",
        )


if __name__ == "__main__":
    unittest.main()
