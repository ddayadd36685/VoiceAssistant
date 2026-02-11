import os
import sys
import unittest

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from voice_assistant.parser import Parser
from voice_assistant.wakeword import WakeWordDetector


class TestVoiceAssistantModules(unittest.TestCase):
    def test_parser(self):
        os.environ["VOICE_ASSISTANT_DISABLE_LLM"] = "1"
        p = Parser()
        res = p.parse("帮我打开 英雄联盟")
        self.assertEqual(res["intent"], "open_file")
        self.assertEqual(res["target"], "英雄联盟")

        res = p.parse("打开 WeGame 打开一下")
        self.assertEqual(res["intent"], "open_file")
        self.assertEqual(res["target"], "Wegame")

        res = p.parse("帮我打开 main.py")
        self.assertEqual(res["intent"], "unknown")

        res = p.parse("你好")
        self.assertEqual(res["intent"], "unknown")

    def test_wakeword_mock(self):
        w = WakeWordDetector()
        self.assertIsNone(w.process(b"\x00" * 1024))
        loud_chunk = b"\xff\x7f" * 512
        res = w.process(loud_chunk)
        self.assertTrue(res is None or isinstance(res, str))


if __name__ == "__main__":
    unittest.main()
