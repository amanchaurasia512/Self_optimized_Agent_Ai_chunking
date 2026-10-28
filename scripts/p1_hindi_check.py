"""P1: measure broken Devanagari in a PDF's extracted text (pdfplumber).
A word cannot start with a combining mark (vowel sign, virama, nasal sign), so the share of Devanagari words that do
is a language-level lower bound on extraction damage, comparable across parsers."""
import sys
import unicodedata

import pdfplumber


def devanagari_words(text):
    return [word for word in text.split() if any("\u0900" <= char <= "\u097f" for char in word)]


def devanagari_quality(text):
    words = devanagari_words(text)
    broken = [word for word in words if unicodedata.category(word[0]) in ("Mn", "Mc")]
    letters = [char for char in text if unicodedata.category(char)[0] in ("L", "M")]
    devanagari_letters = sum("\u0900" <= char <= "\u097f" for char in letters)
    return {"devanagari_share": round(devanagari_letters / len(letters), 3) if letters else 0.0,
            "devanagari_words": len(words), "starts_with_mark": len(broken),
            "broken_share": round(len(broken) / len(words), 3) if words else 0.0,
            "replacement_chars": text.count("\ufffd"), "examples": broken[:10]}

def main():
    for path in sys.argv[1:]:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        print(path, devanagari_quality(text))


if __name__ == "__main__":
    main()