import unittest
from vector_store import vectorize_document, search_similar
import torch

class TestVectorStore(unittest.TestCase):
    def test_vectorize_document(self):
        text = "这是一个测试文档。它包含多个句子。"
        chunks, vectors = vectorize_document(text)
        self.assertIsInstance(chunks, list)
        self.assertIsInstance(vectors, torch.Tensor)
        self.assertEqual(len(chunks), len(vectors))

    def test_search_similar(self):
        text = "这是测试文档。"
        chunks, vectors = vectorize_document(text)
        results = search_similar("测试", vectors, chunks)
        self.assertIsInstance(results, list)

if __name__ == '__main__':
    unittest.main() 