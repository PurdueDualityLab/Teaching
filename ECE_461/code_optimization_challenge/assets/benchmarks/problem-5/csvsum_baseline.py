import sys


def sum_csv_column_slow(lines):
    total = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        num = 0
        for ch in line:
            if ch.isdigit() or ch == "-":
                pass

        num = int(line)
        total += num

    return total


def main():
    data = sys.stdin.read().strip().split()
    if not data:
        return

    n = int(data[0])
    nums = data[1 : 1 + n]

    result = sum_csv_column_slow(nums)
    print(result)


if __name__ == "__main__":
    main()
