from __future__ import annotations

import pytest

from coredis import BaseConnection
from coredis.exceptions import InvalidResponse
from coredis.parser import Parser


class DummyConnection(BaseConnection):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)

    def data_received(self, data):
        self._parser.feed(data)

    async def _connect(self) -> None:
        pass


@pytest.fixture
def connection(request):
    return DummyConnection(decode_responses=request.getfixturevalue("decode"))


@pytest.fixture
def parser(connection):
    parser = Parser()
    parser.on_connect(connection)
    return parser


@pytest.mark.parametrize(
    "decode",
    [
        True,
        False,
    ],
)
class TestPyParser:
    def encoded_value(self, decode: bool, value: bytes):
        if decode:
            return value.decode("latin-1")
        return value

    def test_none(self, parser, decode):
        parser.feed(b"_\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is None
        )

    def test_simple_string(self, parser, decode):
        parser.feed(b"+PONG\r\n")
        assert parser.get_response(
            decode=decode,
            encoding="latin-1",
        ) == self.encoded_value(decode, b"PONG")

    def test_nil_bulk_string(self, parser, decode):
        parser.feed(b"$-1\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is None
        )

    def test_bulk_string(self, parser, decode):
        parser.feed(b"$5\r\nhello\r\n")
        assert parser.get_response(
            decode=decode,
            encoding="latin-1",
        ) == self.encoded_value(decode, b"hello")

    def test_bulk_string_forced_raw(self, parser, decode):
        parser.feed(b"$5\r\nhello\r\n")
        assert parser.get_response(decode=False, encoding="latin-1") == b"hello"

    def test_nil_verbatim_text(self, parser, decode):
        parser.feed(b"=-1\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is None
        )

    def test_verbatim_text(self, parser, decode):
        parser.feed(b"=9\r\ntxt:hello\r\n")
        assert parser.get_response(
            decode=decode,
            encoding="latin-1",
        ) == self.encoded_value(decode, b"hello")

    def test_unknown_verbatim_text_type(self, parser, decode):
        parser.feed(b"=9\r\nrst:hello\r\n")
        with pytest.raises(
            InvalidResponse, match="Unexpected verbatim string of type b'rst'"
        ):
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )

    def test_bool(self, parser, decode):
        parser.feed(b"#f\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is False
        )
        parser.feed(b"#t\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is True
        )

    def test_int(self, parser, decode):
        parser.feed(b":1\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == 1
        )
        parser.feed(b":2\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == 2
        )

    def test_double(self, parser, decode):
        parser.feed(b",3.142\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == 3.142
        )

    def test_bignumber(self, parser, decode):
        parser.feed(b"(3.142\r\n")
        with pytest.raises(InvalidResponse):
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )

    def test_nil_array(self, parser, decode):
        parser.feed(b"*-1\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is None
        )

    def test_empty_array(self, parser, decode):
        parser.feed(b"*0\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == []
        )

    def test_int_array(self, parser, decode):
        parser.feed(b"*2\r\n:1\r\n:2\r\n")
        assert parser.get_response(
            decode=decode,
            encoding="latin-1",
        ) == [1, 2]

    def test_string_array(self, parser, decode):
        parser.feed(b"*2\r\n$2\r\nco\r\n$5\r\nredis\r\n")
        assert parser.get_response(decode=decode, encoding="latin-1",) == [
            self.encoded_value(decode, b"co"),
            self.encoded_value(decode, b"redis"),
        ]

    def test_mixed_array(self, parser, decode):
        parser.feed(b"*3\r\n:-1\r\n$2\r\nco\r\n$5\r\nredis\r\n")
        assert parser.get_response(decode=decode, encoding="latin-1",) == [
            -1,
            self.encoded_value(decode, b"co"),
            self.encoded_value(decode, b"redis"),
        ]

    def test_nested_array(self, parser, decode):
        parser.feed(b"*2\r\n*2\r\n$2\r\nco\r\n$5\r\nredis\r\n:1\r\n")
        assert parser.get_response(decode=decode, encoding="latin-1",) == [
            [
                self.encoded_value(decode, b"co"),
                self.encoded_value(decode, b"redis"),
            ],
            1,
        ]

    def test_simple_push_array(self, parser, decode):
        parser.feed(b">2\r\n$2\r\nco\r\n$5\r\nredis\r\n")
        assert parser.get_response(
            decode=decode, encoding="latin-1", push_message_types={b"co"}
        ) == [
            self.encoded_value(decode, b"co"),
            self.encoded_value(decode, b"redis"),
        ]

    def test_interleaved_simple_push_array(self, parser, decode):
        parser.feed(b":3\r\n>2\r\n:1\r\n:2\r\n:4\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == 3
        )
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == 4
        )
        assert parser.push_messages.get_nowait() == [1, 2]

    def test_nil_map(self, parser, decode):
        parser.feed(b"%-1\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is None
        )

    def test_empty_map(self, parser, decode):
        parser.feed(b"%0\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == {}
        )

    def test_simple_map(self, parser, decode):
        parser.feed(b"%2\r\n:1\r\n:2\r\n:3\r\n:4\r\n")
        assert parser.get_response(
            decode=decode,
            encoding="latin-1",
        ) == {1: 2, 3: 4}

    def test_nil_set(self, parser, decode):
        parser.feed(b"~-1\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            is None
        )

    def test_empty_set(self, parser, decode):
        parser.feed(b"~0\r\n")
        assert (
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
            == set()
        )

    def test_simple_set(self, parser, decode):
        parser.feed(b"~2\r\n:1\r\n:2\r\n")
        assert parser.get_response(
            decode=decode,
            encoding="latin-1",
        ) == {1, 2}

    def test_multi_container(self, parser, decode):
        # dict containing list and set
        parser.feed(
            b"%2\r\n$2\r\nco\r\n*1\r\n:1\r\n$2\r\nre\r\n~3\r\n:1\r\n:2\r\n:3\r\n"
        )
        assert parser.get_response(decode=decode, encoding="latin-1",) == {
            self.encoded_value(decode, b"co"): [1],
            self.encoded_value(decode, b"re"): {1, 2, 3},
        }

    def test_set_with_dict(self, parser, decode):
        # set containing a dict
        # This specifically represents a minimal example of the response from
        # ``COMMANDS INFO with RESP 3``
        parser.feed(b"~1\r\n%1\r\n:1\r\n:2\r\n")
        with pytest.raises(TypeError):
            parser.get_response(
                decode=decode,
                encoding="latin-1",
            )
