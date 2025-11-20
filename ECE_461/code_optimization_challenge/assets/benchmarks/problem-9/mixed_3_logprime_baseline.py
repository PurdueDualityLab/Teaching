import sys


def is_prime(n):
    if n <= 1:
        return False
    for i in range(2, n):
        if n % i == 0:
            return False
    return True


def extract_numbers(line):
    nums = []
    cur = ""
    for ch in line:
        if ch.isdigit():
            cur += ch
        else:
            if cur:
                nums.append(int(cur))
            cur = ""
    if cur:
        nums.append(int(cur))
    return nums


def main():
    data = sys.stdin.read().split("\n")
    prime_count = 0

    for line in data:
        nums = extract_numbers(line)
        for num in nums:
            if is_prime(num):
                prime_count += 1

    print(prime_count)


if __name__ == "__main__":
    main()
