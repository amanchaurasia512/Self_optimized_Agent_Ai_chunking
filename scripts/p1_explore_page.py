"""Look at one PDF page through pdfplumber: the raw text, and signs of glued words and mixed columns."""
import argparse

import pdfplumber


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--pdf", required=True, help="path to the PDF")
    arg_parser.add_argument("--page", type=int, required=True, help="page number, starting at 1")
    args = arg_parser.parse_args()

    with pdfplumber.open(args.pdf) as pdf:
        page = pdf.pages[args.page - 1]
        text = page.extract_text() or ""
        words = page.extract_words()

    print("=== raw text, exactly as pdfplumber returns it ===")
    print(text)
    print("\n=== what to look for ===")
    average = sum(len(word["text"]) for word in words) / max(len(words), 1)
    print(f"characters {len(page.chars)}, words {len(words)}, average word length {average:.1f} (normal English is about 5)")
    longest = sorted(words, key=lambda word: len(word["text"]), reverse=True)[:5]
    print("five longest 'words' (glued words show up here):", [word["text"] for word in longest])
    middle = page.width / 2
    left = sum(word["x0"] < middle for word in words)
    print(f"words starting in the left half / right half: {left} / {len(words) - left} "
          "(both large = two columns, which pdfplumber reads line by line across both)")


if __name__ == "__main__":
    main()