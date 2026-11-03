
#include <iostream>
#include <vector>
#include <thread>
#include <atomic>
#include <chrono>
#include <algorithm>
#include <numeric>
#include <cmath>

using namespace std;
using namespace chrono;

struct Task {
    size_t start;
    size_t end;
    size_t id;
};

volatile size_t global_sink = 0;

const int NUM_WORKERS = 4;


double benchmark(int k, int trials) {
    vector<double> times;

    const size_t N = 1000000;

    for (int trial = 0; trial < trials; trial++) {

        atomic<size_t> next_task{0};
        vector<Task> tasks;
        vector<size_t> worker_results(NUM_WORKERS, 0);

        auto start_time = steady_clock::now();

        // 1. Task formation and descriptor initialization
        tasks.reserve(k);

        for (int j = 0; j < k; j++) {
            size_t s = (N * j) / k;
            size_t e = (N * (j + 1)) / k;

            tasks.push_back({s, e, (size_t)j});
        }

        // 2. Parallel worker scheduling using CAS
        vector<thread> workers;

        for (int w = 0; w < NUM_WORKERS; w++) {
            workers.emplace_back([&, w]() {

                size_t local_sum = 0;

                while (true) {
                    size_t expected =
                        next_task.load(memory_order_relaxed);

                    // Atomically claim a task
                    while (expected < tasks.size() &&
                           !next_task.compare_exchange_weak(
                               expected,
                               expected + 1,
                               memory_order_relaxed,
                               memory_order_relaxed)) {
                    }

                    if (expected >= tasks.size())
                        break;

                    // Simulate task dispatch and consumption
                    const Task& task = tasks[expected];

                    local_sum +=
                        task.end - task.start + task.id;
                }

                worker_results[w] = local_sum;
            });
        }

        // 3. Wait for all workers
        for (auto& worker : workers) {
            worker.join();
        }

        auto end_time = steady_clock::now();

        // Prevent results from being discarded
        for (auto value : worker_results)
            global_sink += value;

        double elapsed =
            duration<double, nano>(
                end_time - start_time
            ).count();

        times.push_back(elapsed);
    }

    sort(times.begin(), times.end());

    return times[times.size() / 2];
}

int main() {

    const int TRIALS = 9;

    vector<int> chunk_sizes = {
        1000, 5000, 10000,
        20000, 40000, 80000
    };

    vector<double> measured;

    cout << "Workers: " << NUM_WORKERS << "\n";
    cout << "Trials: " << TRIALS << "\n\n";

    cout << "Chunks,Total_Time_ns\n";

    for (int k : chunk_sizes) {
        double t = benchmark(k, TRIALS);

        measured.push_back(t);

        cout << k << "," << t << "\n";
    }

    // 4. Linear regression: T(k) = intercept + slope*k
    double mean_k =
        accumulate(chunk_sizes.begin(),
                   chunk_sizes.end(), 0.0)
        / chunk_sizes.size();

    double mean_t =
        accumulate(measured.begin(),
                   measured.end(), 0.0)
        / measured.size();

    double numerator = 0;
    double denominator = 0;

    for (size_t i = 0; i < chunk_sizes.size(); i++) {
        numerator +=
            (chunk_sizes[i] - mean_k) *
            (measured[i] - mean_t);

        denominator +=
            (chunk_sizes[i] - mean_k) *
            (chunk_sizes[i] - mean_k);
    }

    double slope = numerator / denominator;
    double intercept = mean_t - slope * mean_k;

    cout << "\nRegression results:\n";
    cout << "T(k) = " << intercept
         << " + " << slope << " * k\n";

    cout << "\nEstimated marginal scheduling cost: "
         << slope << " ns/task\n";

    return 0;
}
