import sys


def count_words_slow(text):
    words = text.split()
    unique = []

    for w in words:
        if w not in unique:
            unique.append(w)

    result = []

    for u in unique:
        c = 0
        for w in text.split():
            if w == u:
                c += 1
        result.append((u, c))

    for word, cnt in result:
        print(word, cnt)


def main():
    data = sys.stdin.read()
    if not data:
        return

    count_words_slow(data)


if __name__ == "__main__":
    main()
