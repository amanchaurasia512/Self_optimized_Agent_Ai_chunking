# Vendored from ekimetrics/adaptive-chunking, commit ea87ce8, src/adaptive_chunking/paper/splitters.py, lines 60-231
# MIT License, Copyright (c) 2026 Ekimetrics; full text in src/chunk/vendor/LICENSE_adaptive_chunking
# Only the Stanza method is used here; the nltk and spacy branches are kept verbatim but their libraries are not installed.
import stanza


class SentenceSplitter:
    """
    Split text into sentences using NLTK, Stanza, or SpaCy.
    """

    def __init__(self, method = "nltk", sentences_per_chunk = 1, device = "cpu"):
        if method == "nltk":
            # Download NLTK punkt tokenizer if not already downloaded
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('punkt_tab', quiet=True)
            except:
                pass
            self.splitter = self._split_into_sentences_nltk
        elif method == "stanza":
            self.splitter = self._split_into_sentences_stanza
        elif method == "spacy-small":
            self.splitter = lambda text: self._split_into_sentences_spacy(text, modeltype="small")
        elif method == "spacy-medium":
            self.splitter = lambda text: self._split_into_sentences_spacy(text, modeltype="medium")
        elif method == "spacy-large":
            self.splitter = lambda text: self._split_into_sentences_spacy(text, modeltype="large")
        elif method == "lines":
            self.splitter = lambda text: self._split_by_lines(text)
        elif method == "blank_lines":
            self.splitter = lambda text: self._split_by_blank_lines(text)
        else:
            raise ValueError("Invalid method. Choose 'nltk', 'stanza', 'spacy-small', 'spacy-medium', or 'spacy-large'.")

        self.sentences_per_chunk = sentences_per_chunk
        self.device = device

    def _split_into_sentences_nltk(self, text: str) -> list[str]:
        """
        Splits text into sentences using NLTK's sent_tokenize while preserving all text
        including line separators between sentence boundaries.
        """

        # Get the raw sentences
        sentences = sent_tokenize(text)
        result = []

        # If no sentences were found, return the original text
        if not sentences:
            return [text]

        current_pos = 0

        for i, sentence in enumerate(sentences):
            # Find the start position of this sentence
            start_pos = text.find(sentence, current_pos)

            # If we couldn't find the sentence, try a more flexible search
            if start_pos == -1:
                start_pos = current_pos

            # For all sentences except the last one
            if i < len(sentences) - 1:
                # Find the start position of the next sentence
                next_sentence = sentences[i + 1]
                next_start = text.find(next_sentence, start_pos + len(sentence))

                if next_start == -1:
                    # If we can't find the next sentence, just use this one
                    segment = text[start_pos:]
                    current_pos = len(text)
                else:
                    # Include everything up to the start of the next sentence
                    segment = text[start_pos:next_start]
                    current_pos = next_start
            else:
                # For the last sentence, include everything until the end
                segment = text[start_pos:]

            result.append(segment)

        return result

    def _split_into_sentences_stanza(self, text: str) -> list[str]:
        try:
            nlp = stanza.Pipeline('en', processors='tokenize', tokenize_no_ssplit=False, verbose=False, device=self.device)
        except Exception as e:
            print("Stanza model not found. Downloading...")
            stanza.download('en')
            nlp = stanza.Pipeline('en', processors='tokenize', tokenize_no_ssplit=False, verbose=False, device=self.device)

        doc = nlp(text)
        sentences = doc.sentences
        result = []

        for i, sent in enumerate(sentences):
            # For every sentence except the last, extend to include separator
            if i < len(sentences) - 1:
                next_sent = sentences[i+1]
                sentence_with_sep = text[sent.tokens[0].start_char:next_sent.tokens[0].start_char]
            else:
                # For the last sentence, take until the end of text
                sentence_with_sep = text[sent.tokens[0].start_char:]

            result.append(sentence_with_sep)

        return result

    def _split_into_sentences_spacy(self, text: str, modeltype: str) -> list[str]:
        if modeltype == "small":
            nlp = spacy.load("en_core_web_sm")
        elif modeltype == "medium":
            nlp = spacy.load("en_core_web_md")
        elif modeltype == "large":
            nlp = spacy.load("en_core_web_lg")
        else:
            raise ValueError("Invalid model type. Choose 'small', 'medium', or 'large'.")

        if self.device.startswith("cuda"):
            device = self.device.split(":")[-1]
            spacy.prefer_gpu(device)

        doc = nlp(text)
        sentences = list(doc.sents)
        result = []

        for i, sent in enumerate(sentences):
            # For every sentence except the last, extend the sentence to include the separator
            if i < len(sentences) - 1:
                next_sent = sentences[i+1]
                sentence_with_sep = text[sent.start_char:next_sent.start_char]
            else:
                # For the last sentence, take until the end of the text.
                sentence_with_sep = text[sent.start_char:]
            result.append(sentence_with_sep)

        return result

    def _split_by_lines(self, text: str) -> list[str]:
        lines = text.splitlines()
        result = []

        current_blanklines = 0
        for i, line in enumerate(lines):
            if line == "":
                current_blanklines += 1
            else:
                if result:
                    result[-1] += '\n' * current_blanklines
                    current_blanklines = 0
                    result.append(line + '\n')
                else:
                    result.append(line + '\n')
                    result[-1] = '\n' * current_blanklines + result[-1]

        if current_blanklines:
            result[-1] += '\n' * current_blanklines

        return result

    def _split_by_blank_lines(self, text: str) -> list[str]:
        chunks = regex_splitter(text, r"\n\n")
        return chunks

    def split_text(self, text: str) -> list[str]:

        sentences = self.splitter(text)

        # If sentences_per_chunk is greater than 1, group sentences into chunks
        if self.sentences_per_chunk > 1:
            chunks = []
            for i in range(0, len(sentences), self.sentences_per_chunk):
                chunk = "".join(sentences[i:i + self.sentences_per_chunk])
                chunks.append(chunk)
            return chunks
        return sentences

