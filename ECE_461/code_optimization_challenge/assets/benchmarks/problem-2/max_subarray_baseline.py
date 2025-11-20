import sys


def max_subarray_sum(nums):
    """
    Naive cubic-time maximum subarray: O(n^3)
    """
    n = len(nums)
    if n == 0:
        return 0

    best = nums[0]

    for i in range(n):
        for j in range(i, n):
            current = 0
            for k in range(i, j + 1):
                current += nums[k]
            if current > best:
                best = current

    return best


def main():
    data = sys.stdin.read().strip().split()
    if not data:
        return

    it = iter(data)
    n = int(next(it))
    arr = []

    for _ in range(n):
        try:
            arr.append(int(next(it)))
        except StopIteration:
            break

    result = max_subarray_sum(arr)
    print(result)


if __name__ == "__main__":
    main()
