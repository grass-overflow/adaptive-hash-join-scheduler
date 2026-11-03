
#include <windows.h>
#include <iostream>
#include <deque>
#include <vector>
#include <thread>
#include <atomic>
#include <chrono>
#include <algorithm>
#include <numeric>
#include <iomanip>
#include <cstdlib>

using namespace std;
using Clock = chrono::steady_clock;

struct Task {
    int id;
    double estimated_cost_ns;
};

struct SpinMutex {
    atomic_flag flag = ATOMIC_FLAG_INIT;

    void lock() {
        while (flag.test_and_set(memory_order_acquire)) {
            this_thread::yield();
        }
    }

    void unlock() {
        flag.clear(memory_order_release);
    }
};

struct WorkerQueue {
    deque<Task> tasks;
    SpinMutex mutex;
    double remaining_cost_ns = 0;
};

bool pin_cpu(int cpu) {
    if (cpu < 0 || cpu >= 64) return false;

    DWORD_PTR mask = DWORD_PTR(1) << cpu;

    return SetThreadAffinityMask(
        GetCurrentThread(), mask
    ) != 0;
}

struct Stats {
    vector<double> successful_ns;
    vector<double> failed_ns;

    long long tasks_stolen = 0;
    long long successful = 0;
    long long failed = 0;
};

double median(vector<double> v) {
    if (v.empty()) return 0;

    sort(v.begin(), v.end());

    size_t n = v.size();

    if (n % 2)
        return v[n / 2];

    return (v[n / 2 - 1] + v[n / 2]) / 2.0;
}

double mean(const vector<double>& v) {
    if (v.empty()) return 0;

    return accumulate(v.begin(), v.end(), 0.0)
           / v.size();
}

double calibrate_lock() {
    const int repetitions = 5;
    const int iterations = 4096;

    vector<double> samples;

    SpinMutex lock;

    for (int r = 0; r < repetitions; r++) {

        auto start = Clock::now();

        for (int i = 0; i < iterations; i++) {
            lock.lock();
            lock.unlock();
        }

        auto end = Clock::now();

        double elapsed =
            chrono::duration<double, nano>(
                end - start
            ).count();

        samples.push_back(elapsed / iterations);
    }

    return median(samples);
}

Stats run_benchmark(
    int thief_cpu,
    int victim_cpu,
    int task_count,
    int batch_limit,
    bool contention,
    double threshold
) {
    WorkerQueue victim;
    deque<Task> thief_local;

    for (int i = 0; i < task_count; i++) {
        victim.tasks.push_back({i, 1000.0});
        victim.remaining_cost_ns += 1000.0;
    }

    atomic<bool> start{false};
    atomic<bool> stop{false};
    atomic<bool> ready{false};

    thread victim_thread;

    if (contention) {
        victim_thread = thread([&]() {
            if (!pin_cpu(victim_cpu)) {
                cerr << "Victim affinity failed\n";
                abort();
            }

            ready.store(true, memory_order_release);

            while (!start.load(memory_order_acquire)) {
                this_thread::yield();
            }

            while (!stop.load(memory_order_acquire)) {
                victim.mutex.lock();

                // Victim-side queue inspection.
                volatile size_t n = victim.tasks.size();
                (void)n;

                victim.mutex.unlock();
            }
        });

        while (!ready.load(memory_order_acquire)) {
            this_thread::yield();
        }
    }

    if (!pin_cpu(thief_cpu)) {
        cerr << "Thief affinity failed\n";
        stop.store(true);
        start.store(true);

        if (victim_thread.joinable())
            victim_thread.join();

        exit(1);
    }

    Stats stats;
    stats.successful_ns.reserve(task_count);
    stats.failed_ns.reserve(1);

    start.store(true, memory_order_release);

    while (true) {
        auto t0 = Clock::now();

        victim.mutex.lock();

        bool eligible =
            victim.remaining_cost_ns > threshold &&
            !victim.tasks.empty() &&
            victim.tasks.front().estimated_cost_ns
                > threshold;

        if (!eligible) {
            victim.mutex.unlock();

            auto t1 = Clock::now();

            stats.failed_ns.push_back(
                chrono::duration<double, nano>(
                    t1 - t0
                ).count()
            );

            stats.failed++;
            break;
        }

        int n = static_cast<int>(victim.tasks.size());

        int batch = min(
            batch_limit,
            max(1, (n + 1) / 2)
        );

        double transferred_cost = 0;

        for (int i = 0; i < batch; i++) {
            Task task = victim.tasks.front();
            victim.tasks.pop_front();

            transferred_cost += task.estimated_cost_ns;

            thief_local.push_back(task);
        }

        victim.remaining_cost_ns -= transferred_cost;

        victim.mutex.unlock();

        auto t1 = Clock::now();

        stats.successful_ns.push_back(
            chrono::duration<double, nano>(
                t1 - t0
            ).count()
        );

        stats.successful++;
        stats.tasks_stolen += batch;
    }

    stop.store(true, memory_order_release);

    if (victim_thread.joinable())
        victim_thread.join();

    // Ensure transferred tasks were retained.
    if (static_cast<long long>(thief_local.size())
        != stats.tasks_stolen) {
        cerr << "Task count mismatch!\n";
        exit(1);
    }

    return stats;
}

void print_stats(const string& label, const Stats& s) {
    cout << "\n" << label << "\n";
    cout << "--------------------------------\n";

    cout << "Successful steals  : " << s.successful << "\n";
    cout << "Failed attempts    : " << s.failed << "\n";
    cout << "Tasks transferred  : " << s.tasks_stolen << "\n";

    cout << "Mean successful    : "
         << mean(s.successful_ns) << " ns\n";

    cout << "Median successful  : "
         << median(s.successful_ns) << " ns\n";

    cout << "Mean failed        : "
         << mean(s.failed_ns) << " ns\n";
}

int main(int argc, char** argv) {

    if (argc < 3) {
        cout << "Usage: steal_bench.exe "
             << "<thief_cpu> <victim_cpu> "
             << "[task_count] [batch_limit]\n";
        return 1;
    }

    int thief_cpu = atoi(argv[1]);
    int victim_cpu = atoi(argv[2]);

    int task_count =
        argc > 3 ? atoi(argv[3]) : 200000;

    int batch_limit =
        argc > 4 ? atoi(argv[4]) : 32;

    if (task_count <= 0 || batch_limit <= 0 ||
        thief_cpu == victim_cpu) {
        cerr << "Invalid arguments\n";
        return 1;
    }

    cout << fixed << setprecision(2);

    double cas_ns = calibrate_lock();

    // Placeholder until independently calibrated.
    double migration_proxy_ns = 30.0;
    double probe_ns = 6.27;
    double lambda = 2.0;

    double threshold =
        cas_ns +
        migration_proxy_ns +
        lambda * probe_ns;

    cout << "Uncontended lock cost : "
         << cas_ns << " ns\n";

    cout << "Stealing threshold    : "
         << threshold << " ns\n";

    Stats uncontended = run_benchmark(
        thief_cpu, victim_cpu,
        task_count, batch_limit,
        false, threshold
    );

    Stats contended = run_benchmark(
        thief_cpu, victim_cpu,
        task_count, batch_limit,
        true, threshold
    );

    print_stats("UNCONTENDED", uncontended);
    print_stats("CONTENDED", contended);

    double extra =
        median(contended.successful_ns) -
        median(uncontended.successful_ns);

    cout << "\nEstimated additional contention cost: "
         << extra << " ns\n";

    cout << "\nNote: This difference is a contention "
         << "proxy, not pure cache migration latency.\n";

    return 0;
}
