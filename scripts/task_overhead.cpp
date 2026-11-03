
#include <iostream>
#include <vector>
#include <deque>
#include <chrono>
#include <algorithm>
#include <numeric>
#include <cstdint>

using namespace std;
using namespace chrono;

struct Task {
    size_t start;
    size_t end;
    size_t task_id;
    size_t partition_id;
};

volatile uint64_t sink = 0;

// Simulates task formation and queue management
double benchmark(int k, int repetitions) {
    const size_t N = 1000000;

    deque<Task> queue;

    // Warm-up / avoid first-use effects
    for (int i = 0; i < 1000; i++) {
        queue.push_back({0, 100, (size_t)i, 0});
        queue.pop_front();
    }

    vector<double> samples;

    for (int rep = 0; rep < repetitions; rep++) {
        queue.clear();

        auto start_time = steady_clock::now();

        // Form k chunks from a partition
        for (int j = 0; j < k; j++) {
            size_t chunk_start = (N * j) / k;
            size_t chunk_end = (N * (j + 1)) / k;

            Task task{
                chunk_start,
                chunk_end,
                (size_t)j,
                0
            };

            queue.push_back(task);
        }

        // Simulate scheduler consuming tasks
        while (!queue.empty()) {
            Task task = queue.front();
            queue.pop_front();

            sink += task.end - task.start;
        }

        auto end_time = steady_clock::now();

        double elapsed =
            duration<double, nano>(end_time - start_time).count();

        samples.push_back(elapsed / k);
    }

    sort(samples.begin(), samples.end());

    return samples[samples.size() / 2] * k;
}

int main() {
    const int repetitions = 10000;

    vector<int> chunk_sizes = {1, 2, 4, 8, 16, 32, 64};

    cout << "Chunks,Total_Time_ns,Incremental_ns_per_chunk\n";

    double baseline = benchmark(1, repetitions);

    for (int k : chunk_sizes) {
        double total = benchmark(k, repetitions);

        double incremental =
            (total - baseline) / (k - 1);

        if (k == 1)
            incremental = 0;

        cout << k << ","
             << total << ","
             << incremental << "\n";
    }

    return 0;
}
