import socket

import serve


def test_is_port_in_use_detects_listening_service():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()

        assert serve._is_port_in_use("127.0.0.1", listener.getsockname()[1]) is True


def test_is_port_in_use_allows_unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    assert serve._is_port_in_use("127.0.0.1", port) is False
