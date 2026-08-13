import re


class TextChunker:
    """Text chunker for splitting documents into smaller pieces for RAG processing.

    Splits text into chunks of approximately ``chunk_size`` characters with an
    optional ``overlap`` between consecutive chunks to preserve context.
    """

    def __init__(self, chunk_size=500, overlap=100):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text):
        """Split ``text`` into chunks.

        Returns a list of dicts, each containing:
            - chunk_index: int (0-based)
            - content: str (the chunk text)
            - start_pos: int (character position in original text)
            - end_pos: int (character position in original text)
        """
        # Edge cases: empty or whitespace-only text returns empty list.
        if not text or text.strip() == "":
            return []

        # Short text fits in a single chunk.
        if len(text) <= self.chunk_size:
            return [{
                "chunk_index": 0,
                "content": text,
                "start_pos": 0,
                "end_pos": len(text),
            }]

        # Build a list of small contiguous segments that tile the original text.
        # Each segment is a tuple (content, start_pos, end_pos) and is at most
        # ``chunk_size`` characters long. Segments are contiguous so that any
        # consecutive run of them corresponds to a contiguous slice of the
        # original text.
        segments = self._build_segments(text)

        chunks = []
        current_text = ""
        current_start = 0

        for seg_text, seg_start, seg_end in segments:
            if current_text == "":
                # Starting a fresh chunk.
                current_start = seg_start
                current_text = seg_text
            elif len(current_text) + len(seg_text) > self.chunk_size:
                # Adding this segment would exceed chunk_size; finalize current.
                current_end = current_start + len(current_text)
                chunks.append((current_text, current_start, current_end))
                # Begin a new chunk with overlap from the previous chunk.
                if self.overlap > 0 and len(current_text) >= self.overlap:
                    overlap_text = current_text[-self.overlap:]
                    current_start = current_end - self.overlap
                    current_text = overlap_text + seg_text
                else:
                    current_start = seg_start
                    current_text = seg_text
            else:
                # Segment fits; append it.
                current_text += seg_text

        # Flush the trailing chunk.
        if current_text:
            current_end = current_start + len(current_text)
            chunks.append((current_text, current_start, current_end))

        return [{
            "chunk_index": idx,
            "content": content,
            "start_pos": start,
            "end_pos": end,
        } for idx, (content, start, end) in enumerate(chunks)]

    def _build_segments(self, text):
        """Split text into contiguous segments, each no larger than chunk_size.

        Strategy:
            1. Split by paragraphs (double newline).
            2. If a paragraph exceeds chunk_size, split it by sentences.
            3. If a sentence exceeds chunk_size, split it by chunk_size directly.
        """
        segments = []
        for para_text, para_start, para_end in self._split_paragraphs(text):
            if len(para_text) > self.chunk_size:
                for sent_text, sent_start, sent_end in self._split_sentences(
                    para_text, para_start
                ):
                    if len(sent_text) > self.chunk_size:
                        segments.extend(
                            self._split_by_size(sent_text, sent_start)
                        )
                    else:
                        segments.append((sent_text, sent_start, sent_end))
            else:
                segments.append((para_text, para_start, para_end))
        return segments

    def _split_paragraphs(self, text):
        """Split text into paragraphs separated by double newline.

        Returns a list of (content, start_pos, end_pos) tuples that tile the
        original text (the ``\\n\\n`` separator is kept at the end of each
        paragraph so that consecutive slices are contiguous).
        """
        paragraphs = []
        pos = 0
        for match in re.finditer(r"\n\n", text):
            end = match.end()
            paragraphs.append((text[pos:end], pos, end))
            pos = end
        if pos < len(text):
            paragraphs.append((text[pos:len(text)], pos, len(text)))
        return paragraphs

    def _split_sentences(self, text, start_pos):
        """Split text into sentences.

        Sentence delimiters: Chinese ``。！？`` and English ``.!?`` plus newline.
        Returns a list of (content, start_pos, end_pos) tuples that tile the
        input. Each sentence includes its trailing delimiter.
        """
        delimiters = set("。！？.!?\n")
        sentences = []
        last = 0
        for i, ch in enumerate(text):
            if ch in delimiters:
                end = i + 1
                sentences.append((text[last:end], start_pos + last, start_pos + end))
                last = end
        if last < len(text):
            sentences.append(
                (text[last:len(text)], start_pos + last, start_pos + len(text))
            )
        return sentences

    def _split_by_size(self, text, start_pos):
        """Split text into fixed-size pieces of chunk_size characters.

        Returns a list of (content, start_pos, end_pos) tuples that tile the
        input.
        """
        pieces = []
        for i in range(0, len(text), self.chunk_size):
            piece = text[i:i + self.chunk_size]
            pieces.append((piece, start_pos + i, start_pos + i + len(piece)))
        return pieces


if __name__ == "__main__":
    chunker = TextChunker(chunk_size=50, overlap=10)

    print("=== Test 1: empty / whitespace-only text ===")
    print(chunker.chunk(""))
    print(chunker.chunk("   \n  \t "))

    print("\n=== Test 2: short text (single chunk) ===")
    short = "Hello, world!"
    for c in chunker.chunk(short):
        print(c)

    print("\n=== Test 3: multi-paragraph text ===")
    multi = (
        "This is the first paragraph. It has a couple of sentences.\n\n"
        "Here is the second paragraph with more content to chunk.\n\n"
        "And a third paragraph to finish things off."
    )
    for c in chunker.chunk(multi):
        print(c)
        # Verify content matches the original slice.
        assert c["content"] == multi[c["start_pos"]:c["end_pos"]], "slice mismatch!"

    print("\n=== Test 4: oversized paragraph with long sentences ===")
    long_text = "A" * 200
    for c in chunker.chunk(long_text):
        print(c)
        assert c["content"] == long_text[c["start_pos"]:c["end_pos"]], "slice mismatch!"

    print("\n=== Test 5: Chinese text ===")
    cn_text = "这是第一段话。这是第二段话。\n\n这是第三段话，内容比较长用来测试分块效果。"
    for c in chunker.chunk(cn_text):
        print(c)
        assert c["content"] == cn_text[c["start_pos"]:c["end_pos"]], "slice mismatch!"

    print("\nAll tests passed.")
