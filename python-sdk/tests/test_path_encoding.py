from bottube.client import BoTTubeClient


def test_stream_url_encodes_video_id_path_segment():
    client = BoTTubeClient(base_url="https://example.test")
    assert client.get_video_stream_url("vid#frag") == "https://example.test/api/videos/vid%23frag/stream"
    assert client.get_video_stream_url("alice/bob") == "https://example.test/api/videos/alice%2Fbob/stream"


def test_path_param_encodes_reserved_chars():
    assert BoTTubeClient._path_param("a/b?# c") == "a%2Fb%3F%23%20c"
