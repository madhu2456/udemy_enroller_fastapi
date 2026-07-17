"""Tests for the default pytest external-network guard."""

import socket

import pytest


@pytest.mark.parametrize(
    "resolver_name,args",
    [
        ("getaddrinfo", ("example.com", 443)),
        ("gethostbyname", ("example.com",)),
        ("gethostbyname_ex", ("example.com",)),
        ("gethostbyaddr", ("203.0.113.10",)),
        ("getnameinfo", (("203.0.113.10", 443), 0)),
    ],
)
def test_external_dns_is_blocked(resolver_name, args):
    resolver = getattr(socket, resolver_name)
    with pytest.raises(pytest.fail.Exception, match="External network access blocked"):
        resolver(*args)


def test_external_tcp_connect_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(pytest.fail.Exception, match="External network access blocked"):
            client.connect(("203.0.113.10", 443))


def test_external_tcp_connect_ex_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(pytest.fail.Exception, match="External network access blocked"):
            client.connect_ex(("203.0.113.10", 443))


def test_external_udp_send_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(pytest.fail.Exception, match="External network access blocked"):
            client.sendto(b"probe", ("203.0.113.10", 53))


def test_loopback_resolution_is_allowed():
    addresses = socket.getaddrinfo("127.0.0.1", 80)
    assert addresses
    assert all(address[-1][0] == "127.0.0.1" for address in addresses)


def test_ipv4_mapped_loopback_resolution_is_allowed():
    addresses = socket.getaddrinfo("::ffff:127.0.0.1", 80, socket.AF_INET6)
    assert addresses


def test_block_is_not_swallowed_by_application_exception_handlers():
    def application_call():
        try:
            socket.getaddrinfo("example.com", 443)
        except Exception:
            return "swallowed"
        return "allowed"

    with pytest.raises(pytest.fail.Exception, match="External network access blocked"):
        application_call()


def test_socketpair_is_allowed():
    left, right = socket.socketpair()
    try:
        left.sendall(b"ok")
        assert right.recv(2) == b"ok"
    finally:
        left.close()
        right.close()


@pytest.mark.allow_network
def test_allow_network_marker_restores_socket_api():
    assert socket.getaddrinfo.__name__ == "getaddrinfo"
    assert socket.socket.connect.__name__ == "connect"
