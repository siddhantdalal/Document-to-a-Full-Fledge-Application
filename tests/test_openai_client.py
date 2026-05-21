from unittest.mock import MagicMock, patch

from packages.ai_providers.base import CompletionRequest, Message
from packages.ai_providers.openai_client import DEFAULT_MODEL, OpenAIClient


def _mocked_response(text: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=text))]
    response.model_dump.return_value = {"id": "resp_test"}
    return response


def test_complete_prepends_system_message_and_forwards_user_messages():
    with patch("packages.ai_providers.openai_client.OpenAI") as ctor:
        sdk = MagicMock()
        ctor.return_value = sdk
        sdk.chat.completions.create.return_value = _mocked_response("hello")

        client = OpenAIClient(api_key="sk-test")
        result = client.complete(
            CompletionRequest(
                system="you are helpful",
                messages=[Message(role="user", content="hi")],
                temperature=0.5,
                max_tokens=128,
            )
        )

        assert result.content == "hello"
        ctor.assert_called_once_with(api_key="sk-test")
        kwargs = sdk.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == DEFAULT_MODEL
        assert kwargs["messages"] == [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
        ]
        assert kwargs["temperature"] == 0.5
        assert kwargs["max_tokens"] == 128


def test_complete_uses_request_model_when_provided():
    with patch("packages.ai_providers.openai_client.OpenAI") as ctor:
        sdk = MagicMock()
        ctor.return_value = sdk
        sdk.chat.completions.create.return_value = _mocked_response("ok")

        client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
        client.complete(CompletionRequest(messages=[Message(role="user", content="x")]))

        assert sdk.chat.completions.create.call_args.kwargs["model"] == "gpt-4o-mini"


def test_complete_handles_null_content():
    with patch("packages.ai_providers.openai_client.OpenAI") as ctor:
        sdk = MagicMock()
        ctor.return_value = sdk
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content=None))]
        response.model_dump.return_value = {}
        sdk.chat.completions.create.return_value = response

        client = OpenAIClient(api_key="sk-test")
        result = client.complete(CompletionRequest(messages=[Message(role="user", content="x")]))
        assert result.content == ""


def test_validate_key_false_on_authentication_error():
    from openai import AuthenticationError

    with patch("packages.ai_providers.openai_client.OpenAI") as ctor:
        sdk = MagicMock()
        ctor.return_value = sdk
        sdk.chat.completions.create.side_effect = AuthenticationError(
            message="bad key",
            response=MagicMock(status_code=401),
            body={"error": "Invalid API key"},
        )

        client = OpenAIClient(api_key="bad")
        assert client.validate_key() is False


def test_validate_key_true_on_success():
    with patch("packages.ai_providers.openai_client.OpenAI") as ctor:
        sdk = MagicMock()
        ctor.return_value = sdk
        sdk.chat.completions.create.return_value = _mocked_response("ok")

        client = OpenAIClient(api_key="sk-good")
        assert client.validate_key() is True
