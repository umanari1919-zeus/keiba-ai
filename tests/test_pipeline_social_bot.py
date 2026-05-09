import pytest
import json
import os


@pytest.mark.unit
class TestSocialBotDeadLetter:
    def test_dead_letter_written_on_x_failure(self, tmp_path, monkeypatch):
        import pipeline.social_bot_27 as sb
        import types
        dl_path = str(tmp_path / "sns_dead_letter.jsonl")
        monkeypatch.setattr(sb, "DEAD_LETTER_FILE", dl_path)

        fake_tweepy = types.ModuleType("tweepy")
        class FakeClient:
            def __init__(self, **kw): pass
            def create_tweet(self, text=""):
                raise RuntimeError("API error")
        fake_tweepy.Client = FakeClient
        monkeypatch.setitem(__import__("sys").modules, "tweepy", fake_tweepy)

        monkeypatch.setenv("X_API_KEY", "fake")
        monkeypatch.setenv("X_API_SECRET", "fake")
        monkeypatch.setenv("X_ACCESS_TOKEN", "fake")
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "fake")

        result = sb.post_to_x("test message")
        assert result is False
        assert os.path.exists(dl_path)
        with open(dl_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["channel"] == "X"
        assert entry["message"] == "test message"
        assert "error" in entry
        assert "timestamp" in entry

    def test_dead_letter_written_on_discord_failure(self, tmp_path, monkeypatch):
        import pipeline.social_bot_27 as sb
        dl_path = str(tmp_path / "sns_dead_letter.jsonl")
        monkeypatch.setattr(sb, "DEAD_LETTER_FILE", dl_path)
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://invalid.example.com/webhook")

        result = sb.post_to_discord("test discord msg")
        assert result is False
        assert os.path.exists(dl_path)

    def test_no_dead_letter_on_missing_env(self, tmp_path, monkeypatch):
        import pipeline.social_bot_27 as sb
        dl_path = str(tmp_path / "sns_dead_letter.jsonl")
        monkeypatch.setattr(sb, "DEAD_LETTER_FILE", dl_path)
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

        result = sb.post_to_discord("test")
        assert result is False
        assert not os.path.exists(dl_path)

    def test_generate_post_text_no_picks(self, monkeypatch):
        import pipeline.social_bot_27 as sb
        monkeypatch.setattr(os, "listdir", lambda p: [])
        text = sb.generate_post_text()
        assert "うまなり地蔵AI" in text
        assert len(text) <= 270
