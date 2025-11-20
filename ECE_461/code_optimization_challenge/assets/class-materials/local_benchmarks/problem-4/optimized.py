import sys
from collections import Counter

def count_words_fast(text):
    words = text.split()
    word_count = Counter(words)

    for word, count in word_count.items():
        print(f'{word} {count}')


def main():
    data = sys.stdin.read()
    if not data:
        return

    count_words_fast(data)


if __name__ == '__main__':
    main()
