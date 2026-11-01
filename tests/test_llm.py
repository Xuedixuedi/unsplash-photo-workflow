import io

import httpx
import respx
from PIL import Image

from upw.adapters.llm import LlmClient, choose_place, parse_json_object, shrink_image, suggest_tags
from upw.errors import UpwError


def test_parse_json_object() -> None:
    assert parse_json_object('```json\n{"tags": ["lake"]}\n```')["tags"] == ["lake"]
    try:
        parse_json_object("nope")
    except UpwError:
        return
    raise AssertionError("expected json error")


def test_shrink_image() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (2000, 1000), "blue").save(buffer, format="JPEG")
    small = shrink_image(buffer.getvalue())
    with Image.open(io.BytesIO(small)) as image:
        assert max(image.size) <= 512


@respx.mock
def test_cache_and_place_choice(tmp_path) -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"place": "Pearl Shoals"}'}}]},
        )
    )
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(image, format="JPEG")
    raw = image.getvalue()
    client = LlmClient(
        api_key="secret-llm-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        cache_path=tmp_path / "llm.json",
    )
    try:
        assert choose_place(client, photo_id="p1", names=["Five Flower Lake", "Pearl Shoals"], image=raw) == "Pearl Shoals"
        assert choose_place(client, photo_id="p1", names=["Five Flower Lake", "Pearl Shoals"], image=raw) == "Pearl Shoals"
        assert route.call_count == 1
        sent = route.calls[0].request
        assert "secret-llm-key" not in sent.content.decode()
        assert sent.headers["authorization"] == "Bearer secret-llm-key"
        assert choose_place(client, photo_id="p1", names=["Other"], image=raw) is None
        assert choose_place(client, photo_id="p1", names=["Pearl Shoals"], image=None) is None
    finally:
        client.close()


@respx.mock
def test_suggest_tags_and_http_error(tmp_path) -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json={"choices": [{"message": {"content": '{"tags": ["Turquoise Water", "#nope"]}'}}]}),
            httpx.Response(500, text="down"),
        ]
    )
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(image, format="JPEG")
    client = LlmClient(
        api_key="secret-llm-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        cache_path=tmp_path / "llm.json",
    )
    try:
        tags = suggest_tags(client, photo_id="p2", existing=["lake"], need=2, image=image.getvalue())
        assert tags == ["Turquoise Water", "#nope"]
        try:
            client.complete_json(photo_id="p9", purpose="x", prompt="different", image=None)
        except UpwError as exc:
            assert "500" in str(exc)
        else:
            raise AssertionError("expected llm error")
    finally:
        client.close()
