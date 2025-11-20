import sys

TARGET = "YOKOHAMA"


def count_traces(grid):
    n = len(grid)
    m = len(grid[0]) if n > 0 else 0
    total = 0

    def dfs(i, j, pos):
        nonlocal total

        if pos < 0 or pos >= len(TARGET):
            return

        if grid[i][j] != TARGET[pos]:
            return

        if pos == len(TARGET) - 1:
            total += 1
            return

        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]

        for d in dirs:
            ni = i + d[0]
            nj = j + d[1]

            if not (0 <= ni and ni < n and 0 <= nj and nj < m):
                continue

            dfs(ni, nj, pos + 1)

    for i in range(n):
        for j in range(m):
            dfs(i, j, 0)

    return total


def main():
    data = sys.stdin.read().strip().split()
    if not data:
        return

    it = iter(data)
    n = int(next(it))
    m = int(next(it))

    grid = []
    for _ in range(n):
        row = list(next(it).strip())
        grid.append(row)

    result = count_traces(grid)
    print(result)


if __name__ == "__main__":
    main()
