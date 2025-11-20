import sys

sys.setrecursionlimit(10**7)


def count_increasing_paths(grid):
    """
    Deliberately naive DFS that explores all possible paths.
    """

    n = len(grid)
    m = len(grid[0]) if n > 0 else 0

    directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    total_paths = 0

    def dfs(i, j, prev_value):
        if grid[i][j] <= prev_value:
            return 0

        count = 1

        for di, dj in directions:
            ni, nj = i + di, j + dj
            if 0 <= ni < n and 0 <= nj < m:
                count += dfs(ni, nj, grid[i][j])

        return count

    for i in range(n):
        for j in range(m):
            total_paths += dfs(i, j, -(10**18))

    return total_paths


def main():
    data = sys.stdin.read().strip().split()
    if not data:
        return

    it = iter(data)
    n = int(next(it))
    m = int(next(it))

    grid = []
    for _ in range(n):
        row = []
        for _ in range(m):
            row.append(int(next(it)))
        grid.append(row)

    result = count_increasing_paths(grid)
    print(result)


if __name__ == "__main__":
    main()
