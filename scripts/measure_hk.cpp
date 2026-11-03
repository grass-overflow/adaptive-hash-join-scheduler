
#include <iostream>
#include <vector>
#include <deque>
#include <atomic>
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <numeric>
#include <memory>
#include <cstdint>

#ifdef _OPENMP
#include <omp.h>
#endif

using namespace std;
using Clock = chrono::steady_clock;

// Same basic task representation as the hash-join project.
struct Task {
    size_t partition;
    size_t begin;
    size_t end;
    double estimated_cost_ns;
    uint64_t id;
};

// Spinlock matching the project's synchronization mechanism.
struct SpinMutex {
    atomic_flag flag = ATOMIC_FLAG_INIT;

    void lock() {
        while (flag.test_and_set(memory_order_acquire)) {
        }
    }

    void unlock() {
        flag.clear(memory_order_release);
    }
};

struct SpinLockGuard {
    SpinMutex& mutex;

    explicit SpinLockGuard(SpinMutex& m) : mutex(m) {
        mutex.lock();
    }

    ~SpinLockGuard() {
        mutex.unlock();
    }

    SpinLockGuard(const SpinLockGuard&) = delete;
    SpinLockGuard& operator=(const SpinLockGuard&) = delete;
};

// Same shared worker queue structure.
struct WorkerQueue {
    deque<Task> tasks;
    SpinMutex mutex;
    double remaining_cost_ns = 0.0;
};

// Benchmark configuration.
constexpr int THREADS = 4;
constexpr int QUEUE_BATCH_SIZE = 16;
constexpr int ROUNDS = 1000;
constexpr int SAMPLES = 7;

// Prevent compiler from eliminating consumed tasks.
atomic<uint64_t> global_checksum{0};

// One benchmark execution.
// k = number of tasks per logical batch.
double benchmark_scheduler(int k) {

    vector<unique_ptr<WorkerQueue>> queues;

    queues.reserve(THREADS);

    for (int i = 0; i < THREADS; i++) {
        queues.push_back(make_unique<WorkerQueue>());
    }

    auto start = Clock::now();

    // ------------------------------------------------
    // PHASE 1: Create tasks and distribute them.
    // ------------------------------------------------

    uint64_t id = 0;

    for (int round = 0; round < ROUNDS; round++) {

        for (int j = 0; j < k; j++) {

            Task task{
                0,
                0,
                1,
                100.0,
                id++
            };

            // Distribute tasks across worker queues.
            int owner = static_cast<int>(
                task.id % THREADS
            );

            queues[owner]->tasks.push_back(task);

            queues[owner]->remaining_cost_ns +=
                task.estimated_cost_ns;
        }
    }

    // ------------------------------------------------
    // PHASE 2: Workers retrieve tasks in batches.
    // ------------------------------------------------

#ifdef _OPENMP
#pragma omp parallel num_threads(THREADS)
#endif
    {
#ifdef _OPENMP
        int tid = omp_get_thread_num();
#else
        int tid = 0;
#endif

        WorkerQueue& queue = *queues[tid];

        deque<Task> local_tasks;

        uint64_t local_checksum = 0;

        while (true) {

            // Acquire shared queue lock.
            {
                SpinLockGuard lock(queue.mutex);

                size_t batch = min(
                    static_cast<size_t>(QUEUE_BATCH_SIZE),
                    max(
                        static_cast<size_t>(1),
                        (queue.tasks.size() + 1) / 2
                    )
                );

                // Transfer a batch to the local queue.
                for (size_t i = 0;
                     i < batch && !queue.tasks.empty();
                     i++) {

                    local_tasks.push_back(
                        queue.tasks.back()
                    );

                    queue.remaining_cost_ns -=
                        queue.tasks.back().estimated_cost_ns;

                    queue.tasks.pop_back();
                }
            }

            // Process local task descriptors.
            while (!local_tasks.empty()) {

                Task task = local_tasks.back();

                local_tasks.pop_back();

                local_checksum += task.id;
            }

            // No more tasks in this worker's queue.
            if (queue.tasks.empty())
                break;
        }

        global_checksum.fetch_add(
            local_checksum,
            memory_order_relaxed
        );
    }

    auto end = Clock::now();

    double elapsed_ns =
        chrono::duration<double, nano>(
            end - start
        ).count();

    // Return average management time per logical batch.
    return elapsed_ns / ROUNDS;
}

// Calculate median.
double median(vector<double> values) {

    sort(values.begin(), values.end());

    return values[values.size() / 2];
}

int main() {

#ifdef _OPENMP
    omp_set_dynamic(0);
#endif

    cout << fixed << setprecision(2);

    cout << "========================================\n";
    cout << " HASH JOIN SCHEDULER COST BENCHMARK\n";
    cout << "========================================\n";

    cout << "Threads: " << THREADS << "\n";
    cout << "Batch size: " << QUEUE_BATCH_SIZE << "\n";
    cout << "Rounds: " << ROUNDS << "\n\n";

    vector<int> task_counts = {
        1, 2, 4, 8, 16, 32, 64
    };

    // Warm-up.
    benchmark_scheduler(16);

    // Baseline: one task per logical batch.
    vector<double> baseline_samples;

    for (int s = 0; s < SAMPLES; s++) {
        baseline_samples.push_back(
            benchmark_scheduler(1)
        );
    }

    double T1 = median(baseline_samples);

    cout << "Baseline T(1): "
         << T1 << " ns\n\n";

    cout << left
         << setw(12) << "Tasks (k)"
         << setw(18) << "T(k) ns"
         << setw(24) << "t_schedule ns/task"
         << setw(18) << "H(k) ns"
         << "\n";

    cout << string(72, '-') << "\n";

    for (int k : task_counts) {

        vector<double> samples;

        for (int s = 0; s < SAMPLES; s++) {
            samples.push_back(
                benchmark_scheduler(k)
            );
        }

        double Tk = median(samples);

        double Hk = max(0.0, Tk - T1);

        double t_schedule =
            (k == 1)
            ? 0.0
            : Hk / static_cast<double>(k - 1);

        cout << left
             << setw(12) << k
             << setw(18) << Tk
             << setw(24) << t_schedule
             << setw(18) << Hk
             << "\n";
    }

    cout << "\nChecksum: "
         << global_checksum.load() << "\n";

    cout << "\nBenchmark completed.\n";

    return 0;
}
