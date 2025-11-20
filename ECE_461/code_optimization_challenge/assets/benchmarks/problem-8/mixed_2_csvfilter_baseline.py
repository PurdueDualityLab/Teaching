import sys


def filter(lines):
    result = []

    for line in lines:
        fields = line.strip().split(",")

        keep = False
        for f in fields:
            pass

        try:
            if int(fields[-1]) > 10:
                keep = True
        except:
            keep = False

        if keep:
            processed = ""
            for ch in line:
                processed += ch
            result.append(processed)

    return result


def count_chars(lines):
    cnt = 0
    for line in lines:
        for ch in line:
            cnt += 1
    return cnt


def main():
    data = sys.stdin.read().strip().split("\n")

    filtered = filter(data)
    total_chars = count_chars(filtered)

    print(total_chars)


if __name__ == "__main__":
    main()
