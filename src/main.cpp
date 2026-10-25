#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <fstream>
#include <future>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#else
static int omp_get_thread_num() { return 0; }
#endif

namespace {
using Clock = std::chrono::steady_clock;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
constexpr u32 EMPTY_KEY = std::numeric_limits<u32>::max();

struct DataSet { std::vector<u32> r, s; };
struct PartitionedRelation { std::vector<u32> rows; std::vector<std::size_t> offsets; };
struct PartitionedData { PartitionedRelation r, s; double seconds = 0.0; };
struct Task {
    std::size_t partition, begin, end;
    double estimated_cost_ns = 0.0;
};
struct Config {
    std::size_t r_size = 100000;
    std::size_t s_size = 1600000;
    u32 key_range = 0; // zero means the full build-key domain
    std::size_t partitions = 1024;
    int threads = 4;
    std::size_t chunk_size = 2048;
    int repeats = 3;
    double split_factor = 2.5;
    int tasks_per_thread = 32;
    int queue_batch_size = 16;
    int cost_samples = 16;
    double steal_threshold_multiplier = 1.0;
    u64 seed_r = 123456789ULL, seed_s = 987654321ULL;
    std::vector<double> skews{0.0, 0.75, 1.25};
    std::string csv_path = "results.csv";
    std::string raw_csv_path;
    bool self_test = false;
};
struct Distribution { double med=0, q1=0, q3=0, min=0, max=0, sd=0; };
struct Run {
    u64 result=0; double partition_s=0, build_s=0, probe_s=0, e2e_s=0;
    double estimate_s=0, task_plan_s=0, queue_admin_s=std::numeric_limits<double>::quiet_NaN();
    double steal_threshold_ns=0, cost_model_holdout_wape_pct=std::numeric_limits<double>::quiet_NaN();
    double build_cost_ns_per_row=0.0, probe_cost_ns_per_row=0.0;
    double cas_steal_cost_ns=0.0, cache_migration_proxy_ns=0.0, split_benefit_ns=0.0;
    std::size_t tasks=0, heavy_partitions=0, split_partitions=0;
    std::size_t steal_attempts=0, successful_steals=0, successful_steal_batches=0;
    std::size_t failed_steals=0, threshold_skips=0, steal_cas_retries=0;
    double max_partition_over_avg=0.0, worker_rows_over_avg=0.0; bool correct=false;
};

inline double seconds(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double>(b-a).count();
}

std::size_t parse_size(const std::string& s, const std::string& name) {
    if (s.empty() || s[0]=='-') throw std::invalid_argument("invalid value for " + name + ": " + s);
    std::size_t used=0; unsigned long long v=0;
    try { v=std::stoull(s, &used); } catch (...) { throw std::invalid_argument("invalid value for " + name + ": " + s); }
    if (used != s.size() || v > std::numeric_limits<std::size_t>::max()) throw std::invalid_argument("invalid value for " + name + ": " + s);
    return static_cast<std::size_t>(v);
}

int parse_int_range(const std::string& s,const std::string& name,int minimum,int maximum){
    const auto value=parse_size(s,name);
    if(value<static_cast<std::size_t>(minimum)||value>static_cast<std::size_t>(maximum))
        throw std::invalid_argument(name+" must be in ["+std::to_string(minimum)+","+std::to_string(maximum)+"]");
    return static_cast<int>(value);
}

std::vector<double> parse_skews(const std::string& s) {
    std::vector<double> out; std::stringstream ss(s); std::string tok;
    while (std::getline(ss,tok,',')) {
        std::size_t used=0; double x;
        try { x=std::stod(tok,&used); } catch (...) { throw std::invalid_argument("invalid skew: " + tok); }
        if (used != tok.size() || !std::isfinite(x) || x < 0.0 || x > 3.0)
            throw std::invalid_argument("skews must be finite and in [0,3]");
        out.push_back(x);
    }
    if (out.empty()) throw std::invalid_argument("--skews cannot be empty");
    return out;
}

Config parse_args(int argc, char** argv) {
    Config c;
    for (int i=1;i<argc;++i) {
        const std::string a=argv[i];
        if (a=="--help" || a=="-h") {
            std::cout << "Usage: hashjoin [options]\n"
                      << "  --n N                 set both relation sizes to N (legacy convenience)\n"
                      << "  --r-size R             build relation rows (default 100000)\n"
                      << "  --s-size S             probe relation rows (default 1600000; 16x R)\n"
                      << "  --key-range K         Zipf domain; defaults to R size\n"
                      << "  --partitions P        power of two with even log2, e.g. 1024\n"
                      << "  --threads T           OpenMP threads (default 4)\n"
                      << "  --chunk-size C        fixed chunks for paper-style adaptive strategy\n"
                      << "  --tasks-per-thread K  task budget multiplier for novelty (default 32)\n"
                      << "  --queue-batch-size B  private-queue batch transfer size (default 16)\n"
                      << "  --cost-samples N      probe samples per partition for cost estimation (default 16)\n"
                      << "  --steal-threshold-multiplier X  sampled probe-cost gate scale (default 1)\n"
                      << "  --split-factor X      oversized-partition threshold (default 2.5)\n"
                      << "  --repeats R           measured repeats (default 3)\n"
                      << "  --skews z,z,...       Zipf exponents (default 0,0.75,1.25)\n"
                      << "  --seed-r S --seed-s S reproducible independent seeds\n"
                      <<"  --csv PATH            aggregate output CSV (default results.csv)\n"
                      <<"  --raw-csv PATH        optional per-repetition raw measurements\n"
                      <<"  --self-test           run correctness and concurrency edge tests\n";
            std::exit(0);
        }
        if (a=="--self-test") { c.self_test=true; continue; }
        if (i+1>=argc) throw std::invalid_argument("missing value after " + a);
        const std::string v=argv[++i];
        if (a=="--n") { c.r_size=parse_size(v,a); c.s_size=c.r_size; }
        else if (a=="--r-size") c.r_size=parse_size(v,a);
        else if (a=="--s-size") c.s_size=parse_size(v,a);
        else if (a=="--key-range") { const auto x=parse_size(v,a); if (x<1 || x>=EMPTY_KEY) throw std::invalid_argument("--key-range must be in [1, UINT32_MAX-1]"); c.key_range=static_cast<u32>(x); }
        else if (a=="--partitions") c.partitions=parse_size(v,a);
        else if (a=="--threads") c.threads=parse_int_range(v,a,1,64);
        else if (a=="--chunk-size") c.chunk_size=parse_size(v,a);
        else if (a=="--tasks-per-thread") c.tasks_per_thread=parse_int_range(v,a,2,128);
        else if (a=="--queue-batch-size") c.queue_batch_size=parse_int_range(v,a,1,256);
        else if (a=="--cost-samples") c.cost_samples=parse_int_range(v,a,1,64);
        else if (a=="--steal-threshold-multiplier") {
            std::size_t used=0;
            c.steal_threshold_multiplier=std::stod(v,&used);
            if(used!=v.size())throw std::invalid_argument("invalid --steal-threshold-multiplier");
        }
        else if (a=="--split-factor") { std::size_t used=0; c.split_factor=std::stod(v,&used); if(used!=v.size()) throw std::invalid_argument("invalid --split-factor"); }
        else if (a=="--repeats") c.repeats=parse_int_range(v,a,1,1000);
        else if (a=="--skews") c.skews=parse_skews(v);
        else if (a=="--seed-r") c.seed_r=static_cast<u64>(parse_size(v,a));
        else if (a=="--seed-s") c.seed_s=static_cast<u64>(parse_size(v,a));
        else if (a=="--csv") c.csv_path=v;
        else if (a=="--raw-csv") c.raw_csv_path=v;
        else throw std::invalid_argument("unknown option: " + a);
    }
    if (c.r_size>=EMPTY_KEY) throw std::invalid_argument("--r-size must be less than UINT32_MAX");
    if (c.key_range==0) c.key_range=static_cast<u32>(std::max<std::size_t>(1,c.r_size));
    if (c.partitions<4 || (c.partitions&(c.partitions-1))!=0) throw std::invalid_argument("--partitions must be a power of two >= 4");
    int bits=0; for(std::size_t p=c.partitions;p>1;p>>=1) ++bits;
    if(bits%2!=0) throw std::invalid_argument("--partitions must have an even log2 for two equal radix passes (e.g. 1024)");
    if(c.threads<1 || c.threads>64) throw std::invalid_argument("--threads must be in [1,64]");
    if(c.chunk_size<1) throw std::invalid_argument("--chunk-size must be positive");
    if(c.tasks_per_thread<2 || c.tasks_per_thread>128) throw std::invalid_argument("--tasks-per-thread must be in [2,128]");
    if(c.queue_batch_size<1 || c.queue_batch_size>256) throw std::invalid_argument("--queue-batch-size must be in [1,256]");
    if(c.cost_samples<1 || c.cost_samples>64) throw std::invalid_argument("--cost-samples must be in [1,64]");
    if(!std::isfinite(c.steal_threshold_multiplier)
       ||c.steal_threshold_multiplier<0.25||c.steal_threshold_multiplier>64.0)
        throw std::invalid_argument("--steal-threshold-multiplier must be in [0.25,64]");
    if(c.repeats<1 || c.repeats>1000) throw std::invalid_argument("--repeats must be in [1,1000]");
    if(!std::isfinite(c.split_factor) || c.split_factor<1.0 || c.split_factor>100.0) throw std::invalid_argument("--split-factor must be in [1,100]");
#ifndef _OPENMP
    c.threads = 1;
#endif
    return c;
}

class ZipfSampler {
public:
    ZipfSampler(std::size_t n, double z): n_(n), uniform_(z<=1e-12) {
        if(uniform_) return;
        std::vector<double> scaled(n_); prob_.assign(n_,0.0); alias_.assign(n_,0);
        long double sum=0.0L;
        for(std::size_t i=0;i<n_;++i) sum += 1.0L/std::pow(static_cast<long double>(i+1),z);
        std::vector<std::size_t> small,large; small.reserve(n_); large.reserve(n_);
        for(std::size_t i=0;i<n_;++i) {
            scaled[i]=static_cast<double>((1.0L/std::pow(static_cast<long double>(i+1),z))*n_/sum);
            (scaled[i]<1.0?small:large).push_back(i);
        }
        while(!small.empty()&&!large.empty()) {
            const auto s=small.back();small.pop_back();const auto l=large.back();large.pop_back();
            prob_[s]=scaled[s];alias_[s]=l;scaled[l]=(scaled[l]+scaled[s])-1.0;
            (scaled[l]<1.0?small:large).push_back(l);
        }
        for (auto i : large) prob_[i] = 1.0;
        for (auto i : small) prob_[i] = 1.0;
    }
    template<class RNG> u32 sample(RNG& rng) const {
        std::uniform_int_distribution<std::size_t> d(0,n_-1); const auto col=d(rng);
        if(uniform_) return static_cast<u32>(col);
        return static_cast<u32>(std::generate_canonical<double,53>(rng)<prob_[col]?col:alias_[col]);
    }
private: std::size_t n_; bool uniform_; std::vector<double> prob_; std::vector<std::size_t> alias_;
};

DataSet generate_data(const Config& c,double skew) {
    DataSet d; d.r.resize(c.r_size); d.s.resize(c.s_size);
    std::mt19937_64 rr(c.seed_r),rs(c.seed_s);
    std::iota(d.r.begin(), d.r.end(), u32{0});
    std::shuffle(d.r.begin(), d.r.end(), rr); // primary-key build relation: keys are unique
    ZipfSampler zs(c.key_range,skew);
    for(auto& x:d.s) x=zs.sample(rs);
    return d;
}

std::size_t log2_exact(std::size_t x) {
    std::size_t b=0;while(x>1){x>>=1;++b;}return b;
}

// Two-pass parallel radix partitioning: per-thread histograms, prefix offsets,
// and lock-free disjoint scatter ranges. Output partition id = high_bits * fanout + low_bits.
PartitionedRelation radix_partition_2pass(const std::vector<u32>& input,std::size_t pcount,int threads) {
    const int total_bits=static_cast<int>(log2_exact(pcount));
    const int bits=total_bits/2;
    const std::size_t fanout=std::size_t{1}<<bits;
    const u32 mask=static_cast<u32>(fanout-1);
    const std::size_t n=input.size();

    std::vector<std::vector<std::size_t>> h1(static_cast<std::size_t>(threads),std::vector<std::size_t>(fanout,0));
#ifdef _OPENMP
#pragma omp parallel num_threads(threads)
#endif
    {
        const int tid=omp_get_thread_num();
        const std::size_t begin=n*static_cast<std::size_t>(tid)/static_cast<std::size_t>(threads);
        const std::size_t end=n*static_cast<std::size_t>(tid+1)/static_cast<std::size_t>(threads);
        auto& h=h1[static_cast<std::size_t>(tid)];
        for(std::size_t i=begin;i<end;++i) ++h[input[i]&mask];
    }
    std::vector<std::vector<std::size_t>> start1(static_cast<std::size_t>(threads),std::vector<std::size_t>(fanout,0));
    std::size_t base=0;
    for(std::size_t b=0;b<fanout;++b){
        std::size_t at=base;
        for(int t=0;t<threads;++t){start1[static_cast<std::size_t>(t)][b]=at;at+=h1[static_cast<std::size_t>(t)][b];}
        base=at;
    }
    std::vector<u32> stage1(n);
#ifdef _OPENMP
#pragma omp parallel num_threads(threads)
#endif
    {
        const int tid=omp_get_thread_num();const std::size_t begin=n*static_cast<std::size_t>(tid)/static_cast<std::size_t>(threads);
        const std::size_t end=n*static_cast<std::size_t>(tid+1)/static_cast<std::size_t>(threads);
        auto cursor=start1[static_cast<std::size_t>(tid)];
        for(std::size_t i=begin;i<end;++i){const auto b=static_cast<std::size_t>(input[i]&mask);stage1[cursor[b]++]=input[i];}
    }

    // Each (low radix bucket, first-pass worker) is a contiguous independent segment.
    const std::size_t nsegments=fanout*static_cast<std::size_t>(threads);
    std::vector<std::vector<std::size_t>> h2(nsegments,std::vector<std::size_t>(fanout,0));
#ifdef _OPENMP
#pragma omp parallel for schedule(dynamic,1) num_threads(threads)
#endif
    for(long long si=0;si<static_cast<long long>(nsegments);++si){
        const std::size_t seg=static_cast<std::size_t>(si), low=seg/static_cast<std::size_t>(threads), t=seg%static_cast<std::size_t>(threads);
        const std::size_t begin=start1[t][low], len=h1[t][low], end=begin+len;
        auto& h=h2[seg];for(std::size_t i=begin;i<end;++i) ++h[(stage1[i]>>bits)&mask];
    }
    PartitionedRelation out;out.rows.resize(n);out.offsets.assign(pcount+1,0);
    for(std::size_t high=0;high<fanout;++high){
        for(std::size_t low=0;low<fanout;++low){
            const std::size_t p=high*fanout+low;std::size_t count=0;
            for(int t=0;t<threads;++t) count+=h2[low*static_cast<std::size_t>(threads)+static_cast<std::size_t>(t)][high];
            out.offsets[p+1]=count;
        }
    }
    for(std::size_t p=1;p<out.offsets.size();++p) out.offsets[p]+=out.offsets[p-1];
    std::vector<std::vector<std::size_t>> start2(nsegments,std::vector<std::size_t>(fanout,0));
    for(std::size_t low=0;low<fanout;++low){
        for(std::size_t high=0;high<fanout;++high){
            const std::size_t p=high*fanout+low;std::size_t at=out.offsets[p];
            for(int t=0;t<threads;++t){const std::size_t seg=low*static_cast<std::size_t>(threads)+static_cast<std::size_t>(t);start2[seg][high]=at;at+=h2[seg][high];}
        }
    }
#ifdef _OPENMP
#pragma omp parallel for schedule(dynamic,1) num_threads(threads)
#endif
    for(long long si=0;si<static_cast<long long>(nsegments);++si){
        const std::size_t seg=static_cast<std::size_t>(si),low=seg/static_cast<std::size_t>(threads),t=seg%static_cast<std::size_t>(threads);
        const std::size_t begin=start1[t][low],end=begin+h1[t][low];auto cursor=start2[seg];
        for(std::size_t i=begin;i<end;++i){const std::size_t high=(stage1[i]>>bits)&mask;out.rows[cursor[high]++]=stage1[i];}
    }
    if(out.offsets.back()!=n) throw std::runtime_error("radix partition lost rows");
    return out;
}

PartitionedData partition_data(const DataSet& d,const Config& c){
    const auto st=Clock::now();PartitionedData p;
    p.r=radix_partition_2pass(d.r,c.partitions,c.threads);
    p.s=radix_partition_2pass(d.s,c.partitions,c.threads);
    p.seconds=seconds(st,Clock::now());return p;
}

u64 reference_join_count(const DataSet& d){
    std::unordered_map<u32,u64> f;f.reserve(d.r.size());for(u32 k:d.r)++f[k];u64 out=0;
    for(u32 k:d.s){const auto it=f.find(k);if(it!=f.end())out+=it->second;}return out;
}

std::size_t next_power_two(std::size_t x){
    if (x <= 2) return 2;
    --x;
    for (std::size_t s=1; s<sizeof(x)*8; s<<=1) x |= x>>s;
    if (x == std::numeric_limits<std::size_t>::max()) throw std::overflow_error("hash table capacity overflow");
    return x+1;
}
inline u32 hash_key(u32 x){x^=x>>16;x*=0x7feb352dU;x^=x>>15;x*=0x846ca68bU;x^=x>>16;return x;}
struct HashTable{
    std::vector<u32> keys;std::vector<u64> counts;std::size_t mask=0;
    void init(std::size_t n){if(n==0){keys.clear();counts.clear();mask=0;return;}const auto cap=next_power_two(n*2+1);keys.assign(cap,EMPTY_KEY);counts.assign(cap,0);mask=cap-1;}
    void add(u32 key){std::size_t i=static_cast<std::size_t>(hash_key(key))&mask;while(keys[i]!=EMPTY_KEY&&keys[i]!=key)i=(i+1)&mask;if(keys[i]==EMPTY_KEY){keys[i]=key;counts[i]=1;}else ++counts[i];}
    u64 get(u32 key)const{if(keys.empty())return 0;std::size_t i=static_cast<std::size_t>(hash_key(key))&mask;while(keys[i]!=EMPTY_KEY){if(keys[i]==key)return counts[i];i=(i+1)&mask;}return 0;}
    std::pair<u64,std::size_t> get_with_probe_count(u32 key)const{
        if(keys.empty())return {0,1};
        std::size_t i=static_cast<std::size_t>(hash_key(key))&mask,probes=0;
        while(keys[i]!=EMPTY_KEY){++probes;if(keys[i]==key)return {counts[i],probes};i=(i+1)&mask;}
        return {0,probes+1};
    }
};

struct PreparedData { PartitionedData part; std::vector<HashTable> tables; double build_s = 0.0; };

std::vector<HashTable> build_tables(const PartitionedData& p,const Config& c,double& build_s){
    const auto st=Clock::now();std::vector<HashTable> tables(c.partitions);
#ifdef _OPENMP
#pragma omp parallel for schedule(static) num_threads(c.threads)
#endif
    for(long long pi=0;pi<static_cast<long long>(c.partitions);++pi){
        const std::size_t i=static_cast<std::size_t>(pi),b=p.r.offsets[i],e=p.r.offsets[i+1];auto& t=tables[i];
        t.init(e-b);for(std::size_t j=b;j<e;++j)t.add(p.r.rows[j]);
    }
    build_s=seconds(st,Clock::now());return tables;
}

PreparedData prepare_data(const DataSet& data,const Config& c){
    PreparedData prepared;prepared.part=partition_data(data,c);
    prepared.tables=build_tables(prepared.part,c,prepared.build_s);
    return prepared;
}

u64 probe_range(const PartitionedData& p,const std::vector<HashTable>& tables,std::size_t part,std::size_t begin,std::size_t end){
    const std::size_t abs=p.s.offsets[part]+begin;const std::size_t limit=std::min(end,p.s.offsets[part+1]-p.s.offsets[part]);u64 sum=0;
    for(std::size_t i=begin;i<limit;++i)sum+=tables[part].get(p.s.rows[abs+i-begin]);
    return sum;
}

std::vector<Task> make_tasks(const PartitionedData& p,std::size_t chunk_size,bool adaptive,double split_factor,std::size_t& heavy){
    const auto pc=p.s.offsets.size()-1;std::size_t n=p.s.rows.size();const double average=static_cast<double>(n)/static_cast<double>(pc);
    std::vector<Task> tasks;heavy=0;
    for(std::size_t i=0;i<pc;++i){const std::size_t len=p.s.offsets[i+1]-p.s.offsets[i];
        const bool split=adaptive&&len>split_factor*average&&chunk_size<=len/2;
        if(split){
            ++heavy;
        for(std::size_t b=0;b<len;){
            const std::size_t end=b+std::min(chunk_size,len-b);
            tasks.push_back({i,b,end});b=end;
        }
        }
        else if(len)tasks.push_back({i,0,len});
    }
    return tasks;
}

std::vector<Task> make_budgeted_tasks(const PartitionedData& p,const Config& c,std::size_t& heavy,std::size_t& split_count){
    const std::size_t pc=p.s.offsets.size()-1;
    const double avg=static_cast<double>(p.s.rows.size())/static_cast<double>(pc);
    std::vector<std::pair<std::size_t,std::size_t>> candidates; // (partition, probe rows)
    for(std::size_t i=0;i<pc;++i){
        const std::size_t len=p.s.offsets[i+1]-p.s.offsets[i];
        if(len>c.split_factor*avg && c.chunk_size<=len/2) candidates.push_back({i,len});
    }
    heavy=candidates.size();split_count=0;
    std::sort(candidates.begin(),candidates.end(),[](const auto& a,const auto& b){
        if(a.second!=b.second)return a.second>b.second;
        return a.first<b.first;
    });
    const std::size_t budget=static_cast<std::size_t>(c.threads*c.tasks_per_thread);
    // Reserve only one quarter of the task budget as the number of candidate
    // partitions. The remaining budget can then be distributed in proportion to
    // partition size, rather than degenerating into exactly two pieces per partition.
    const std::size_t selected_count=std::min(candidates.size(),std::max<std::size_t>(1,budget/4));
    std::vector<std::size_t> allocated(candidates.size(),0);
    if(selected_count>0){
        std::size_t total=0;
        for(std::size_t j=0;j<selected_count;++j)total+=candidates[j].second;
        for(std::size_t j=0;j<selected_count;++j)allocated[j]=2;
        std::size_t remaining=budget-2*selected_count;
        std::vector<std::pair<double,std::size_t>> remainders;
        std::size_t assigned=0;
        for(std::size_t j=0;j<selected_count;++j){
            const double exact=static_cast<double>(remaining)*static_cast<double>(candidates[j].second)/static_cast<double>(total);
            const auto whole=static_cast<std::size_t>(std::floor(exact));
            allocated[j]+=whole;assigned+=whole;remainders.push_back({exact-static_cast<double>(whole),j});
        }
        std::sort(remainders.begin(),remainders.end(),[](const auto& a,const auto& b){
            if(a.first!=b.first)return a.first>b.first;
            return a.second<b.second;
        });
        for(std::size_t j=0;j<remaining-assigned;++j)++allocated[remainders[j].second];
    }
    std::vector<std::size_t> per_partition_chunk(pc,0);
    split_count=selected_count;
    for(std::size_t j=0;j<selected_count;++j){
        const auto part=candidates[j].first,len=candidates[j].second;
        const std::size_t target=std::max<std::size_t>(2,allocated[j]);
        per_partition_chunk[part]=std::max(c.chunk_size,len/target+(len%target!=0));
    }
    std::vector<Task> tasks;
    for(std::size_t i=0;i<pc;++i){
        const std::size_t len=p.s.offsets[i+1]-p.s.offsets[i];if(!len)continue;
        const std::size_t chunk=per_partition_chunk[i];
        if(chunk>0){
            for(std::size_t b=0;b<len;){
                const std::size_t end=b+std::min(chunk,len-b);
                tasks.push_back({i,b,end});b=end;
            }
        }else tasks.push_back({i,0,len});
    }
    return tasks;
}

struct CostModel {
    std::vector<double> partition_cost_per_row_ns;
    double build_cost_ns_per_row=0.0;
    double probe_cost_ns_per_row=0.0;
    double cas_steal_cost_ns=0.0;
    double cache_migration_proxy_ns=0.0;
    double steal_threshold_ns=0.0;
    double dispatch_cost_ns=0.0;
    double estimate_s=0.0;
    double validation_wape_pct=std::numeric_limits<double>::quiet_NaN();
};

struct SpinMutex {
    std::atomic_flag flag=ATOMIC_FLAG_INIT;

    void lock(std::size_t* retries=nullptr){
        while(flag.test_and_set(std::memory_order_acquire)){
            if(retries)++(*retries);
        }
    }

    void unlock(){flag.clear(std::memory_order_release);}
};

class SpinLockGuard {
public:
    explicit SpinLockGuard(SpinMutex& lock,std::size_t* retries=nullptr):lock_(lock){lock_.lock(retries);}
    ~SpinLockGuard(){lock_.unlock();}
    SpinLockGuard(const SpinLockGuard&)=delete;
    SpinLockGuard& operator=(const SpinLockGuard&)=delete;
private:
    SpinMutex& lock_;
};

struct SchedulerCostCalibration {
    double cas_steal_ns=0.0;
    double cache_migration_proxy_ns=0.0;
    double queue_operation_ns=0.0;
};

const SchedulerCostCalibration& scheduler_cost_calibration(){
    static const SchedulerCostCalibration calibration=[]{
        constexpr std::size_t iterations=4096;
        SpinMutex lock;
        std::vector<double> cas_samples,contention_samples;
        cas_samples.reserve(5);
        contention_samples.reserve(5);
        for(std::size_t sample=0;sample<5;++sample){
            const auto started=Clock::now();
            for(std::size_t i=0;i<iterations;++i){
                SpinLockGuard guard(lock);
            }
            cas_samples.push_back(std::chrono::duration<double,std::nano>(
                Clock::now()-started).count()/static_cast<double>(iterations));
        }
        for(std::size_t sample=0;sample<5;++sample){
            const auto started=Clock::now();
#ifdef _OPENMP
#pragma omp parallel num_threads(2)
#endif
            {
                for(std::size_t i=0;i<iterations;++i){
                    SpinLockGuard guard(lock);
                }
            }
            contention_samples.push_back(std::chrono::duration<double,std::nano>(
                Clock::now()-started).count()/(2.0*static_cast<double>(iterations)));
        }
        auto median=[](std::vector<double>& values){
            std::sort(values.begin(),values.end());
            return values[values.size()/2];
        };
        SchedulerCostCalibration result;
        result.cas_steal_ns=median(cas_samples);
        result.cache_migration_proxy_ns=std::max(0.0,median(contention_samples)-result.cas_steal_ns);

        std::deque<Task> queue;
        for(std::size_t i=0;i<64;++i)queue.push_back({0,0,1,0.0});
        const auto queue_started=Clock::now();
        for(std::size_t i=0;i<iterations;++i){
            queue.push_back(queue.front());
            queue.pop_front();
        }
        result.queue_operation_ns=std::chrono::duration<double,std::nano>(
            Clock::now()-queue_started).count()/static_cast<double>(iterations);
        return result;
    }();
    return calibration;
}

CostModel estimate_partition_costs(const PartitionedData& part,const std::vector<HashTable>& tables,
                                   const Config& c,double build_s){
    const auto started=Clock::now();
    const std::size_t count=part.s.offsets.size()-1;
    std::vector<double> sampled_steps(count,0.0);
    std::vector<std::size_t> sampled_counts(count,0);
    std::vector<double> validation_steps(count,0.0);
    std::vector<std::size_t> validation_counts(count,0);
    std::size_t total_steps=0;
    const double average_rows=static_cast<double>(part.s.rows.size())/static_cast<double>(count);
    for(std::size_t i=0;i<count;++i){
        const std::size_t begin=part.s.offsets[i],len=part.s.offsets[i+1]-begin;
        if(len<=c.split_factor*average_rows||c.chunk_size>len/2)continue;
        const std::size_t samples=std::min<std::size_t>(static_cast<std::size_t>(c.cost_samples),len/2);
        std::size_t steps=0,held_out_steps=0;
        for(std::size_t j=0;j<samples;++j){
            const std::size_t denominator=2*samples;
            const std::size_t estimate_at=begin+(2*j*len)/denominator;
            const std::size_t validation_at=begin+((2*j+1)*len)/denominator;
            steps+=tables[i].get_with_probe_count(part.s.rows[estimate_at]).second;
            held_out_steps+=tables[i].get_with_probe_count(part.s.rows[validation_at]).second;
        }
        sampled_steps[i]=static_cast<double>(steps)/static_cast<double>(samples);
        sampled_counts[i]=samples;
        validation_steps[i]=static_cast<double>(held_out_steps)/static_cast<double>(samples);
        validation_counts[i]=samples;
        total_steps+=steps;
    }
    std::size_t profiled_rows=0;
    u64 observed_result=0;
    constexpr std::size_t probe_timing_repetitions=16;
    const auto calibration_started=Clock::now();
    for(std::size_t repetition=0;repetition<probe_timing_repetitions;++repetition){
        for(std::size_t i=0;i<count;++i){
            if(sampled_counts[i]==0)continue;
            observed_result+=probe_range(part,tables,i,0,sampled_counts[i]);
            if(repetition==0)profiled_rows+=sampled_counts[i];
        }
    }
    const double measured_lookup_ns=profiled_rows==0?0.0
        :std::chrono::duration<double,std::nano>(Clock::now()-calibration_started).count()
            /(static_cast<double>(profiled_rows)*static_cast<double>(probe_timing_repetitions));
    volatile u64 sink=observed_result;
    (void)sink;
    const double average_steps=profiled_rows==0?0.0
        :static_cast<double>(total_steps)/static_cast<double>(profiled_rows);

    const SchedulerCostCalibration& scheduler_costs=scheduler_cost_calibration();

    CostModel model;
    model.partition_cost_per_row_ns.assign(count,measured_lookup_ns);
    model.build_cost_ns_per_row=part.r.rows.empty()?0.0
        :build_s*1e9/static_cast<double>(part.r.rows.size());
    model.probe_cost_ns_per_row=measured_lookup_ns;
    model.cas_steal_cost_ns=scheduler_costs.cas_steal_ns;
    model.cache_migration_proxy_ns=scheduler_costs.cache_migration_proxy_ns;
    model.dispatch_cost_ns=scheduler_costs.queue_operation_ns;
    model.steal_threshold_ns=scheduler_costs.cas_steal_ns
        +scheduler_costs.cache_migration_proxy_ns
        +c.steal_threshold_multiplier*measured_lookup_ns;
    double weighted_error=0.0,held_out_work=0.0;
    for(std::size_t i=0;i<count;++i){
        if(sampled_counts[i]>0&&average_steps>0.0)
            model.partition_cost_per_row_ns[i]=sampled_steps[i]*measured_lookup_ns/average_steps;
        if(validation_counts[i]>0){
            const double rows=static_cast<double>(part.s.offsets[i+1]-part.s.offsets[i]);
            weighted_error+=std::abs(sampled_steps[i]-validation_steps[i])*rows;
            held_out_work+=validation_steps[i]*rows;
        }
    }
    if(held_out_work>0.0)model.validation_wape_pct=100.0*weighted_error/held_out_work;
    model.estimate_s=seconds(started,Clock::now());
    return model;
}

std::vector<Task> make_cost_aware_tasks(const PartitionedData& part,const Config& c,
                                       const CostModel& model,std::size_t& heavy,
                                       std::size_t& split_count,double& predicted_benefit_ns){
    const std::size_t pc=part.s.offsets.size()-1;
    struct Candidate { std::size_t partition, rows; double combined_cost, probe_cost; };
    std::vector<Candidate> candidates;
    for(std::size_t i=0;i<pc;++i){
        const std::size_t len=part.s.offsets[i+1]-part.s.offsets[i];
        const std::size_t build_rows=part.r.offsets[i+1]-part.r.offsets[i];
        const double probe_cost=model.partition_cost_per_row_ns[i]*static_cast<double>(len);
        const double combined_cost=model.build_cost_ns_per_row*static_cast<double>(build_rows)
                                   +probe_cost;
        if(len>c.split_factor*static_cast<double>(part.s.rows.size())/static_cast<double>(pc)
           &&c.chunk_size<=len/2)
            candidates.push_back({i,len,combined_cost,probe_cost});
    }
    heavy=candidates.size();
    std::sort(candidates.begin(),candidates.end(),[](const Candidate& a,const Candidate& b){
        if(a.combined_cost!=b.combined_cost)return a.combined_cost>b.combined_cost;
        return a.partition<b.partition;
    });
    const std::size_t budget=static_cast<std::size_t>(c.threads*c.tasks_per_thread);
    const std::size_t selected=std::min(candidates.size(),std::max<std::size_t>(1,budget/4));
    std::vector<std::size_t> allocation(selected,2);
    if(selected>0){
        double selected_cost=0.0;
        for(std::size_t i=0;i<selected;++i)selected_cost+=candidates[i].combined_cost;
        const std::size_t remaining=budget-2*selected;
        std::vector<std::pair<double,std::size_t>> remainders;
        std::size_t assigned=0;
        for(std::size_t i=0;i<selected;++i){
            const double exact=selected_cost>0.0
                ?static_cast<double>(remaining)*candidates[i].combined_cost/selected_cost
                :static_cast<double>(remaining)/static_cast<double>(selected);
            const auto whole=static_cast<std::size_t>(std::floor(exact));
            allocation[i]+=whole;
            assigned+=whole;
            remainders.push_back({exact-static_cast<double>(whole),i});
        }
        std::sort(remainders.begin(),remainders.end(),[](const auto& a,const auto& b){
            if(a.first!=b.first)return a.first>b.first;
            return a.second<b.second;
        });
        for(std::size_t i=0;i<remaining-assigned;++i)++allocation[remainders[i].second];
    }
    std::vector<std::size_t> chunk_for(pc,0);
    split_count=selected;
    predicted_benefit_ns=0.0;
    for(std::size_t i=0;i<selected;++i){
        const auto& candidate=candidates[i];
        const std::size_t target=std::max<std::size_t>(2,allocation[i]);
        const std::size_t useful_chunks=std::min<std::size_t>(
            target,static_cast<std::size_t>(c.threads));
        const double benefit=candidate.probe_cost
            *(1.0-1.0/static_cast<double>(std::max<std::size_t>(1,useful_chunks)));
        const double split_overhead=static_cast<double>(target-1)*model.dispatch_cost_ns;
        if(benefit<=split_overhead){
            --split_count;
            continue;
        }
        predicted_benefit_ns+=benefit-split_overhead;
        const std::size_t even_chunk=candidate.rows/target+(candidate.rows%target!=0);
        chunk_for[candidate.partition]=std::max(c.chunk_size,even_chunk);
    }
    std::vector<Task> tasks;
    for(std::size_t i=0;i<pc;++i){
        const std::size_t begin=part.s.offsets[i],len=part.s.offsets[i+1]-begin;
        if(len==0)continue;
        const std::size_t chunk=chunk_for[i];
        const double per_row=model.partition_cost_per_row_ns[i];
        if(chunk==0)tasks.push_back({i,0,len,per_row*static_cast<double>(len)});
        else for(std::size_t b=0;b<len;){
            const std::size_t end=b+std::min(chunk,len-b);
            tasks.push_back({i,b,end,per_row*static_cast<double>(end-b)});
            b=end;
        }
    }
    return tasks;
}

bool has_split_candidate(const PartitionedData& part,const Config& c){
    const std::size_t pc=part.s.offsets.size()-1;
    const double average=static_cast<double>(part.s.rows.size())/static_cast<double>(pc);
    for(std::size_t i=0;i<pc;++i){
        const std::size_t len=part.s.offsets[i+1]-part.s.offsets[i];
        if(len>c.split_factor*average&&c.chunk_size<=len/2)return true;
    }
    return false;
}

struct WorkerStats {
    u64 result=0;
    std::size_t rows=0,steal_attempts=0,successful_steals=0,successful_steal_batches=0;
    std::size_t steal_cas_retries=0;
    std::size_t failed_steals=0,threshold_skips=0;
    double queue_admin_ns=0.0;
    std::deque<Task> local_tasks;
};

struct WorkerQueue {
    std::deque<Task> tasks;
    SpinMutex mutex;
    double remaining_cost_ns=0.0;
};

void execute_private_queues(const PartitionedData& part,const std::vector<HashTable>& tables,
                            const Config& c,const std::vector<Task>& tasks,bool allow_steals,
                            bool gate_steals,double threshold_ns,Run& out){
    const auto setup_started=Clock::now();
    const std::size_t thread_count=static_cast<std::size_t>(c.threads);
    std::vector<std::unique_ptr<WorkerQueue>> queues;
    queues.reserve(thread_count);
    for(std::size_t i=0;i<thread_count;++i)queues.push_back(std::unique_ptr<WorkerQueue>(new WorkerQueue));
    std::vector<Task> ordered_tasks=tasks;
    std::stable_sort(ordered_tasks.begin(),ordered_tasks.end(),[](const Task& left,const Task& right){
        if(left.estimated_cost_ns!=right.estimated_cost_ns)
            return left.estimated_cost_ns>right.estimated_cost_ns;
        if(left.partition!=right.partition)return left.partition<right.partition;
        return left.begin<right.begin;
    });
    for(const Task& task:ordered_tasks){
        const auto owner=static_cast<std::size_t>(std::min_element(
            queues.begin(),queues.end(),[](const auto& left,const auto& right){
                if(left->remaining_cost_ns!=right->remaining_cost_ns)
                    return left->remaining_cost_ns<right->remaining_cost_ns;
                return left->tasks.size()<right->tasks.size();
            })-queues.begin());
        WorkerQueue& queue=*queues[owner];
        queue.tasks.push_back(task);
        queue.remaining_cost_ns+=task.estimated_cost_ns;
    }
    out.task_plan_s+=seconds(setup_started,Clock::now());
    std::vector<WorkerStats> workers(thread_count);
    const bool use_private_static=!allow_steals;
    const auto probe_started=Clock::now();
    if(use_private_static){
#ifdef _OPENMP
#pragma omp parallel num_threads(c.threads)
#endif
        {
            const std::size_t tid=static_cast<std::size_t>(omp_get_thread_num());
            WorkerStats& stats=workers[tid];
            for(const Task& task:queues[tid]->tasks){
                stats.result+=probe_range(part,tables,task.partition,task.begin,task.end);
                stats.rows+=task.end-task.begin;
            }
        }
        out.probe_s=seconds(probe_started,Clock::now());
        std::size_t max_rows=0;
        for(const WorkerStats& worker:workers){
            out.result+=worker.result;
            max_rows=std::max(max_rows,worker.rows);
        }
        out.queue_admin_s=0.0;
        const double mean_rows=static_cast<double>(part.s.rows.size())/static_cast<double>(thread_count);
        out.worker_rows_over_avg=mean_rows>0.0?static_cast<double>(max_rows)/mean_rows:0.0;
        return;
    }
#ifdef _OPENMP
#pragma omp parallel num_threads(c.threads)
#endif
    {
        const std::size_t tid=static_cast<std::size_t>(omp_get_thread_num());
        WorkerStats& stats=workers[tid];
        std::size_t victim_shift=0;
        for(;;){
            Task task{};
            bool found=false;
            if(!stats.local_tasks.empty()){
                task=stats.local_tasks.back();
                stats.local_tasks.pop_back();
                found=true;
            }else{
                auto queue_started=Clock::now();
                {
                    WorkerQueue& local=*queues[tid];
                    SpinLockGuard lock(local.mutex);
                    const std::size_t batch=std::min<std::size_t>(
                        static_cast<std::size_t>(c.queue_batch_size),
                        std::max<std::size_t>(1,(local.tasks.size()+1)/2));
                    for(std::size_t i=0;i<batch&&!local.tasks.empty();++i){
                        stats.local_tasks.push_back(local.tasks.back());
                        local.remaining_cost_ns-=local.tasks.back().estimated_cost_ns;
                        local.tasks.pop_back();
                    }
                }
                stats.queue_admin_ns+=std::chrono::duration<double,std::nano>(Clock::now()-queue_started).count();
                if(!stats.local_tasks.empty()){
                    task=stats.local_tasks.back();
                    stats.local_tasks.pop_back();
                    found=true;
                }
            }
            if(!found&&allow_steals&&thread_count>1){
                const std::size_t first=(tid+1+victim_shift)%thread_count;
                for(std::size_t offset=0;offset<thread_count-1&&!found;++offset){
                    const std::size_t victim=(first+offset)%thread_count;
                    if(victim==tid)continue;
                    const auto queue_started=Clock::now();
                    WorkerQueue& remote=*queues[victim];
                    {
                        SpinLockGuard lock(remote.mutex,&stats.steal_cas_retries);
                        ++stats.steal_attempts;
                        if(remote.tasks.empty())++stats.failed_steals;
                        else if(gate_steals&&(remote.remaining_cost_ns<=threshold_ns
                                           ||remote.tasks.front().estimated_cost_ns<=threshold_ns))
                            ++stats.threshold_skips;
                        else{
                            const std::size_t batch=std::min<std::size_t>(
                                static_cast<std::size_t>(c.queue_batch_size),
                                std::max<std::size_t>(1,(remote.tasks.size()+1)/2));
                            for(std::size_t i=0;i<batch&&!remote.tasks.empty();++i){
                                stats.local_tasks.push_back(remote.tasks.front());
                                remote.remaining_cost_ns-=remote.tasks.front().estimated_cost_ns;
                                remote.tasks.pop_front();
                                ++stats.successful_steals;
                            }
                            if(!stats.local_tasks.empty()){
                                ++stats.successful_steal_batches;
                                task=stats.local_tasks.back();
                                stats.local_tasks.pop_back();
                                found=true;
                            }
                        }
                    }
                    stats.queue_admin_ns+=std::chrono::duration<double,std::nano>(Clock::now()-queue_started).count();
                }
                ++victim_shift;
            }
            if(!found)break;
            stats.result+=probe_range(part,tables,task.partition,task.begin,task.end);
            stats.rows+=task.end-task.begin;
        }
    }
    out.probe_s=seconds(probe_started,Clock::now());
    double queue_ns=0.0;
    for(const WorkerStats& worker:workers){
        out.result+=worker.result;
        out.steal_attempts+=worker.steal_attempts;
        out.successful_steals+=worker.successful_steals;
        out.successful_steal_batches+=worker.successful_steal_batches;
        out.steal_cas_retries+=worker.steal_cas_retries;
        out.failed_steals+=worker.failed_steals;
        out.threshold_skips+=worker.threshold_skips;
        queue_ns+=worker.queue_admin_ns;
    }
    out.queue_admin_s=queue_ns/1e9;
    const double mean_rows=static_cast<double>(part.s.rows.size())/static_cast<double>(thread_count);
    std::size_t max_rows=0;
    for(const WorkerStats& worker:workers)max_rows=std::max(max_rows,worker.rows);
    out.worker_rows_over_avg=mean_rows>0.0?static_cast<double>(max_rows)/mean_rows:0.0;
}

Run execute_prepared(const PreparedData& prepared,const Config& c,const std::string& algorithm,u64 expected){
    Run out;const auto& part=prepared.part;const auto& tables=prepared.tables;
    out.partition_s=part.seconds;out.build_s=prepared.build_s;
    const auto planning_started=Clock::now();
    const double avg_partition=static_cast<double>(part.s.rows.size())/static_cast<double>(c.partitions);
    std::size_t max_partition=0;
    for(std::size_t i=0;i<c.partitions;++i)max_partition=std::max(max_partition,part.s.offsets[i+1]-part.s.offsets[i]);
    out.max_partition_over_avg=avg_partition>0?static_cast<double>(max_partition)/avg_partition:0.0;
    std::vector<std::size_t> worker_rows(static_cast<std::size_t>(c.threads),0);
    u64 result=0;
    const bool cost_aware=algorithm=="cost_aware_no_steal"
                       ||algorithm=="cost_aware_ungated_steal"
                       ||algorithm=="novelty_cost_gated_steal";
    CostModel model;
    std::vector<Task> tasks;
    bool fallback_coarse=false;
    if(cost_aware){
        if(algorithm=="novelty_cost_gated_steal"){
            const auto gate_started=Clock::now();
            fallback_coarse=!has_split_candidate(part,c);
            out.estimate_s=seconds(gate_started,Clock::now());
        }
        if(fallback_coarse){
            tasks=make_tasks(part,1,false,c.split_factor,out.heavy_partitions);
        }else{
            model=estimate_partition_costs(part,tables,c,prepared.build_s);
            out.estimate_s+=model.estimate_s;
            out.steal_threshold_ns=model.steal_threshold_ns;
            out.cost_model_holdout_wape_pct=model.validation_wape_pct;
            out.build_cost_ns_per_row=model.build_cost_ns_per_row;
            out.probe_cost_ns_per_row=model.probe_cost_ns_per_row;
            out.cas_steal_cost_ns=model.cas_steal_cost_ns;
            out.cache_migration_proxy_ns=model.cache_migration_proxy_ns;
            tasks=make_cost_aware_tasks(part,c,model,out.heavy_partitions,out.split_partitions,
                                        out.split_benefit_ns);
        }
    }else if(algorithm=="radix_dynamic_coarse")
        tasks=make_tasks(part,part.s.rows.size()+1,false,c.split_factor,out.heavy_partitions);
    else if(algorithm=="paper_fine_grained"){
        tasks=make_tasks(part,c.chunk_size,true,c.split_factor,out.heavy_partitions);
        out.split_partitions=out.heavy_partitions;
    }else if(algorithm=="novelty_budgeted")
        tasks=make_budgeted_tasks(part,c,out.heavy_partitions,out.split_partitions);
    else if(algorithm=="fine_grained_all")
        tasks=make_tasks(part,c.chunk_size,false,c.split_factor,out.heavy_partitions);
    else if(algorithm!="radix_static")
        throw std::invalid_argument("unknown algorithm: "+algorithm);
    out.task_plan_s=seconds(planning_started,Clock::now())-out.estimate_s;
    out.tasks=algorithm=="radix_static"?c.partitions:tasks.size();

    if(algorithm=="radix_static"){
        const auto allocation_started=Clock::now();
        std::vector<u64> sums(c.partitions,0);
        out.task_plan_s+=seconds(allocation_started,Clock::now());
        const auto p0=Clock::now();
#ifdef _OPENMP
#pragma omp parallel for schedule(static) num_threads(c.threads)
#endif
        for(long long pi=0;pi<static_cast<long long>(c.partitions);++pi){const auto i=static_cast<std::size_t>(pi);const auto len=part.s.offsets[i+1]-part.s.offsets[i];sums[i]=probe_range(part,tables,i,0,len);worker_rows[static_cast<std::size_t>(omp_get_thread_num())]+=len;}
        out.probe_s=seconds(p0,Clock::now());
        const auto aggregate_started=Clock::now();
        result=std::accumulate(sums.begin(),sums.end(),u64{0});
        out.task_plan_s+=seconds(aggregate_started,Clock::now());
    }else if(cost_aware&&!fallback_coarse){
        const bool allow_steals=algorithm!="cost_aware_no_steal";
        const bool gate_steals=algorithm=="novelty_cost_gated_steal";
        execute_private_queues(part,tables,c,tasks,allow_steals,gate_steals,
                               model.steal_threshold_ns,out);
        result=out.result;
    }else{
        const auto allocation_started=Clock::now();
        std::vector<u64> sums(tasks.size(),0);
        out.task_plan_s+=seconds(allocation_started,Clock::now());
        const auto p0=Clock::now();
#ifdef _OPENMP
#pragma omp parallel for schedule(dynamic,1) num_threads(c.threads)
#endif
        for(long long ti=0;ti<static_cast<long long>(tasks.size());++ti){
            const auto& t=tasks[static_cast<std::size_t>(ti)];const auto len=t.end-t.begin;
            sums[static_cast<std::size_t>(ti)]=probe_range(part,tables,t.partition,t.begin,t.end);
            worker_rows[static_cast<std::size_t>(omp_get_thread_num())]+=len;
        }
        out.probe_s=seconds(p0,Clock::now());
        const auto aggregate_started=Clock::now();
        result=std::accumulate(sums.begin(),sums.end(),u64{0});
        out.task_plan_s+=seconds(aggregate_started,Clock::now());
    }
    out.result=result;out.correct=(result==expected);
    const double mean_worker=static_cast<double>(part.s.rows.size())/static_cast<double>(c.threads);
    const std::size_t max_worker=cost_aware
        ?static_cast<std::size_t>(out.worker_rows_over_avg*mean_worker)
        :*std::max_element(worker_rows.begin(),worker_rows.end());
    if(!cost_aware)out.worker_rows_over_avg=mean_worker>0.0?static_cast<double>(max_worker)/mean_worker:0.0;
    out.e2e_s=out.partition_s+out.build_s+out.estimate_s+out.task_plan_s+out.probe_s;
    return out;
}

Distribution describe(std::vector<double> v){
    if (v.empty()) return {};
    std::sort(v.begin(),v.end());
    auto q=[&](double f){const double x=f*static_cast<double>(v.size()-1);const std::size_t lo=static_cast<std::size_t>(x),hi=std::min(v.size()-1,lo+1);return v[lo]+(v[hi]-v[lo])*(x-static_cast<double>(lo));};
    Distribution d;d.med=q(.5);d.q1=q(.25);d.q3=q(.75);d.min=v.front();d.max=v.back();double mean=std::accumulate(v.begin(),v.end(),0.0)/v.size();double ss=0;for(double x:v)ss+=(x-mean)*(x-mean);d.sd=std::sqrt(ss/v.size());return d;
}
std::string csv_quote(const std::string& s){if(s.find_first_of(",\"\n")==std::string::npos)return s;std::string o="\"";for(char c:s){if(c=='\"')o+="\"\"";else o+=c;}return o+"\"";}

void run_self_tests(){
    const std::vector<std::string> algorithms={
        "radix_static","radix_dynamic_coarse","paper_fine_grained","novelty_budgeted",
        "cost_aware_no_steal","cost_aware_ungated_steal","novelty_cost_gated_steal"
    };
    const DataSet duplicates{{1,2,2,3,4,4,4,7},{2,2,4,7,8,0,2,4,4,4,4,4,4,4,4,4}};
    const DataSet empty_probe{{1,2,3},{}};
    const DataSet empty_build{{},{0,0,0,0,0,0,0}};
    const DataSet both_empty{{},{}};
    const std::vector<DataSet> cases={duplicates,empty_probe,empty_build,both_empty};
    for(int threads:{1,2,4}){
        Config c;c.partitions=16;c.threads=threads;c.chunk_size=2;c.tasks_per_thread=8;c.split_factor=1.5;
        for(const DataSet& data:cases){
            const u64 expected=reference_join_count(data);
            const PreparedData prepared=prepare_data(data,c);
            for(const std::string& algorithm:algorithms){
                const Run run=execute_prepared(prepared,c,algorithm,expected);
                if(!run.correct)
                    throw std::runtime_error("self-test correctness failure: "+algorithm
                        +", threads="+std::to_string(threads));
                if(run.successful_steal_batches>run.steal_attempts||run.successful_steals>run.tasks)
                    throw std::runtime_error("self-test observed impossible steal counters");
            }
        }
    }
    auto concurrent_case=[](std::vector<u32> r,std::vector<u32> s){
        Config c;c.partitions=16;c.threads=2;c.chunk_size=2;c.tasks_per_thread=8;c.split_factor=1.5;
        DataSet data{std::move(r),std::move(s)};
        const u64 expected=reference_join_count(data);
        const PreparedData prepared=prepare_data(data,c);
        const Run run=execute_prepared(prepared,c,"novelty_cost_gated_steal",expected);
        return run.correct&&run.result==expected;
    };
    auto first=std::async(std::launch::async,concurrent_case,
                          std::vector<u32>{1,2,2,3,4,4,4,7},
                          std::vector<u32>(256,4));
    auto second=std::async(std::launch::async,concurrent_case,
                           std::vector<u32>{10,11,12,13},
                           std::vector<u32>{10,10,11,12,13,13,99});
    if(!first.get()||!second.get())throw std::runtime_error("self-test concurrent execution failed");
    std::cout<<"PASS: duplicate keys, empty inputs, extreme skew, 1/2/4 threads, concurrent joins, and all schedulers.\n";
}

} // namespace

int main(int argc,char** argv){
    try{
        const Config c=parse_args(argc,argv);
        if(c.self_test){run_self_tests();return 0;}
#ifdef _OPENMP
        omp_set_dynamic(0);
#endif
        std::ofstream csv(c.csv_path,std::ios::out|std::ios::trunc);
        if(!csv)throw std::runtime_error("cannot write CSV: "+c.csv_path);
        std::ofstream raw_csv;
        if(!c.raw_csv_path.empty()){
            raw_csv.open(c.raw_csv_path,std::ios::out|std::ios::trunc);
            if(!raw_csv)throw std::runtime_error("cannot write raw CSV: "+c.raw_csv_path);
            raw_csv<<"seed_r,seed_s,skew,repetition,algorithm,r_size,s_size,key_range,partitions,threads,"
                   <<"chunk_size,tasks_per_thread,split_factor,queue_batch_size,cost_samples,"
                   <<"steal_threshold_multiplier,"
                   <<"expected_result,result,correct,partition_s,build_s,cost_estimation_s,task_planning_s,"
                   <<"probe_s,e2e_s,tasks,heavy_partitions,split_partitions,max_partition_over_avg,"
                   <<"worker_rows_over_avg,steal_attempts,successful_steals,successful_steal_batches,"
                   <<"failed_steals,threshold_skips,steal_cas_retries,"
                   <<"steal_threshold_ns,queue_admin_s,cost_model_holdout_wape_pct,"
                   <<"build_cost_ns_per_row,probe_cost_ns_per_row,cas_steal_cost_ns,"
                   <<"cache_migration_proxy_ns,split_benefit_ns\n";
        }
        csv<<"seed_r,seed_s,skew,algorithm,r_size,s_size,key_range,partitions,threads,repeats,chunk_size,"
              "tasks_per_thread,split_factor,queue_batch_size,cost_samples,steal_threshold_multiplier,"
              "expected_result,result,correct,partition_median_s,partition_min_s,"
              "partition_max_s,build_median_s,cost_estimation_median_s,task_planning_median_s,probe_median_s,"
              "e2e_median_s,e2e_q1_s,e2e_q3_s,e2e_min_s,e2e_max_s,e2e_sd_s,tasks_median,heavy_partitions,"
              "split_partitions,max_partition_over_avg,worker_rows_over_avg,steal_attempts_median,"
              "successful_steals_median,successful_steal_batches_median,failed_steals_median,"
              "threshold_skips_median,steal_cas_retries_median,steal_threshold_ns_median,"
              "queue_admin_median_s,cost_model_holdout_wape_median_pct,build_cost_ns_per_row_median,"
              "probe_cost_ns_per_row_median,cas_steal_cost_ns_median,cache_migration_proxy_ns_median,"
              "split_benefit_ns_median,parallel_speedup_vs_static,"
              "parallel_speedup_vs_sequential\n";
        std::cout<<"Parallel radix hash join reproduction + adaptive granularity experiment\n"
                 <<"R/build="<<c.r_size<<", S/probe="<<c.s_size<<", Zipf domain="<<c.key_range<<", partitions="<<c.partitions<<", threads="<<c.threads<<", repeats="<<c.repeats<<"\n";
        const std::vector<std::string> strategies={
            "radix_static","radix_dynamic_coarse","paper_fine_grained","novelty_budgeted",
            "cost_aware_no_steal","cost_aware_ungated_steal","novelty_cost_gated_steal"
        };
        std::vector<std::string> algorithms=strategies;
        algorithms.push_back("sequential_reference");
        std::cout<<std::left<<std::setw(7)<<"skew"<<std::setw(30)<<"algorithm"<<std::right<<std::setw(11)<<"E2E med"
                 <<std::setw(10)<<"tasks"<<std::setw(10)<<"heavy"<<"  correct\n";
        std::size_t skew_index = 0;
        for(double skew:c.skews){
            const DataSet data=generate_data(c,skew);const u64 expected=reference_join_count(data);
            struct Acc{
                std::vector<double> part,build,estimate,plan,probe,e2e,tasks,heavy,splits,part_ratio,worker_ratio;
                std::vector<double> attempts,successes,success_batches,failures,skips,steal_retries;
                std::vector<double> threshold,queue_admin,cost_wape,build_cost,probe_cost,cas_cost,migration_proxy,split_benefit;
                Run last;
            };
            std::unordered_map<std::string,Acc> acc;
            const PreparedData warm_prepared=prepare_data(data,c);
            for(const auto& alg:strategies){
                const Run warm=execute_prepared(warm_prepared,c,alg,expected);
                if(!warm.correct)throw std::runtime_error("warm-up correctness failure in "+alg+" at skew "+std::to_string(skew));
            }
            const std::size_t base_rot=static_cast<std::size_t>((c.seed_r+c.seed_s+skew_index)%algorithms.size());
            for(int rep=0;rep<c.repeats;++rep){
                const PreparedData prepared=prepare_data(data,c);
                std::vector<std::string> order=algorithms;
                std::rotate(order.begin(),order.begin()+static_cast<std::ptrdiff_t>((base_rot+static_cast<std::size_t>(rep))%order.size()),order.end());
                for(const auto& alg:order){
                    Run r;
                    if(alg=="sequential_reference"){
                        const auto started=Clock::now();
                        r.result=reference_join_count(data);
                        r.probe_s=seconds(started,Clock::now());
                        r.e2e_s=r.probe_s;
                        r.correct=(r.result==expected);
                    }else r=execute_prepared(prepared,c,alg,expected);
                    if(!r.correct)throw std::runtime_error("correctness failure in "+alg+" at skew "+std::to_string(skew));
                    auto& a=acc[alg];
                    a.part.push_back(r.partition_s);a.build.push_back(r.build_s);a.estimate.push_back(r.estimate_s);
                    a.plan.push_back(r.task_plan_s);a.probe.push_back(r.probe_s);a.e2e.push_back(r.e2e_s);
                    a.tasks.push_back(static_cast<double>(r.tasks));a.heavy.push_back(static_cast<double>(r.heavy_partitions));
                    a.splits.push_back(static_cast<double>(r.split_partitions));a.part_ratio.push_back(r.max_partition_over_avg);
                    a.worker_ratio.push_back(r.worker_rows_over_avg);a.attempts.push_back(static_cast<double>(r.steal_attempts));
                    a.successes.push_back(static_cast<double>(r.successful_steals));a.failures.push_back(static_cast<double>(r.failed_steals));
                    a.success_batches.push_back(static_cast<double>(r.successful_steal_batches));
                    a.skips.push_back(static_cast<double>(r.threshold_skips));
                    a.steal_retries.push_back(static_cast<double>(r.steal_cas_retries));
                    a.threshold.push_back(r.steal_threshold_ns);
                    a.build_cost.push_back(r.build_cost_ns_per_row);
                    a.probe_cost.push_back(r.probe_cost_ns_per_row);
                    a.cas_cost.push_back(r.cas_steal_cost_ns);
                    a.migration_proxy.push_back(r.cache_migration_proxy_ns);
                    a.split_benefit.push_back(r.split_benefit_ns);
                    if(std::isfinite(r.queue_admin_s))a.queue_admin.push_back(r.queue_admin_s);
                    if(std::isfinite(r.cost_model_holdout_wape_pct))a.cost_wape.push_back(r.cost_model_holdout_wape_pct);
                    a.last=r;
                    if(raw_csv){
                        raw_csv<<std::setprecision(10)<<c.seed_r<<','<<c.seed_s<<','<<skew<<','<<rep<<','
                               <<alg<<','<<c.r_size<<','<<c.s_size<<','<<c.key_range<<','<<c.partitions<<','
                               <<c.threads<<','<<c.chunk_size<<','<<c.tasks_per_thread<<','<<c.split_factor<<','
                               <<c.queue_batch_size<<','<<c.cost_samples<<','<<c.steal_threshold_multiplier<<','
                               <<expected<<','<<r.result<<','<<(r.correct?1:0)<<','
                               <<r.partition_s<<','<<r.build_s<<','<<r.estimate_s<<','<<r.task_plan_s<<','
                               <<r.probe_s<<','<<r.e2e_s<<','<<r.tasks<<','<<r.heavy_partitions<<','
                               <<r.split_partitions<<','<<r.max_partition_over_avg<<','<<r.worker_rows_over_avg<<','
                               <<r.steal_attempts<<','<<r.successful_steals<<','<<r.successful_steal_batches<<','
                               <<r.failed_steals<<','
                               <<r.threshold_skips<<','<<r.steal_cas_retries<<','<<r.steal_threshold_ns<<',';
                        if(std::isfinite(r.queue_admin_s))raw_csv<<r.queue_admin_s;
                        raw_csv<<',';
                        if(std::isfinite(r.cost_model_holdout_wape_pct))raw_csv<<r.cost_model_holdout_wape_pct;
                        raw_csv<<','<<r.build_cost_ns_per_row<<','<<r.probe_cost_ns_per_row<<','
                               <<r.cas_steal_cost_ns<<','<<r.cache_migration_proxy_ns<<','
                               <<r.split_benefit_ns<<'\n';
                    }
                }
            }
            const auto base=describe(acc["radix_static"].e2e).med;
            const double sequential=describe(acc["sequential_reference"].e2e).med;
            for(const auto& alg:algorithms){
                const auto& a=acc[alg];
                const auto pp=describe(a.part),bb=describe(a.build),est=describe(a.estimate),pl=describe(a.plan);
                const auto qq=describe(a.probe),ee=describe(a.e2e),t=describe(a.tasks),h=describe(a.heavy);
                const auto sp=describe(a.splits),pr=describe(a.part_ratio),wr=describe(a.worker_ratio);
                const auto attempts=describe(a.attempts),successes=describe(a.successes);
                const auto success_batches=describe(a.success_batches),failures=describe(a.failures);
                const auto skips=describe(a.skips),steal_retries=describe(a.steal_retries);
                const auto threshold=describe(a.threshold),build_cost=describe(a.build_cost);
                const auto probe_cost=describe(a.probe_cost),cas_cost=describe(a.cas_cost);
                const auto migration_proxy=describe(a.migration_proxy),split_benefit=describe(a.split_benefit);
                const double speed_static=ee.med>0?base/ee.med:0.0;
                const double speed_seq=ee.med>0?sequential/ee.med:0.0;
                std::cout<<std::defaultfloat<<std::left<<std::setw(7)<<skew<<std::setw(30)<<alg<<std::right
                         <<std::fixed<<std::setprecision(6)<<std::setw(11)<<ee.med<<std::setw(10)
                         <<static_cast<std::size_t>(t.med)<<std::setw(10)<<static_cast<std::size_t>(h.med)<<"  YES\n";
                csv<<std::setprecision(10)<<c.seed_r<<','<<c.seed_s<<','<<skew<<','<<csv_quote(alg)<<','
                   <<c.r_size<<','<<c.s_size<<','<<c.key_range<<','<<c.partitions<<','<<c.threads<<','
                   <<c.repeats<<','<<c.chunk_size<<','<<c.tasks_per_thread<<','<<c.split_factor<<','
                   <<c.queue_batch_size<<','<<c.cost_samples<<','<<c.steal_threshold_multiplier<<','
                   <<expected<<','<<a.last.result<<','<<(a.last.correct?1:0)<<','<<pp.med<<','<<pp.min<<','
                   <<pp.max<<','<<bb.med<<','<<est.med<<','<<pl.med<<','<<qq.med<<','<<ee.med<<','
                   <<ee.q1<<','<<ee.q3<<','<<ee.min<<','<<ee.max<<','<<ee.sd<<','
                   <<static_cast<std::size_t>(t.med)<<','<<static_cast<std::size_t>(h.med)<<','
                   <<static_cast<std::size_t>(sp.med)<<','<<pr.med<<','<<wr.med<<','
                   <<attempts.med<<','<<successes.med<<','<<success_batches.med<<','<<failures.med<<','<<skips.med<<','
                   <<steal_retries.med<<','<<threshold.med<<',';
                if(!a.queue_admin.empty())csv<<describe(a.queue_admin).med;
                csv<<',';
                if(!a.cost_wape.empty())csv<<describe(a.cost_wape).med;
                csv<<','<<build_cost.med<<','<<probe_cost.med<<','<<cas_cost.med<<','
                   <<migration_proxy.med<<','<<split_benefit.med<<','<<speed_static<<','<<speed_seq<<'\n';
            }
            csv.flush();if(raw_csv)raw_csv.flush();++skew_index;
        }
        std::cout<<"Summary CSV written to: "<<c.csv_path<<"\n";
        if(raw_csv)std::cout<<"Raw per-repetition CSV written to: "<<c.raw_csv_path<<"\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<"\nUse --help for usage.\n";return 1;}
}
