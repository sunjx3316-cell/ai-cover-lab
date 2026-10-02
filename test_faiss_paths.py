import tempfile
import unittest
from pathlib import Path

import faiss
import numpy as np

from rvc_worker import read_faiss_index


class FaissPaths(unittest.TestCase):
    def test_unicode_index_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / '\u58f0\u7ebf' / 'voice.index'
            path.parent.mkdir()
            index = faiss.IndexFlatL2(2)
            vectors = np.array([[1, 2], [3, 4]], dtype='float32')
            index.add(vectors)
            path.write_bytes(faiss.serialize_index(index).tobytes())
            restored = read_faiss_index(path)
            self.assertEqual(restored.ntotal, 2)
            _, ids = restored.search(vectors, 1)
            np.testing.assert_array_equal(ids[:, 0], [0, 1])

    def test_missing_index_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                read_faiss_index(Path(temporary) / 'missing.index')

    def test_corrupt_index_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bad.index'
            path.write_bytes(b'not an index')
            with self.assertRaises(RuntimeError):
                read_faiss_index(path)


if __name__ == '__main__':
    unittest.main()
