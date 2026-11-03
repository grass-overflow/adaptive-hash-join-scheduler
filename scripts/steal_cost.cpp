

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <pthread.h>
#include <sched.h>
#include <thread>
#include <vector>

using namespace std;
using Clock = chrono::steady_clock;

// ------------------------------------------------------------
// Configuration
// ------------------------------------------------------------

constexpr int REPEATS = 7;
constexpr int CAS_ITERATIONS = 2000000;
constexpr int WARMUP_ROUNDS = 100000;
constexpr int DEFAULT_ROUNDS = 1000000;

// ------------------------------------------------------------
// CPU affinity
// ------------------------------------------------------------

bool pin_to_cpu(int cpu) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu, &cpuset);

    return pthread_setaffinity_np(
        pthread_self(),
        sizeof(cpuset),
        &cpuset
    ) == 0;
}

inline void cpu_pause() {
#if defined(__x86_64__) || defined(__i386__)
    __builtin_ia32_pause();
#else
    atomic_signal_fence(memory_order_seq_cst);
#endif
}

// ------------------------------------------------------------
// Median
// ------------------------------------------------------------

double median(vector<double> values) {
    sort(values.begin(), values.end());

    int n = static_cast<int>(values.size());

    if (n % 2 == 1)
        return values[n / 2];

    return (values[n / 2 - 1] + values[n / 2]) / 2.0;
}

// ------------------------------------------------------------
// Experiment 1: Uncontended spinlock acquisition + release
// ------------------------------------------------------------

double measure_cas_cost(int cpu) {
    if (!pin_to_cpu(cpu)) {
        cerr << "Failed to pin CAS benchmark thread to CPU "
             << cpu << '\n';
        exit(EXIT_FAILURE);
    }

    atomic_flag lock = ATOMIC_FLAG_INIT;

    vector<double> results;

    for (int repeat = 0; repeat < REPEATS; ++repeat) {

        // Warmup
        for (int i = 0; i < 100000; ++i) {
            while (lock.test_and_set(memory_order_acquire))
                cpu_pause();

            lock.clear(memory_order_release);
        }

        auto start = Clock::now();

        for (int i = 0; i < CAS_ITERATIONS; ++i) {
            while (lock.test_and_set(memory_order_acquire))
                cpu_pause();

            lock.clear(memory_order_release);
        }

        auto finish = Clock::now();

        double elapsed_ns =
            chrono::duration<double, nano>(
                finish - start
            ).count();

        results.push_back(elapsed_ns / CAS_ITERATIONS);
    }

    return median(results);
}

// ------------------------------------------------------------
// Experiment 2: Cache-line ownership handoff
//
// Both threads repeatedly access the SAME cache line.
// Thread 0 changes turn: 0 -> 1
// Thread 1 changes turn: 1 -> 0
//
// Each round contains two inter-core handoffs.
// ------------------------------------------------------------

struct alignas(64) SharedCacheLine {
    atomic<int> turn{0};
};

struct alignas(64) Synchronization {
    atomic<int> ready{0};
    atomic<bool> start{false};
};

double run_cache_handoff(
    int cpu0,
    int cpu1,
    int rounds
) {
    SharedCacheLine shared;
    Synchronization sync;

    auto worker = [&](int cpu, int expected, int next) {

        if (!pin_to_cpu(cpu)) {
            cerr << "Failed to pin worker to CPU "
                 << cpu << '\n';
            exit(EXIT_FAILURE);
        }

        sync.ready.fetch_add(1, memory_order_release);

        while (!sync.start.load(memory_order_acquire))
            cpu_pause();

        for (int i = 0; i < rounds; ++i) {

            while (shared.turn.load(memory_order_acquire)
                   != expected) {
                cpu_pause();
            }

            shared.turn.store(next, memory_order_release);
        }
    };

    thread t0(worker, cpu0, 0, 1);
    thread t1(worker, cpu1, 1, 0);

    // Wait until both workers are pinned and ready.
    while (sync.ready.load(memory_order_acquire) != 2)
        cpu_pause();

    auto start = Clock::now();

    sync.start.store(true, memory_order_release);

    t0.join();
    t1.join();

    auto finish = Clock::now();

    double elapsed_ns =
        chrono::duration<double, nano>(
            finish - start
        ).count();

    // Two ownership handoffs per round.
    return elapsed_ns / (2.0 * rounds);
}

double measure_cache_cost(
    int cpu0,
    int cpu1,
    int rounds
) {
    vector<double> results;

    for (int repeat = 0; repeat < REPEATS; ++repeat) {

        // Separate warmup run.
        run_cache_handoff(
            cpu0, cpu1, WARMUP_ROUNDS
        );

        double value = run_cache_handoff(
            cpu0, cpu1, rounds
        );

        results.push_back(value);
    }

    return median(results);
}

// ------------------------------------------------------------
// Main
// ------------------------------------------------------------

int main(int argc, char** argv) {

    int cpu0 = argc > 1 ? atoi(argv[1]) : 0;
    int cpu1 = argc > 2 ? atoi(argv[2]) : 2;
    int rounds = argc > 3 ? atoi(argv[3]) : DEFAULT_ROUNDS;

    if (cpu0 < 0 || cpu1 < 0 ||
        cpu0 == cpu1 || rounds <= 0) {
        cerr << "Usage: ./steal_cost <CPU0> <CPU1> <rounds>\n";
        return EXIT_FAILURE;
    }

    cout << fixed << setprecision(2);

    cout << "\n========================================\n";
    cout << "   WORK-STEALING COST CALIBRATION\n";
    cout << "========================================\n";

    cout << "CPU 0             : " << cpu0 << '\n';
    cout << "CPU 1             : " << cpu1 << '\n';
    cout << "Measurement rounds: " << rounds << '\n';
    cout << "Repeated trials   : " << REPEATS << '\n';

    // 1. Measure uncontended lock acquisition/release.
    double cas_ns = measure_cas_cost(cpu0);

    // 2. Measure inter-core cache-line handoff.
    double cache_ns = measure_cache_cost(
        cpu0, cpu1, rounds
    );

    // 3. Estimate combined cost.
    double steal_ns = cas_ns + cache_ns;

    cout << "\n--------------- RESULTS ----------------\n";

    cout << "CAS lock cost             : "
         << cas_ns << " ns\n";

    cout << "Cache-line handoff cost   : "
         << cache_ns << " ns\n";

    cout << "----------------------------------------\n";

    cout << "Estimated steal cost      : "
         << steal_ns << " ns\n";

    cout << "========================================\n";

    cout << "\nNote: Cache-line handoff is an effective\n"
         << "coherence handoff measurement, not a\n"
         << "direct measurement of physical cache\n"
         << "migration alone.\n";

    return EXIT_SUCCESS;
}
