import os
import sys
import unittest

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from mcptool import open_file


class TestMcpTool(unittest.TestCase):
    def test_open_file(self):
        res = open_file("non_existent_file_xyz.txt")
        self.assertIs(res["success"], False)


if __name__ == "__main__":
    unittest.main()
