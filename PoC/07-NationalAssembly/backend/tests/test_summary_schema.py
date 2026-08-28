from pathlib import Path
import unittest


class SummarySchemaTests(unittest.TestCase):
    def test_summary_cache_is_unique_by_content_and_model_contract(self):
        migration = Path(__file__).parents[1] / "migrations" / "0019_transcript_utterance_summaries.sql"
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE transcript_utterance_summaries", sql)
        self.assertIn(
            "UNIQUE (broadcast_id, content_hash, provider, model, prompt_version)", sql,
        )
        self.assertIn("usage_metadata jsonb", sql)

    def test_live_insight_is_stored_with_the_cached_summary(self):
        migration = Path(__file__).parents[1] / "migrations" / "0025_transcript_summary_live_insight.sql"
        sql = migration.read_text(encoding="utf-8")
        repository = (
            Path(__file__).parents[1] / "app" / "db" / "summary_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN live_insight jsonb", sql)
        self.assertIn("Jsonb(item.get(\"live_insight\") or {})", repository)
        self.assertIn("del provider, model, prompt_version", repository)


if __name__ == "__main__":
    unittest.main()
