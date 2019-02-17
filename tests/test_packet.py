import binascii
from unittest import TestCase

from aioquic.packet import (PACKET_TYPE_INITIAL, PROTOCOL_VERSION_DRAFT_17,
                            QuicHeader, pull_ack_frame, pull_quic_header,
                            pull_uint_var, push_ack_frame, push_quic_header,
                            push_uint_var)
from aioquic.tls import Buffer, BufferReadError

from .utils import load


class UintTest(TestCase):
    def roundtrip(self, data, value):
        buf = Buffer(data=data)
        self.assertEqual(pull_uint_var(buf), value)
        self.assertEqual(buf.tell(), len(data))

        buf = Buffer(capacity=8)
        push_uint_var(buf, value)
        self.assertEqual(buf.data, data)

    def test_uint_var(self):
        # 1 byte
        self.roundtrip(b'\x00', 0)
        self.roundtrip(b'\x01', 1)
        self.roundtrip(b'\x25', 37)
        self.roundtrip(b'\x3f', 63)

        # 2 bytes
        self.roundtrip(b'\x7b\xbd', 15293)
        self.roundtrip(b'\x7f\xff', 16383)

        # 4 bytes
        self.roundtrip(b'\x9d\x7f\x3e\x7d', 494878333)
        self.roundtrip(b'\xbf\xff\xff\xff', 1073741823)

        # 8 bytes
        self.roundtrip(b'\xc2\x19\x7c\x5e\xff\x14\xe8\x8c', 151288809941952652)
        self.roundtrip(b'\xff\xff\xff\xff\xff\xff\xff\xff', 4611686018427387903)

    def test_pull_uint_var_truncated(self):
        buf = Buffer(capacity=0)
        with self.assertRaises(BufferReadError):
            pull_uint_var(buf)

    def test_push_uint_var_too_big(self):
        buf = Buffer(capacity=8)
        with self.assertRaises(ValueError) as cm:
            push_uint_var(buf, 4611686018427387904)
        self.assertEqual(str(cm.exception), 'Integer is too big for a variable-length integer')


class PacketTest(TestCase):
    def test_pull_empty(self):
        buf = Buffer(data=b'')
        with self.assertRaises(BufferReadError):
            pull_quic_header(buf)

    def test_pull_initial_client(self):
        buf = Buffer(data=load('initial_client.bin'))
        header = pull_quic_header(buf)
        self.assertEqual(header.version, PROTOCOL_VERSION_DRAFT_17)
        self.assertEqual(header.packet_type, PACKET_TYPE_INITIAL)
        self.assertEqual(header.destination_cid, binascii.unhexlify('90ed1e1c7b04b5d3'))
        self.assertEqual(header.source_cid, b'')
        self.assertEqual(header.token, b'')
        self.assertEqual(header.rest_length, 1263)
        self.assertEqual(buf.tell(), 17)

    def test_pull_initial_server(self):
        buf = Buffer(data=load('initial_server.bin'))
        header = pull_quic_header(buf)
        self.assertEqual(header.version, PROTOCOL_VERSION_DRAFT_17)
        self.assertEqual(header.packet_type, PACKET_TYPE_INITIAL)
        self.assertEqual(header.destination_cid, b'')
        self.assertEqual(header.source_cid, binascii.unhexlify('0fcee9852fde8780'))
        self.assertEqual(header.token, b'')
        self.assertEqual(header.rest_length, 182)
        self.assertEqual(buf.tell(), 17)

    def test_pull_long_header_no_fixed_bit(self):
        buf = Buffer(data=b'\x80\x00\x00\x00\x00\x00')
        with self.assertRaises(ValueError) as cm:
            pull_quic_header(buf)
        self.assertEqual(str(cm.exception), 'Packet fixed bit is zero')

    def test_pull_long_header_too_short(self):
        buf = Buffer(data=b'\xc0\x00')
        with self.assertRaises(BufferReadError):
            pull_quic_header(buf)

    def test_pull_short_header(self):
        buf = Buffer(data=b'\x40\x00')
        with self.assertRaises(ValueError) as cm:
            pull_quic_header(buf)
        self.assertEqual(str(cm.exception), 'Short header is not supported yet')

    def test_push_initial(self):
        buf = Buffer(capacity=32)
        header = QuicHeader(
            version=PROTOCOL_VERSION_DRAFT_17,
            packet_type=PACKET_TYPE_INITIAL,
            destination_cid=binascii.unhexlify('90ed1e1c7b04b5d3'),
            source_cid=b'')
        push_quic_header(buf, header)
        self.assertEqual(buf.data, binascii.unhexlify('c0ff0000115090ed1e1c7b04b5d30000000000'))


class FrameTest(TestCase):
    def test_ack_frame(self):
        data = b'\x00\x02\x00\x00'

        # parse
        buf = Buffer(data=data)
        ack = pull_ack_frame(buf)
        self.assertEqual(ack.largest_acknowledged, 0)
        self.assertEqual(ack.ack_delay, 2)
        self.assertEqual(ack.first_ack_range, 0)
        self.assertEqual(ack.ack_ranges, [])

        # serialize
        buf = Buffer(capacity=8)
        push_ack_frame(buf, ack)
        self.assertEqual(buf.data, data)

    def test_ack_frame_with_ranges(self):
        data = b'\x00\x02\x01\x00\x02\x03'

        buf = Buffer(data=data)
        ack = pull_ack_frame(buf)
        self.assertEqual(ack.largest_acknowledged, 0)
        self.assertEqual(ack.ack_delay, 2)
        self.assertEqual(ack.first_ack_range, 0)
        self.assertEqual(ack.ack_ranges, [(2, 3)])

        buf = Buffer(capacity=8)
        push_ack_frame(buf, ack)
        self.assertEqual(buf.data, data)
