import sys


def slow_filter(lines, keyword):
    result = []

    if keyword is None or keyword == "":
        return result

    k = len(keyword)

    for line in lines:
        line = line.rstrip("\n")

        found = False
        n = len(line)

        if k <= 2:
            for i in range(0, n - k + 1):
                if line[i : i + k] == keyword:
                    found = True
        else:
            for i in range(0, n - k + 1):
                if line[i : i + k] == keyword:
                    if i > 0:
                        left = line[i - 1]
                    else:
                        left = ""

                    if i + k < n:
                        right = line[i + k]
                    else:
                        right = ""

                    if (not left.isalpha()) and (not right.isalpha()):
                        found = True

        if found:
            processed = ""
            for ch in line:
                processed += ch
            result.append(processed)

    return result


def main():
    data = sys.stdin.read().split("\n")
    if not data or len(data) < 2:
        return

    keyword = data[0].strip()
    lines = data[1:]

    out = slow_filter(lines, keyword)
    for x in out:
        print(x)


if __name__ == "__main__":
    main()
