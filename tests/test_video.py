import struct
import unittest
import http.client
import threading
from http.server import ThreadingHTTPServer
from oseasy_helper.video import Frame, Reassembler, TsMuxer, State, handler_for, mpeg_crc

# Structural NAL markers, not a decodable classroom video sample.
KEY = bytes.fromhex('000000016704000000016805000000016506')
PFRAME = bytes.fromhex('0000014107')


def packet(seq, index, count, body):
    return struct.pack('<8H', 65535, index, count, 320, 180, seq, 320, 180) + body


class CoreTests(unittest.TestCase):
    def test_out_of_order_and_duplicates(self):
        r = Reassembler()
        self.assertEqual(r.push(packet(1, 1, 2, KEY[8:]), 0), [])
        self.assertEqual(r.push(packet(1, 1, 2, KEY[8:]), .01), [])
        frames = r.push(packet(1, 0, 2, KEY[:8]), .02)
        self.assertEqual([f.data for f in frames], [KEY])
        self.assertEqual(r.duplicates, 1)

    def test_sequence_wrap(self):
        r = Reassembler()
        self.assertEqual(len(r.push(packet(65535, 0, 1, KEY), 0)), 1)
        self.assertEqual(len(r.push(packet(0, 0, 1, PFRAME), .1)), 1)
        self.assertEqual(r.lost, 0)

    def test_loss_waits_for_key(self):
        r = Reassembler()
        r.push(packet(1, 0, 1, KEY), 0)
        self.assertEqual(r.push(packet(3, 0, 1, PFRAME), .1), [])
        self.assertEqual(r.drain(.6), [])
        self.assertEqual(r.lost, 1)
        self.assertEqual(len(r.push(packet(4, 0, 1, KEY), .7)), 1)

    def test_reject_invalid(self):
        r = Reassembler()
        for b in (b'bad', packet(0, 2, 2, KEY), packet(0, 0, 5000, KEY)):
            self.assertEqual(r.push(b), [])
        self.assertEqual(r.invalid, 3)

    def test_stream_restart_after_silence(self):
        r = Reassembler()
        r.push(packet(200, 0, 1, KEY), 0)
        self.assertEqual(r.push(packet(1, 0, 1, PFRAME), 3), [])
        self.assertEqual(len(r.push(packet(2, 0, 1, KEY), 3.1)), 1)

    def test_ts_psi_crc_and_video_pid(self):
        ts = TsMuxer().mux(Frame(KEY, True, 320, 180, 0))
        packets = [ts[i:i+188] for i in range(0, len(ts), 188)]
        self.assertTrue(all(len(p) == 188 and p[0] == 0x47 for p in packets))
        self.assertEqual([((p[1] & 31) << 8) | p[2] for p in packets[:3]], [0, 0x1000, 0x100])
        for p in packets[:2]:
            length = ((p[6] & 15) << 8) | p[7]
            self.assertEqual(mpeg_crc(p[5:5+3+length]), 0)

    def test_fragment_to_http_stream(self):
        state = State()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(state))
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request('GET', '/live.ts')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Type'), 'video/mp2t')
            raw = KEY + b'\x55' * 800
            # Exercise out-of-order input through the actual HTTP publishing path.
            for index in (2, 0, 1):
                body = raw[index*300:(index+1)*300]
                for frame in state.reassembler.push(packet(1, index, 3, body), .01*index):
                    state.publish(frame)
            expected = TsMuxer().mux(Frame(raw, True, 320, 180, .02))
            self.assertEqual(response.read(len(expected)), expected)
            response.close()
        finally:
            connection.close()
            state.running = False
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    def test_ts_preserves_pes_payload_across_packets(self):
        raw = KEY + bytes(range(256)) * 3
        ts = TsMuxer().mux(Frame(raw, True, 320, 180, 0))
        payload = bytearray()
        for offset in range(0, len(ts), 188):
            p = ts[offset:offset+188]
            if ((p[1] & 31) << 8) | p[2] != 0x100:
                continue
            start = 5 + p[4] if p[3] & 0x20 else 4
            payload.extend(p[start:])
        self.assertEqual(payload[:9], bytes.fromhex('000001e00000808005'))
        self.assertEqual(payload[14:], bytes.fromhex('0000000109f0') + raw)


if __name__ == '__main__':
    unittest.main()
