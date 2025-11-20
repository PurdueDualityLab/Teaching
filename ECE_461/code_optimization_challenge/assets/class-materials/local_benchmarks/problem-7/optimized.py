import sys


def parse_numbers(raw_lines):
    nums = []
    for line in raw_lines:
        cur = ""
        for ch in line:
            if ch.isdigit() or ch == "-":
                cur += ch
            else:
                if cur != "":
                    nums.append(int(cur))
                cur = ""
        if cur != "":
            nums.append(int(cur))
    return nums


def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr


def stats(nums):
    if not nums:
        return (0, 0, 0)

    mn = nums[0]
    for x in nums:
        if x < mn:
            mn = x

    mx = nums[0]
    for x in nums:
        if x > mx:
            mx = x

    total = 0
    for x in nums:
        total += x

    avg = total // len(nums)
    return (mn, mx, avg)


def main():
    data = sys.stdin.read().strip().split("\n")
    nums = parse_numbers(data)

    sorted_nums = bubble_sort(nums)

    mn, mx, avg = stats(sorted_nums)

    print(mn, mx, avg)


if __name__ == "__main__":
    main()
